import base64
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.http import HttpResponseRedirect
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAlgorithmError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
)

from .services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_REFRESH_EXPIRA_EN,
    SESSION_REFRESH_TOKEN,
    SESSION_ROLES,
    SESSION_USUARIO,
    establecer_sesion_oidc,
    extraer_roles_sistema,
    renovar_sesion_oidc,
    sesion_oidc_vigente,
    validar_access_token,
)
from .keycloak import KeycloakError
from .views import FLUJO_LOGIN, FLUJO_REGISTRO, OIDC_FLOWS_SESSION_KEY


class FlujoOIDCMixin:
    client: Any

    def iniciar_flujo(self, nombre_url):
        response = cast(
            HttpResponseRedirect,
            self.client.get(reverse(nombre_url)),
        )
        params = parse_qs(urlsplit(response.url).query)
        state = params["state"][0]
        flow = self.client.session[OIDC_FLOWS_SESSION_KEY][state]
        return response, params, state, flow

    @staticmethod
    def claims_validos(roles=None):
        return {
            "sub": "usuario-keycloak-1",
            "preferred_username": "usuario.prueba",
            "email": "usuario@example.com",
            "email_verified": True,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "iss": settings.KEYCLOAK_EXPECTED_ISSUER,
            "azp": settings.KEYCLOAK_CLIENT_ID,
            "realm_access": {"roles": roles or ["USUARIO"]},
        }


class RegistroUsuarioTests(FlujoOIDCMixin, TestCase):
    def test_registro_redirige_a_keycloak(self):
        response, params, _, _ = self.iniciar_flujo("usuarios:registro")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.url).netloc, "localhost:8080")
        self.assertIn(
            "/realms/global-exchange/protocol/openid-connect/registrations",
            response.url,
        )
        self.assertEqual(params["client_id"], [settings.KEYCLOAK_CLIENT_ID])
        self.assertEqual(params["response_type"], ["code"])
        self.assertIn("openid", params["scope"][0])

    def test_registro_usa_callback_backend_configurado(self):
        _, params, _, _ = self.iniciar_flujo("usuarios:registro")

        self.assertEqual(params["redirect_uri"], [settings.OIDC_CALLBACK_URL])
        self.assertNotEqual(params["redirect_uri"], ["http://localhost:8000/"])

    def test_registro_genera_state_y_lo_asocia_al_flujo(self):
        _, params, state, flow = self.iniciar_flujo("usuarios:registro")

        self.assertEqual(params["state"], [state])
        self.assertEqual(flow["tipo_flujo"], FLUJO_REGISTRO)
        self.assertGreaterEqual(len(state), 32)

    def test_registro_usa_pkce_s256_asociado_al_state(self):
        _, params, _, flow = self.iniciar_flujo("usuarios:registro")
        verifier = flow["code_verifier"]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        self.assertGreaterEqual(len(verifier), 43)
        self.assertEqual(params["code_challenge"], [challenge])
        self.assertEqual(params["code_challenge_method"], ["S256"])

    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_callback_identifica_registro(self, mock_post, mock_validar_token):
        _, _, state, _ = self.iniciar_flujo("usuarios:registro")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "token-prueba"}
        mock_validar_token.return_value = self.claims_validos()

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-prueba", "state": state},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["flujo"], FLUJO_REGISTRO)
        self.assertEqual(response.json()["message"], "Registro y autenticación exitosos")
        self.assertNotIn("access_token", response.json())


class LoginUsuarioTests(FlujoOIDCMixin, TestCase):
    def test_login_genera_state_y_pkce(self):
        response, params, state, flow = self.iniciar_flujo("usuarios:login")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/protocol/openid-connect/auth", response.url)
        self.assertEqual(params["state"], [state])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(flow["tipo_flujo"], FLUJO_LOGIN)
        self.assertIn("code_verifier", flow)

    def test_intentos_simultaneos_conservan_verifiers_independientes(self):
        _, _, state_1, flow_1 = self.iniciar_flujo("usuarios:login")
        _, _, state_2, flow_2 = self.iniciar_flujo("usuarios:login")

        self.assertNotEqual(state_1, state_2)
        self.assertNotEqual(flow_1["code_verifier"], flow_2["code_verifier"])
        self.assertEqual(len(self.client.session[OIDC_FLOWS_SESSION_KEY]), 2)

    def test_callback_rechaza_state_faltante(self):
        self.iniciar_flujo("usuarios:login")

        response = self.client.get(
            reverse("usuarios:callback"), {"code": "codigo-prueba"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "State OIDC inválido o expirado")
        self.assertNotIn(OIDC_FLOWS_SESSION_KEY, self.client.session)

    def test_callback_rechaza_state_incorrecto(self):
        self.iniciar_flujo("usuarios:login")

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-prueba", "state": "state-ajeno"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(OIDC_FLOWS_SESSION_KEY, self.client.session)

    def test_callback_rechaza_codigo_faltante_y_consume_state(self):
        _, _, state, _ = self.iniciar_flujo("usuarios:login")

        response = self.client.get(reverse("usuarios:callback"), {"state": state})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"], "No se recibió código de autorización"
        )
        self.assertNotIn(OIDC_FLOWS_SESSION_KEY, self.client.session)

    def test_callback_rechaza_state_expirado(self):
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        session = self.client.session
        session[OIDC_FLOWS_SESSION_KEY][state]["creado_en"] = (
            int(time.time()) - settings.OIDC_FLOW_MAX_AGE_SECONDS - 1
        )
        session.save()

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-prueba", "state": state},
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(OIDC_FLOWS_SESSION_KEY, self.client.session)

    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_state_correcto_usa_su_verifier_y_crea_sesion(
        self, mock_post, mock_validar_token
    ):
        _, _, state, flow = self.iniciar_flujo("usuarios:login")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "token-prueba",
            "refresh_token": "refresh-prueba",
            "refresh_expires_in": 1800,
        }
        mock_validar_token.return_value = self.claims_validos(["USUARIO"])

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-prueba", "state": state},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Login exitoso")
        self.assertEqual(response.json()["roles"], ["USUARIO"])
        self.assertNotIn("access_token", response.json())
        self.assertEqual(
            mock_post.call_args.kwargs["data"]["code_verifier"],
            flow["code_verifier"],
        )
        self.assertEqual(
            mock_post.call_args.kwargs["data"]["redirect_uri"],
            settings.OIDC_CALLBACK_URL,
        )
        session = self.client.session
        self.assertTrue(session[SESSION_AUTENTICADO])
        self.assertGreater(session[SESSION_EXPIRA_EN], time.time())
        self.assertEqual(session[SESSION_REFRESH_TOKEN], "refresh-prueba")
        self.assertGreater(session[SESSION_REFRESH_EXPIRA_EN], time.time())
        self.assertGreater(session.get_expiry_age(), 300)
        self.assertNotIn("kc_access_token", session)
        self.assertNotIn("refresh_token", response.json())
        self.assertNotIn("refresh-prueba", response.content.decode())

    @patch("usuarios.views.requests.post")
    def test_callback_informa_keycloak_no_disponible(self, mock_post):
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        mock_post.side_effect = requests.RequestException("sin conexión")

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-prueba", "state": state},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Keycloak no está disponible")
        self.assertNotIn(OIDC_FLOWS_SESSION_KEY, self.client.session)

    @patch("usuarios.views.requests.post")
    def test_callback_informa_rechazo_del_intercambio(self, mock_post):
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        mock_post.return_value.status_code = 400

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-rechazado", "state": state},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"], "No se pudo autenticar con Keycloak"
        )
        self.assertNotIn(SESSION_AUTENTICADO, self.client.session)

    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_state_ya_utilizado_es_rechazado(self, mock_post, mock_validar_token):
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "token-prueba"}
        mock_validar_token.return_value = self.claims_validos()
        params = {"code": "codigo-prueba", "state": state}

        primera = self.client.get(reverse("usuarios:callback"), params)
        segunda = self.client.get(reverse("usuarios:callback"), params)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 400)
        self.assertTrue(self.client.session[SESSION_AUTENTICADO])

    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_callback_rechaza_token_invalido(self, mock_post, mock_validar_token):
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "invalido"}
        mock_validar_token.side_effect = InvalidTokenError("Token inválido")

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-prueba", "state": state},
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SESSION_AUTENTICADO, self.client.session)

    @override_settings(OIDC_LOGIN_SUCCESS_URL="http://localhost:3000/inicio")
    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_callback_solo_usa_destino_fijo_de_frontend(
        self, mock_post, mock_validar_token
    ):
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "token-prueba"}
        mock_validar_token.return_value = self.claims_validos()

        response = cast(
            HttpResponseRedirect,
            self.client.get(
                reverse("usuarios:callback"),
                {
                    "code": "codigo-prueba",
                    "state": state,
                    "next": "https://malicioso",
                },
            ),
        )

        self.assertRedirects(
            response,
            "http://localhost:3000/inicio",
            fetch_redirect_response=False,
        )


class AutorizacionBackendTests(TestCase):
    client: Any

    def autenticar_con_roles(self, roles, expira_en=None):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-keycloak-1",
            "username": "usuario.prueba",
            "email": "usuario@example.com",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = expira_en or int(time.time()) + 300
        session.save()

    def test_perfil_con_sesion_vigente_devuelve_identidad_y_roles(self):
        self.autenticar_con_roles(["USUARIO"])

        response = self.client.get(reverse("usuarios:perfil_usuario"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["roles"], ["USUARIO"])

    def test_perfil_rechaza_sesion_expirada_y_limpia_autenticacion(self):
        self.autenticar_con_roles(["ADMINISTRADOR"], int(time.time()) - 1)

        response = self.client.get(reverse("usuarios:perfil_usuario"))

        self.assertEqual(response.status_code, 401)
        self.assertNotIn(SESSION_AUTENTICADO, self.client.session)
        self.assertNotIn(SESSION_ROLES, self.client.session)

    def test_administrador_vigente_accede_a_vista_protegida(self):
        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.get(reverse("usuarios:acceso_administrador"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Acceso administrativo permitido")

    def test_usuario_sin_rol_administrador_recibe_403(self):
        self.autenticar_con_roles(["USUARIO"])

        response = self.client.get(reverse("usuarios:acceso_administrador"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Acceso denegado")

    def test_usuario_no_autenticado_recibe_401(self):
        response = self.client.get(reverse("usuarios:acceso_administrador"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Autenticación requerida")


@override_settings(OIDC_REFRESH_MARGIN_SECONDS=60)
class RenovacionSesionOIDCTests(FlujoOIDCMixin, TestCase):
    def preparar_request(self, *, expira_en=None, refresh_expira_en=None):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-keycloak-1",
            "username": "usuario.prueba",
            "email": "usuario@example.com",
        }
        session[SESSION_ROLES] = ["USUARIO"]
        session[SESSION_EXPIRA_EN] = expira_en or int(time.time()) + 300
        session[SESSION_REFRESH_TOKEN] = "refresh-original"
        session[SESSION_REFRESH_EXPIRA_EN] = (
            refresh_expira_en or int(time.time()) + 1800
        )
        session["kc_user"] = self.claims_validos(["USUARIO"])
        session["kc_id_token"] = "id-token-original"
        session.save()
        return SimpleNamespace(session=session)

    def test_refresh_token_invalido_no_deja_contexto_parcial(self):
        request = SimpleNamespace(session=self.client.session)

        with self.assertRaises(InvalidTokenError):
            establecer_sesion_oidc(
                request,
                self.claims_validos(["USUARIO"]),
                refresh_token=123,
                refresh_expires_in=1800,
            )

        self.assertNotIn(SESSION_AUTENTICADO, request.session)
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)

    def test_login_sin_refresh_elimina_refresh_anterior(self):
        request = self.preparar_request()

        establecer_sesion_oidc(
            request,
            self.claims_validos(["USUARIO"]),
            rotar_clave=False,
        )

        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)
        self.assertNotIn(SESSION_REFRESH_EXPIRA_EN, request.session)

    @patch("usuarios.services.keycloak.renovar_sesion_oidc")
    def test_token_vigente_no_hace_refresh(self, mock_renovar):
        request = self.preparar_request(expira_en=int(time.time()) + 120)

        self.assertTrue(sesion_oidc_vigente(request))
        mock_renovar.assert_not_called()

    @patch("usuarios.services.keycloak.renovar_sesion_oidc", return_value=True)
    def test_token_proximo_a_expirar_hace_refresh(self, mock_renovar):
        request = self.preparar_request(expira_en=int(time.time()) + 30)

        self.assertTrue(sesion_oidc_vigente(request))
        mock_renovar.assert_called_once_with(request)

    @patch("usuarios.services.keycloak.renovar_sesion_oidc", return_value=True)
    def test_token_expirado_intenta_refresh_y_mantiene_sesion(self, mock_renovar):
        request = self.preparar_request(expira_en=int(time.time()) - 1)

        self.assertTrue(sesion_oidc_vigente(request))
        mock_renovar.assert_called_once_with(request)

    @patch("usuarios.services.keycloak.validar_access_token")
    @patch("usuarios.services.keycloak.requests.post")
    def test_refresh_actualiza_claims_expiracion_roles_y_rota_token(
        self, mock_post, mock_validar_token
    ):
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        claims_nuevos = self.claims_validos(["USUARIO", "CAJERO"])
        claims_nuevos["exp"] = int(time.time()) + 300
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "access-nuevo",
            "refresh_token": "refresh-rotado",
            "refresh_expires_in": 1700,
            "id_token": "id-token-nuevo",
        }
        mock_validar_token.return_value = claims_nuevos

        self.assertTrue(renovar_sesion_oidc(request))

        data = mock_post.call_args.kwargs["data"]
        self.assertEqual(data["grant_type"], "refresh_token")
        self.assertEqual(data["refresh_token"], "refresh-original")
        self.assertEqual(data["client_id"], settings.KEYCLOAK_CLIENT_ID)
        mock_validar_token.assert_called_once_with("access-nuevo")
        self.assertEqual(request.session[SESSION_REFRESH_TOKEN], "refresh-rotado")
        self.assertEqual(request.session[SESSION_ROLES], ["CAJERO", "USUARIO"])
        self.assertEqual(request.session[SESSION_EXPIRA_EN], claims_nuevos["exp"])
        self.assertEqual(request.session["kc_user"], claims_nuevos)
        self.assertEqual(request.session["kc_id_token"], "id-token-nuevo")
        self.assertNotIn("kc_access_token", request.session)

    @patch("usuarios.services.keycloak.validar_access_token")
    @patch("usuarios.services.keycloak.requests.post")
    def test_endpoint_renueva_sesion_sin_exponer_tokens(
        self, mock_post, mock_validar_token
    ):
        self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "access-secreto-renovado",
            "refresh_token": "refresh-secreto-rotado",
            "refresh_expires_in": 1700,
        }
        mock_validar_token.return_value = self.claims_validos(
            ["USUARIO", "ANALISTA_CAMBIARIO"]
        )

        response = self.client.get(reverse("usuarios:perfil_usuario"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()["roles"]), {"USUARIO", "ANALISTA_CAMBIARIO"}
        )
        contenido = response.content.decode()
        self.assertNotIn("access-secreto-renovado", contenido)
        self.assertNotIn("refresh-secreto-rotado", contenido)
        self.assertNotIn("access_token", contenido)
        self.assertNotIn("refresh_token", contenido)

    @patch("usuarios.services.keycloak.validar_access_token")
    @patch("usuarios.services.keycloak.requests.post")
    def test_refresh_sin_rotacion_conserva_refresh_token_actual(
        self, mock_post, mock_validar_token
    ):
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "access-nuevo"}
        mock_validar_token.return_value = self.claims_validos(["USUARIO"])

        self.assertTrue(renovar_sesion_oidc(request))

        self.assertEqual(request.session[SESSION_REFRESH_TOKEN], "refresh-original")
        self.assertEqual(request.session["kc_id_token"], "id-token-original")

    @patch("usuarios.services.keycloak.requests.post")
    def test_invalid_grant_limpia_todo_el_contexto_oidc(self, mock_post):
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Session not active",
        }

        self.assertFalse(renovar_sesion_oidc(request))

        for clave in (
            SESSION_AUTENTICADO,
            SESSION_USUARIO,
            SESSION_ROLES,
            SESSION_EXPIRA_EN,
            SESSION_REFRESH_TOKEN,
            SESSION_REFRESH_EXPIRA_EN,
            "kc_user",
            "kc_id_token",
        ):
            self.assertNotIn(clave, request.session)

    @patch("usuarios.services.keycloak.requests.post")
    def test_respuesta_http_inesperada_limpia_sesion(self, mock_post):
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 503

        self.assertFalse(renovar_sesion_oidc(request))
        mock_post.return_value.json.assert_not_called()
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)
        self.assertNotIn(SESSION_AUTENTICADO, request.session)

    @patch("usuarios.services.keycloak.requests.post")
    def test_json_invalido_durante_refresh_limpia_sesion(self, mock_post):
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.side_effect = ValueError("JSON inválido")

        self.assertFalse(renovar_sesion_oidc(request))
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)
        self.assertNotIn(SESSION_AUTENTICADO, request.session)

    @patch("usuarios.services.keycloak.requests.post")
    def test_error_de_conexion_no_revela_token_y_limpia_sesion(self, mock_post):
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.side_effect = requests.RequestException("sin conexión")

        self.assertFalse(renovar_sesion_oidc(request))
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)
        self.assertNotIn(SESSION_AUTENTICADO, request.session)

    @patch("usuarios.services.keycloak.validar_access_token")
    @patch("usuarios.services.keycloak.requests.post")
    def test_access_token_renovado_invalido_limpia_sesion(
        self, mock_post, mock_validar_token
    ):
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "invalido"}
        mock_validar_token.side_effect = InvalidTokenError("Token inválido")

        self.assertFalse(renovar_sesion_oidc(request))
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)
        self.assertNotIn(SESSION_AUTENTICADO, request.session)

    @patch("usuarios.services.keycloak.requests.post")
    def test_refresh_token_expirado_localmente_no_contacta_keycloak(self, mock_post):
        request = self.preparar_request(
            expira_en=int(time.time()) - 1,
            refresh_expira_en=int(time.time()) - 1,
        )

        self.assertFalse(renovar_sesion_oidc(request))
        mock_post.assert_not_called()
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)


class MetodosHTTPYLogoutTests(TestCase):
    client: Any

    def autenticar_con_roles(self, roles):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-metodos",
            "username": "usuario.metodos",
            "email": "metodos@example.com",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = int(time.time()) + 300
        session["kc_user"] = {
            "sub": "usuario-metodos",
            "preferred_username": "usuario.metodos",
        }
        session.save()

    def test_vistas_publicas_de_lectura_rechazan_post(self):
        urls = (
            reverse("usuarios:home"),
            reverse("usuarios:login"),
            reverse("usuarios:registro"),
            reverse("usuarios:callback"),
            reverse("usuarios:logout"),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 405)

    def test_vistas_protegidas_rechazan_metodos_no_soportados(self):
        self.autenticar_con_roles(["ADMINISTRADOR"])
        urls_solo_get = (
            reverse("usuarios:dashboard"),
            reverse("usuarios:list"),
            reverse("usuarios:clients"),
            reverse("usuarios:perfil_usuario"),
            reverse("usuarios:acceso_administrador"),
        )

        for url in urls_solo_get:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 405)

        self.assertEqual(self.client.put(reverse("usuarios:create")).status_code, 405)
        self.assertEqual(
            self.client.put(reverse("usuarios:edit", args=["usuario-1"])).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(reverse("usuarios:disable", args=["usuario-1"])).status_code,
            405,
        )

    def test_gestion_de_usuarios_rechaza_anonimos_y_no_administradores(self):
        rutas = (
            ("get", reverse("usuarios:list")),
            ("get", reverse("usuarios:create")),
            ("get", reverse("usuarios:edit", args=["usuario-1"])),
            ("post", reverse("usuarios:disable", args=["usuario-1"])),
        )

        for metodo, url in rutas:
            with self.subTest(tipo="anonimo", url=url):
                response = getattr(self.client, metodo)(url)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("usuarios:login"))

        self.autenticar_con_roles(["USUARIO"])
        for metodo, url in rutas:
            with self.subTest(tipo="sin_rol", url=url):
                self.assertEqual(getattr(self.client, metodo)(url).status_code, 403)

    def test_logout_limpia_sesion_y_redirige_a_keycloak(self):
        self.autenticar_con_roles(["USUARIO"])
        session = self.client.session
        session["kc_id_token"] = "id-token-prueba"
        session[SESSION_REFRESH_TOKEN] = "refresh-token-prueba"
        session[SESSION_REFRESH_EXPIRA_EN] = int(time.time()) + 1800
        session.save()

        response = cast(
            HttpResponseRedirect,
            self.client.get(reverse("usuarios:logout")),
        )
        params = parse_qs(urlsplit(response.url).query)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/protocol/openid-connect/logout", response.url)
        self.assertEqual(params["id_token_hint"], ["id-token-prueba"])
        self.assertEqual(params["client_id"], [settings.KEYCLOAK_CLIENT_ID])
        self.assertNotIn(SESSION_AUTENTICADO, self.client.session)
        self.assertNotIn(SESSION_ROLES, self.client.session)
        self.assertNotIn(SESSION_REFRESH_TOKEN, self.client.session)
        self.assertNotIn(SESSION_REFRESH_EXPIRA_EN, self.client.session)
        self.assertNotIn("kc_id_token", self.client.session)


class RolesKeycloakTests(TestCase):
    def test_extrae_solo_roles_definidos_por_el_sistema(self):
        claims = {
            "realm_access": {
                "roles": [
                    "ADMINISTRADOR",
                    "USUARIO",
                    "offline_access",
                    "rol-inventado",
                ]
            }
        }

        self.assertEqual(
            extraer_roles_sistema(claims), ["ADMINISTRADOR", "USUARIO"]
        )

    def test_rol_usuario_es_aceptado(self):
        claims = {"realm_access": {"roles": ["USUARIO"]}}

        self.assertEqual(extraer_roles_sistema(claims), ["USUARIO"])

    def test_nuevo_usuario_solo_recibe_usuario_como_rol_de_negocio_efectivo(self):
        claims = {
            "realm_access": {
                "roles": [
                    "default-roles-global-exchange",
                    "offline_access",
                    "uma_authorization",
                    "USUARIO",
                ]
            }
        }

        self.assertEqual(extraer_roles_sistema(claims), ["USUARIO"])

    def test_roles_directos_se_suman_a_usuario_heredado(self):
        for rol_directo in (
            "CAJERO",
            "ANALISTA_CAMBIARIO",
            "ADMINISTRADOR",
        ):
            with self.subTest(rol_directo=rol_directo):
                claims = {
                    "realm_access": {
                        "roles": [
                            "default-roles-global-exchange",
                            "USUARIO",
                            rol_directo,
                        ]
                    }
                }

                self.assertEqual(
                    set(extraer_roles_sistema(claims)), {"USUARIO", rol_directo}
                )


class ValidacionTokenTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()

    def crear_token(self, **overrides):
        claims = {
            "sub": "usuario-keycloak-1",
            "iss": settings.KEYCLOAK_EXPECTED_ISSUER,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "azp": settings.KEYCLOAK_CLIENT_ID,
            "email_verified": True,
        }
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm="RS256")

    @patch(
        "usuarios.services.keycloak.jwt.get_unverified_header",
        return_value={"alg": "none"},
    )
    def test_rechaza_alg_none(self, _mock_header):
        with self.assertRaises(InvalidAlgorithmError):
            validar_access_token("token-sin-firma")

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_valida_token_rs256_con_firma_issuer_expiracion_y_cliente(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )

        claims = validar_access_token(self.crear_token())

        self.assertEqual(claims["sub"], "usuario-keycloak-1")
        mock_jwks.assert_called_once_with(
            f"{settings.KEYCLOAK_INTERNAL_URL.rstrip('/')}"
            f"/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
        )

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_token_expirado(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )
        token = self.crear_token(exp=int(time.time()) - 30)

        with self.assertRaises(ExpiredSignatureError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_firma_incorrecta(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )
        otra_clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {
            "sub": "usuario-keycloak-1",
            "iss": settings.KEYCLOAK_EXPECTED_ISSUER,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "azp": settings.KEYCLOAK_CLIENT_ID,
            "email_verified": True,
        }
        token = jwt.encode(claims, otra_clave, algorithm="RS256")

        with self.assertRaises(InvalidSignatureError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_acepta_cliente_en_aud_sin_azp(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )
        token = self.crear_token(azp=None, aud=[settings.KEYCLOAK_CLIENT_ID])

        claims = validar_access_token(token)

        self.assertIn(settings.KEYCLOAK_CLIENT_ID, claims["aud"])

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_issuer_incorrecto(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )
        token = self.crear_token(iss="http://keycloak:8080/realms/global-exchange")

        with self.assertRaises(InvalidIssuerError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_cliente_incorrecto(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )
        token = self.crear_token(azp="otro-cliente", aud=["account"])

        with self.assertRaises(InvalidAudienceError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_cuenta_no_verificada(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )
        token = self.crear_token(email_verified=False)

        with self.assertRaises(InvalidTokenError):
            validar_access_token(token)


class GestionUsuariosBackendTests(TestCase):
    client: Any

    def setUp(self):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "admin-gestion",
            "username": "admin.gestion",
            "email": "admin@example.com",
        }
        session[SESSION_ROLES] = ["ADMINISTRADOR"]
        session[SESSION_EXPIRA_EN] = int(time.time()) + 300
        session["kc_user"] = {
            "sub": "admin-gestion",
            "preferred_username": "admin.gestion",
        }
        session.save()

    @patch("usuarios.views.admin_request")
    def test_listado_renderiza_usuarios_de_keycloak(self, mock_admin_request):
        mock_admin_request.return_value = [
            {
                "id": "kc-user-1",
                "username": "usuario.listado",
                "email": "listado@example.com",
                "enabled": True,
            }
        ]

        response = self.client.get(reverse("usuarios:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "usuario.listado")
        mock_admin_request.assert_called_once_with("/users?max=100")

    @patch("usuarios.views.admin_request")
    def test_listado_informa_error_controlado_de_keycloak(self, mock_admin_request):
        mock_admin_request.side_effect = KeycloakError("Keycloak no disponible")

        response = self.client.get(reverse("usuarios:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Keycloak no disponible")

    @patch("usuarios.views.actualizar_roles_usuario")
    @patch("usuarios.views.admin_request")
    def test_creacion_codifica_busqueda_y_asigna_roles(
        self, mock_admin_request, mock_actualizar_roles
    ):
        mock_admin_request.side_effect = [None, [{"id": "kc-user-creado"}]]

        response = self.client.post(
            reverse("usuarios:create"),
            {
                "username": "usuario+qa@example.com",
                "email": "usuario.qa@example.com",
                "first_name": "Usuario",
                "last_name": "QA",
                "password": "temporal-segura",
                "roles": ["CAJERO"],
            },
        )

        self.assertEqual(response.status_code, 302)
        primera_llamada, segunda_llamada = mock_admin_request.call_args_list
        self.assertEqual(primera_llamada.args[0], "/users")
        self.assertEqual(primera_llamada.kwargs["method"], "POST")
        self.assertTrue(
            primera_llamada.kwargs["payload"]["credentials"][0]["temporary"]
        )
        self.assertEqual(
            segunda_llamada.args[0],
            "/users?username=usuario%2Bqa%40example.com&exact=true",
        )
        mock_actualizar_roles.assert_called_once_with("kc-user-creado", ["CAJERO"])

    @patch("usuarios.views.actualizar_roles_usuario")
    @patch("usuarios.views.admin_request")
    def test_creacion_sin_roles_confia_en_usuario_heredado(
        self, mock_admin_request, mock_actualizar_roles
    ):
        mock_admin_request.side_effect = [None, [{"id": "kc-user-default"}]]

        response = self.client.post(
            reverse("usuarios:create"),
            {
                "username": "usuario.default",
                "email": "default@example.com",
                "password": "temporal-segura",
            },
        )

        self.assertEqual(response.status_code, 302)
        mock_actualizar_roles.assert_not_called()

    @patch("usuarios.views.roles_usuario", return_value=["USUARIO"])
    @patch("usuarios.views.admin_request")
    def test_edicion_get_usa_objeto_de_keycloak(
        self, mock_admin_request, mock_roles_usuario
    ):
        mock_admin_request.return_value = {
            "id": "kc-user-editar",
            "username": "usuario.editar",
            "email": "editar@example.com",
            "firstName": "Nombre",
            "lastName": "Apellido",
            "enabled": True,
        }

        response = self.client.get(
            reverse("usuarios:edit", args=["kc-user-editar"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "editar@example.com")
        mock_admin_request.assert_called_once_with("/users/kc-user-editar")
        mock_roles_usuario.assert_called_once_with("kc-user-editar")

    @patch("usuarios.views.admin_request")
    def test_baja_deshabilita_sin_eliminar_usuario(self, mock_admin_request):
        usuario = {
            "id": "kc-user-baja",
            "username": "usuario.baja",
            "enabled": True,
        }
        mock_admin_request.side_effect = [usuario, None]

        response = self.client.post(
            reverse("usuarios:disable", args=["kc-user-baja"])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_admin_request.call_count, 2)
        actualizacion = mock_admin_request.call_args_list[1]
        self.assertEqual(actualizacion.args[0], "/users/kc-user-baja")
        self.assertEqual(actualizacion.kwargs["method"], "PUT")
        self.assertFalse(actualizacion.kwargs["payload"]["enabled"])


class ConfiguracionRealmTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ruta = Path(settings.BASE_DIR) / "keycloak" / "global-exchange-realm.json"
        cls.realm = json.loads(ruta.read_text(encoding="utf-8"))

    def test_registro_y_verificacion_email_estan_habilitados(self):
        self.assertTrue(self.realm["registrationAllowed"])
        self.assertTrue(self.realm["verifyEmail"])
        self.assertFalse(self.realm["duplicateEmailsAllowed"])
        verify_email = next(
            action
            for action in self.realm["requiredActions"]
            if action["alias"] == "VERIFY_EMAIL"
        )
        self.assertTrue(verify_email["enabled"])

    def test_smtp_apunta_a_mailpit(self):
        self.assertEqual(self.realm["smtpServer"]["host"], "mailpit")
        self.assertEqual(self.realm["smtpServer"]["port"], "1025")

    def test_usuario_es_unico_rol_de_negocio_asignado_por_defecto(self):
        default_role = next(
            role
            for role in self.realm["roles"]["realm"]
            if role["name"] == "default-roles-global-exchange"
        )
        roles_por_defecto = set(default_role["composites"]["realm"])

        self.assertIn("USUARIO", roles_por_defecto)
        self.assertTrue(
            roles_por_defecto.isdisjoint(
                {"ADMINISTRADOR", "CAJERO", "ANALISTA_CAMBIARIO"}
            )
        )

    def test_default_role_del_realm_apunta_al_composite_global_exchange(self):
        default_role = next(
            role
            for role in self.realm["roles"]["realm"]
            if role["name"] == "default-roles-global-exchange"
        )

        self.assertEqual(self.realm["defaultRole"]["id"], default_role["id"])
        self.assertEqual(
            self.realm["defaultRole"]["name"], "default-roles-global-exchange"
        )
        self.assertTrue(default_role["composite"])

    def test_cliente_exige_pkce_s256(self):
        cliente = next(
            client
            for client in self.realm["clients"]
            if client["clientId"] == "global-exchange-web"
        )

        self.assertEqual(
            cliente["attributes"]["pkce.code.challenge.method"], "S256"
        )

    def test_registro_exige_password_en_formulario_inicial(self):
        registration_form = next(
            flow
            for flow in self.realm["authenticationFlows"]
            if flow["alias"] == "registration form"
        )
        password_validation = next(
            execution
            for execution in registration_form["authenticationExecutions"]
            if execution.get("authenticator") == "registration-password-action"
        )

        self.assertEqual(password_validation["requirement"], "REQUIRED")
        config_alias = password_validation["authenticatorConfig"]
        password_config = next(
            config
            for config in self.realm["authenticatorConfig"]
            if config["alias"] == config_alias
        )
        self.assertEqual(
            password_config["config"]["always_set_password_on_register_form"],
            "true",
        )

class AsignarRolTests(TestCase):
    client: Any

    def _autenticar_como(self, roles):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "admin-prueba",
            "username": "admin",
            "email": "admin@prueba.com",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session.save()

    def test_requiere_autenticacion(self):
        response = self.client.post(
            reverse("usuarios:asignar_rol"),
            data={
                "usuario_id": "usuario-1",
                "rol": "CAJERO",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_requiere_rol_administrador(self):
        self._autenticar_como(["USUARIO"])

        response = self.client.post(
            reverse("usuarios:asignar_rol"),
            data={
                "usuario_id": "usuario-1",
                "rol": "CAJERO",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    @patch("usuarios.views.asignar_rol_usuario")
    def test_administrador_puede_asignar_rol(self, mock_asignar):
        self._autenticar_como(["ADMINISTRADOR"])

        response = self.client.post(
            reverse("usuarios:asignar_rol"),
            data={
                "usuario_id": "usuario-1",
                "rol": "CAJERO",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        mock_asignar.assert_called_once_with("usuario-1", "CAJERO")

    @patch("usuarios.views.asignar_rol_usuario")
    def test_no_permite_rol_duplicado(self, mock_asignar):
        self._autenticar_como(["ADMINISTRADOR"])
        mock_asignar.side_effect = ValueError("El usuario ya posee ese rol.")

        response = self.client.post(
            reverse("usuarios:asignar_rol"),
            data={
                "usuario_id": "usuario-1",
                "rol": "CAJERO",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "El usuario ya posee ese rol.",
        )


class RolesPermisosViewTests(TestCase):
    """Comprueba la consulta administrativa de roles de Keycloak."""

    def _autenticar_como(self, roles):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "admin-roles",
            "username": "admin.roles",
            "email": "admin.roles@example.com",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session["kc_user"] = {
            "sub": "admin-roles",
            "preferred_username": "admin.roles",
        }
        session.save()

    def test_usuario_anonimo_es_redirigido_al_login(self):
        response = self.client.get(reverse("usuarios:roles_permisos"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_usuario_sin_rol_administrador_recibe_403(self):
        self._autenticar_como(["USUARIO"])

        response = self.client.get(reverse("usuarios:roles_permisos"))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "usuarios/forbidden.html")

    @patch("usuarios.views.admin_request")
    def test_administrador_consulta_los_roles_de_keycloak(self, mock_admin_request):
        self._autenticar_como(["ADMINISTRADOR"])
        mock_admin_request.return_value = [
            {"name": "ADMINISTRADOR"},
            {"name": "CAJERO"},
            {"name": "ANALISTA_CAMBIARIO"},
            {"name": "USUARIO"},
            {"name": "offline_access"},
        ]

        response = self.client.get(reverse("usuarios:roles_permisos"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/roles_permisos.html")
        self.assertEqual(len(response.context["roles_sistema"]), 4)
        self.assertTrue(
            all(role["configurado"] for role in response.context["roles_sistema"])
        )
        mock_admin_request.assert_called_once_with("/roles")

    @patch("usuarios.views.admin_request")
    def test_error_de_keycloak_conserva_la_vista_informativa(
        self,
        mock_admin_request,
    ):
        self._autenticar_como(["ADMINISTRADOR"])
        mock_admin_request.side_effect = KeycloakError(
            "No se pudo conectar con Keycloak."
        )

        response = self.client.get(reverse("usuarios:roles_permisos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin verificar", count=4)
        self.assertContains(response, "No se pudo verificar Keycloak")


class FrontendApiScreensTests(TestCase):
    """Verifica que las pantallas conectadas exponen su configuración de API."""

    def _autenticar_como(self, roles):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "frontend-api-user",
            "username": "frontend.api",
            "email": "frontend.api@example.com",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session["kc_user"] = {
            "sub": "frontend-api-user",
            "preferred_username": "frontend.api",
        }
        session.save()

    def test_monedas_carga_la_configuracion_de_api(self):
        self._autenticar_como(["ADMINISTRADOR"])

        response = self.client.get(reverse("usuarios:monedas"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/monedas.html")
        self.assertContains(response, 'data-ge-api="currencies"')
        self.assertContains(response, reverse("monedas:listar_monedas"))

    def test_tasas_comerciales_carga_la_configuracion_de_api(self):
        self._autenticar_como(["ANALISTA_CAMBIARIO"])

        response = self.client.get(reverse("usuarios:tasas_comerciales"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/tasas_comerciales.html")
        self.assertContains(response, 'data-ge-api="rates"')
        self.assertContains(response, reverse("tasas:historial_tasas_comerciales"))
        self.assertContains(response, "Tasas comerciales")
        self.assertContains(response, "Nueva tasa comercial")
        self.assertContains(response, "cada modificación crea una nueva versión")
        self.assertContains(response, 'data-can-manage="true"')
        self.assertContains(response, "data-deactivate-url=")

    def test_pagos_carga_la_configuracion_de_api(self):
        self._autenticar_como(["ADMINISTRADOR"])

        response = self.client.get(reverse("usuarios:pagos"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/pagos.html")
        self.assertContains(response, 'data-ge-api="payments"')
        self.assertContains(response, reverse("metodos_pago:inicio_metodos_pago"))

    @patch("usuarios.views.admin_request", return_value=[])
    def test_navegacion_frontend_del_administrador_renderiza(self, _mock_admin_request):
        self._autenticar_como(["ADMINISTRADOR"])
        rutas = (
            reverse("usuarios:dashboard"),
            reverse("usuarios:list"),
            reverse("consultar_clientes"),
            reverse("usuarios:monedas"),
            reverse("usuarios:tasas"),
            reverse("usuarios:tasas_comerciales"),
            reverse("usuarios:pagos"),
            reverse("usuarios:roles_permisos"),
        )

        for ruta in rutas:
            with self.subTest(ruta=ruta):
                response = self.client.get(ruta)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<svg")
                self.assertNotContains(response, "Divisas")

    def test_navegacion_frontend_del_analista_renderiza(self):
        self._autenticar_como(["ANALISTA_CAMBIARIO"])
        rutas = (
            reverse("usuarios:dashboard"),
            reverse("usuarios:tasas"),
            reverse("usuarios:tasas_comerciales"),
            reverse("usuarios:monedas"),
        )

        for ruta in rutas:
            with self.subTest(ruta=ruta):
                response = self.client.get(ruta)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<svg")
                self.assertNotContains(response, "Divisas")


class NavegacionUsuarioTests(TestCase):
    """Protege la navegación honesta y los permisos visibles de USUARIO."""

    def _autenticar_como(self, roles=("USUARIO",), selected_client=None):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-navigation",
            "username": "usuario.navigation",
            "email": "usuario.navigation@example.com",
        }
        session[SESSION_ROLES] = list(roles)
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session["kc_user"] = {
            "sub": "usuario-navigation",
            "preferred_username": "usuario.navigation",
        }
        if selected_client:
            session["selected_client"] = selected_client
        session.save()

    @staticmethod
    def _sidebar(response):
        html = response.content.decode()
        return html.split('<nav class="ge-frontend-nav">', 1)[1].split("</nav>", 1)[0]

    def test_cada_ruta_real_tiene_un_unico_item_activo_en_sidebar(self):
        self._autenticar_como()
        rutas = {
            "usuarios:dashboard": "Resumen",
            "usuarios:tasas": "Tasas",
            "usuarios:simulador": "Conversor",
            "usuarios:monedas": "Monedas",
            "consultar_clientes": "Mi cliente",
        }

        for nombre, etiqueta in rutas.items():
            with self.subTest(nombre=nombre):
                response = self.client.get(reverse(nombre))
                self.assertEqual(response.status_code, 200)
                sidebar = self._sidebar(response)
                self.assertEqual(sidebar.count('aria-current="page"'), 1)
                self.assertIn(etiqueta, sidebar)

    def test_sidebar_separa_destinos_reales_de_funciones_pendientes(self):
        self._autenticar_como()

        response = self.client.get(reverse("usuarios:dashboard"))
        sidebar = self._sidebar(response)

        for nombre in (
            "usuarios:dashboard",
            "usuarios:tasas",
            "usuarios:simulador",
            "usuarios:monedas",
            "consultar_clientes",
        ):
            self.assertIn(f'href="{reverse(nombre)}"', sidebar)
        self.assertEqual(sidebar.count('class="ge-frontend-nav-pending"'), 5)
        self.assertEqual(sidebar.count(">Pendiente</span>"), 5)
        self.assertNotIn(reverse("usuarios:pagos"), sidebar)

    def test_dashboard_no_presenta_datos_ni_operaciones_simuladas(self):
        self._autenticar_como(selected_client={"id": 9, "name": "Cliente Real SA"})

        response = self.client.get(reverse("usuarios:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Real SA")
        self.assertContains(response, "FUNCIONES EN PREPARACIÓN")
        for contenido_falso in (
            "KNG S.A.",
            "TXN-2026-",
            "FAC-2026-",
            "31 de agosto de 2026",
            "Confirmar operación",
        ):
            self.assertNotContains(response, contenido_falso)

    def test_dashboard_explica_ausencia_de_cliente_seleccionado(self):
        self._autenticar_como()

        response = self.client.get(reverse("usuarios:dashboard"))

        self.assertContains(response, "No seleccionaste un cliente")
        self.assertContains(response, "Ver clientes asociados")

    def test_mi_cliente_muestra_estado_vacio_sin_controles_administrativos(self):
        self._autenticar_como()

        response = self.client.get(reverse("consultar_clientes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Mi cliente · Global Exchange</title>", html=True)
        self.assertContains(response, "No tenés clientes asociados disponibles.")
        self.assertNotContains(response, "+ Nuevo cliente")
        self.assertNotContains(response, "data-crear-url=")
        self.assertNotContains(response, "data-editar-url=")
        self.assertNotContains(response, "data-baja-url=")

    def test_pagos_de_configuracion_es_solo_para_administrador(self):
        self._autenticar_como()
        self.assertEqual(self.client.get(reverse("usuarios:pagos")).status_code, 403)

        self._autenticar_como(("ADMINISTRADOR",))
        response = self.client.get(reverse("usuarios:pagos"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/pagos.html")

    def test_navbar_autenticado_apunta_a_rutas_reales_y_seguridad_existe(self):
        self._autenticar_como()

        response = self.client.get(reverse("usuarios:seguridad"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/seguridad.html")
        for nombre in (
            "usuarios:dashboard",
            "usuarios:tasas",
            "usuarios:simulador",
            "usuarios:seguridad",
        ):
            self.assertContains(response, f'href="{reverse(nombre)}"')
        self.assertNotContains(response, 'data-nav-section="seguridad"')

    def test_usuario_solo_ve_consulta_de_monedas_activas(self):
        self._autenticar_como()

        response = self.client.get(reverse("usuarios:monedas"))

        self.assertContains(response, 'data-can-manage="false"')
        self.assertContains(response, reverse("monedas:listar_monedas_activas"))
        self.assertNotContains(response, "+ Nueva moneda")
        self.assertNotContains(response, ">Acciones</th>")
        self.assertNotContains(response, "data-create-url=")
        self.assertNotContains(response, "data-edit-url=")
        self.assertNotContains(response, "data-state-url=")

    def test_tasas_y_conversor_exponen_endpoints_independientes_y_reales(self):
        self._autenticar_como()

        tasas = self.client.get(reverse("usuarios:tasas"))
        conversor = self.client.get(reverse("usuarios:simulador"))

        self.assertContains(tasas, 'data-ge-api="reference-rates"')
        self.assertContains(tasas, reverse("tasas:consultar"))
        self.assertContains(tasas, "Tasas de referencia")
        self.assertContains(tasas, "Tasas comerciales vigentes")
        self.assertContains(tasas, "data-commercial-rates")
        self.assertNotContains(tasas, 'data-ge-api="simulator"')
        self.assertContains(conversor, 'data-ge-api="simulator"')
        self.assertContains(conversor, reverse("tasas:simular_conversion"))
        self.assertContains(conversor, reverse("monedas:listar_monedas_activas"))
        self.assertContains(conversor, "data-sim-delivered")
        self.assertContains(conversor, "data-sim-rate-type")
        self.assertNotContains(conversor, "data-sim-operation")
        self.assertNotContains(conversor, 'data-ge-api="reference-rates"')

    def test_menu_legacy_solo_muestra_medios_de_pago_al_admin(self):
        enlace = f'href="{reverse("usuarios:pagos")}"'

        for role in ("ADMINISTRADOR", "USUARIO", "CAJERO", "ANALISTA_CAMBIARIO"):
            with self.subTest(role=role):
                html = render_to_string(
                    "usuarios/forbidden.html",
                    {
                        "kc_user": {"preferred_username": "prueba"},
                        "kc_roles": [role],
                        "kc_display_name": "Prueba",
                        "request": SimpleNamespace(
                            resolver_match=SimpleNamespace(
                                url_name="forbidden",
                                app_name="usuarios",
                            )
                        ),
                        "required_roles": [],
                    },
                )
                if role == "ADMINISTRADOR":
                    self.assertIn(enlace, html)
                    self.assertIn("Medios de pago", html)
                else:
                    self.assertNotIn(enlace, html)
                    self.assertNotIn("Medios de pago", html)

    def test_conversor_no_integra_cliente_aunque_exista_una_seleccion(self):
        from clientes.models import Cliente, UsuarioCliente

        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Contextual Real",
            tipo_persona="JURIDICA",
            documento="CTX-REAL-001",
        )
        UsuarioCliente.objects.create(
            cliente=cliente,
            keycloak_user_id="usuario-navigation",
            username="usuario.navigation",
        )
        self._autenticar_como()

        seleccion = self.client.post(
            reverse("seleccionar_cliente", args=[cliente.id])
        )
        response = self.client.get(reverse("usuarios:simulador"))

        self.assertEqual(seleccion.status_code, 302)
        self.assertNotContains(response, "CLIENTE ACTUAL")
        self.assertNotContains(response, "CTX-REAL-001")
        self.assertNotContains(response, "Cambiar cliente")
        self.assertNotContains(response, "data-simulator-client-context")

    def test_conversor_no_requiere_cliente_ni_presenta_operacion(self):
        self._autenticar_como()

        response = self.client.get(reverse("usuarios:simulador"))

        self.assertNotContains(response, "cliente seleccionado")
        self.assertNotContains(response, "Seleccionar cliente")
        self.assertNotContains(response, "Continuar operación")
        self.assertNotContains(response, "Compra")
        self.assertNotContains(response, "Venta")

    def test_smoke_de_dashboards_para_los_cuatro_roles(self):
        for role in ("USUARIO", "CAJERO", "ANALISTA_CAMBIARIO", "ADMINISTRADOR"):
            with self.subTest(role=role):
                self._autenticar_como((role,))
                response = self.client.get(reverse("usuarios:dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<svg")

    def test_landing_publica_usa_endpoints_reales_y_no_carga_datos_demo(self):
        response = self.client.get(reverse("usuarios:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("tasas:consultar"))
        self.assertContains(response, reverse("tasas:simular_conversion"))
        self.assertContains(response, reverse("monedas:listar_monedas_activas"))
        self.assertContains(response, "data-converter-type")
        self.assertContains(response, "landing.js?v=rf09-hu19-20260910")
        self.assertNotContains(response, "js/ge-data.js")
        for contenido_falso in ("7.480", "8.120", "Datos demo", "KNG S.A."):
            self.assertNotContains(response, contenido_falso)

    def test_landing_preserva_la_composicion_visual_original(self):
        response = self.client.get(reverse("usuarios:home"))

        self.assertContains(response, "Líderes en")
        self.assertContains(response, 'class="ge-market-board"')
        self.assertContains(response, "Global Market")
        self.assertContains(response, "data-market-chart")
        self.assertContains(response, "Histórico · Próximamente")
        self.assertContains(response, 'class="frontend-currency-list"')

    def test_sidebars_por_rol_no_exponen_destinos_prohibidos(self):
        self._autenticar_como(("ADMINISTRADOR",))
        admin = self._sidebar(self.client.get(reverse("usuarios:dashboard")))
        self.assertIn(f'href="{reverse("usuarios:pagos")}"', admin)
        self.assertIn("Métodos de pago", admin)

        self._autenticar_como(("ANALISTA_CAMBIARIO",))
        response_analista = self.client.get(reverse("usuarios:dashboard"))
        analista = self._sidebar(response_analista)
        self.assertNotIn(reverse("usuarios:pagos"), analista)
        self.assertNotIn(reverse("usuarios:simulador"), analista)
        self.assertNotIn(reverse("consultar_clientes"), analista)
        for etiqueta in ("Tasas", "Tasas comerciales", "Monedas"):
            self.assertIn(etiqueta, analista)
        self.assertNotContains(
            response_analista, f'href="{reverse("usuarios:simulador")}"'
        )

        self._autenticar_como(("CAJERO",))
        response_cajero = self.client.get(reverse("usuarios:dashboard"))
        cajero = self._sidebar(response_cajero)
        self.assertEqual(cajero.count('class="ge-frontend-nav-pending"'), 6)
        self.assertEqual(cajero.count(f'href="{reverse("usuarios:dashboard")}"'), 1)
        self.assertNotIn(reverse("usuarios:simulador"), cajero)
        self.assertNotIn(reverse("consultar_clientes"), cajero)
        self.assertNotContains(
            response_cajero, f'href="{reverse("usuarios:simulador")}"'
        )

    def test_usuario_conserva_conversor_y_mi_cliente_en_sidebar_y_navbar(self):
        self._autenticar_como(("USUARIO",))

        response = self.client.get(reverse("usuarios:dashboard"))
        sidebar = self._sidebar(response)

        self.assertIn(f'href="{reverse("usuarios:simulador")}"', sidebar)
        self.assertIn(f'href="{reverse("consultar_clientes")}"', sidebar)
        self.assertContains(
            response,
            f'href="{reverse("usuarios:simulador")}"',
            count=4,
        )

    def test_rutas_compartidas_no_cambian_permisos_para_cajero_y_analista(self):
        for role in ("CAJERO", "ANALISTA_CAMBIARIO"):
            with self.subTest(role=role):
                self._autenticar_como((role,))
                self.assertEqual(
                    self.client.get(reverse("usuarios:simulador")).status_code,
                    200,
                )
                self.assertEqual(
                    self.client.get(reverse("consultar_clientes")).status_code,
                    200,
                )

    def test_admin_solo_consulta_tasas_comerciales_en_la_interfaz(self):
        self._autenticar_como(("ADMINISTRADOR",))

        response = self.client.get(reverse("usuarios:tasas_comerciales"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-can-manage="false"')
        self.assertNotContains(response, ">Nueva tasa comercial</button>")
        self.assertNotContains(response, "data-deactivate-url=")
        self.assertContains(response, reverse("tasas:historial_tasas_comerciales"))

    def test_dashboards_no_muestran_kpis_ficticios(self):
        falsos = ("KNG S.A.", "TXN-2026-", "48.2M", "614", "31 de agosto de 2026")
        for role in ("CAJERO", "ANALISTA_CAMBIARIO", "ADMINISTRADOR"):
            with self.subTest(role=role):
                self._autenticar_como((role,))
                response = self.client.get(reverse("usuarios:dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Próximamente")
                for contenido in falsos:
                    self.assertNotContains(response, contenido)

    def test_dashboard_admin_preserva_kpis_graficos_y_actividad(self):
        self._autenticar_como(("ADMINISTRADOR",))

        response = self.client.get(reverse("usuarios:dashboard"))
        html = response.content.decode()

        self.assertEqual(html.count("ge-kpi--icon"), 8)
        self.assertEqual(html.count("ge-chart-box"), 2)
        self.assertContains(response, "Actividad reciente")
        self.assertContains(response, "Actividad operativa · Próximamente")

    def test_dashboard_analista_preserva_kpis_y_graficos(self):
        self._autenticar_como(("ANALISTA_CAMBIARIO",))

        response = self.client.get(reverse("usuarios:dashboard"))
        html = response.content.decode()

        self.assertEqual(html.count("ge-kpi--icon"), 4)
        self.assertEqual(html.count("ge-chart-box"), 2)
        self.assertContains(response, "Histórico de tasas")
        self.assertContains(response, "Ganancia diaria · PYG")

    def test_dashboard_cajero_preserva_modulos_visuales_inactivos(self):
        self._autenticar_como(("CAJERO",))

        response = self.client.get(reverse("usuarios:dashboard"))
        html = response.content.decode()

        self.assertEqual(html.count("ge-card ge-balance"), 4)
        self.assertEqual(html.count("data-caja-panel="), 3)
        self.assertEqual(html.count("data-bill-currency="), 4)
        self.assertContains(response, 'id="cierre-caja"')
        self.assertEqual(html.count('class="ge-balance-state">PRÓXIMAMENTE'), 4)
        self.assertContains(response, "data-bill-currency-select disabled")


class UsuariosFrontendApiTest(TestCase):
    """Pruebas de los endpoints JSON utilizados por la interfaz Frontend."""

    def _autenticar_como(self, roles):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "admin-gestion",
            "username": "admin.gestion",
            "email": "admin@example.com",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 300
        session["kc_user"] = {
            "sub": "admin-gestion",
            "preferred_username": "admin.gestion",
        }
        session.save()

    def setUp(self):
        self._autenticar_como(["ADMINISTRADOR"])

    @patch("usuarios.views.actualizar_roles_usuario")
    @patch("usuarios.views.admin_request")
    def test_crear_usuario_api(self, mock_admin_request, mock_actualizar_roles):
        mock_admin_request.side_effect = [
            None,
            [{"id": "kc-usuario-api", "username": "usuario.api", "email": "api@example.com"}],
        ]

        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps({
                "username": "usuario.api",
                "email": "api@example.com",
                "first_name": "Usuario",
                "last_name": "API",
                "password": "temporal-segura",
                "roles": ["CAJERO"],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(mock_admin_request.call_count, 2)
        primera, segunda = mock_admin_request.call_args_list
        self.assertEqual(primera.args[0], "/users")
        self.assertEqual(primera.kwargs["method"], "POST")
        self.assertEqual(primera.kwargs["payload"]["username"], "usuario.api")
        self.assertIn("exact=true", segunda.args[0])
        mock_actualizar_roles.assert_called_once_with("kc-usuario-api", ["CAJERO"])

    @patch("usuarios.views.actualizar_roles_usuario")
    @patch("usuarios.views.admin_request")
    def test_crear_usuario_api_no_asigna_usuario_directamente(
        self, mock_admin_request, mock_actualizar_roles
    ):
        mock_admin_request.side_effect = [None, [{"id": "kc-usuario-default"}]]

        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps({
                "username": "usuario.default",
                "email": "default@example.com",
                "password": "temporal-segura",
                "roles": ["USUARIO"],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        mock_actualizar_roles.assert_not_called()

    @patch("usuarios.views.admin_request")
    def test_crear_usuario_api_datos_invalidos(self, mock_admin_request):
        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps({
                "username": "",
                "email": "incompleto@example.com",
                "password": "corta",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        mock_admin_request.assert_not_called()

    @patch("usuarios.views.admin_request")
    def test_crear_usuario_api_error_keycloak(self, mock_admin_request):
        mock_admin_request.side_effect = KeycloakError("Keycloak rechazó la creación.")

        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps({
                "username": "usuario.api",
                "email": "api@example.com",
                "password": "temporal-segura",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Keycloak rechazó la creación.",
        )

    @patch("usuarios.views.roles_usuario", return_value=["ADMINISTRADOR"])
    @patch("usuarios.views.admin_request")
    def test_detalle_usuario_api(self, mock_admin_request, mock_roles_usuario):
        mock_admin_request.return_value = {
            "id": "kc-detalle",
            "username": "usuario.detalle",
            "email": "detalle@example.com",
            "firstName": "Detalle",
            "lastName": "User",
            "enabled": True,
        }

        response = self.client.get(reverse("usuarios_api:detalle_usuario", args=["kc-detalle"]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "usuario.detalle")
        self.assertEqual(data["email"], "detalle@example.com")
        self.assertTrue(data["enabled"])
        self.assertEqual(data["roles"], ["ADMINISTRADOR"])

    @patch("usuarios.views.actualizar_roles_usuario")
    @patch("usuarios.views.admin_request")
    def test_editar_usuario_api(self, mock_admin_request, mock_actualizar_roles):
        usuario = {
            "id": "kc-editar",
            "username": "usuario.editar",
            "email": "antes@example.com",
            "firstName": "Antes",
            "lastName": "",
            "enabled": True,
        }
        mock_admin_request.side_effect = [usuario, None]

        response = self.client.post(
            reverse("usuarios_api:editar_usuario", args=["kc-editar"]),
            data=json.dumps({
                "first_name": "Despues",
                "last_name": "Editado",
                "email": "despues@example.com",
                "enabled": False,
                "roles": ["USUARIO", "CAJERO"],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        actualizacion = mock_admin_request.call_args_list[1]
        self.assertEqual(actualizacion.kwargs["method"], "PUT")
        self.assertEqual(actualizacion.kwargs["payload"]["enabled"], False)
        self.assertEqual(actualizacion.kwargs["payload"]["email"], "despues@example.com")
        mock_actualizar_roles.assert_called_once_with("kc-editar", ["USUARIO", "CAJERO"])

    @patch("usuarios.views.admin_request")
    def test_editar_usuario_api_inexistente(self, mock_admin_request):
        mock_admin_request.side_effect = KeycloakError("User cannot be found")

        response = self.client.post(
            reverse("usuarios_api:editar_usuario", args=["kc-no-existe"]),
            data=json.dumps({"first_name": "Nadie", "roles": []}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    @patch("usuarios.views.admin_request")
    def test_baja_usuario_api(self, mock_admin_request):
        usuario = {"id": "kc-baja", "username": "usuario.baja", "enabled": True}
        mock_admin_request.side_effect = [usuario, None]

        response = self.client.post(
            reverse("usuarios_api:baja_usuario", args=["kc-baja"]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        actualizacion = mock_admin_request.call_args_list[1]
        self.assertEqual(actualizacion.kwargs["method"], "PUT")
        self.assertEqual(actualizacion.kwargs["payload"]["enabled"], False)

    @patch("usuarios.views.admin_request")
    def test_baja_usuario_api_inexistente(self, mock_admin_request):
        mock_admin_request.side_effect = KeycloakError("User cannot be found")

        response = self.client.post(
            reverse("usuarios_api:baja_usuario", args=["kc-no-existe"]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_crear_usuario_requiere_administrador(self):
        self._autenticar_como(["USUARIO"])

        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps({
                "username": "sin.permiso",
                "email": "sin@example.com",
                "password": "temporal-segura",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_api_metodos_restringidos(self):
        urls_mutacion = [
            reverse("usuarios_api:crear_usuario"),
            reverse("usuarios_api:editar_usuario", args=["kc-405"]),
            reverse("usuarios_api:baja_usuario", args=["kc-405"]),
        ]

        for url in urls_mutacion:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

        with self.subTest(url="detalle"):
            response = self.client.post(
                reverse("usuarios_api:detalle_usuario", args=["kc-405"]),
                data=json.dumps({}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 405)
