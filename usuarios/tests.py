import base64
import hashlib
import json
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.db import connection
from django.http import HttpResponseRedirect
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
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
from .views import FLUJO_LOGIN, FLUJO_REGISTRO, OIDC_FLOWS_SESSION_KEY


class FlujoOIDCMixin:
    """Mixin con utilidades compartidas para probar los flujos OIDC."""

    client: Any

    def iniciar_flujo(self, nombre_url):
        response = cast(HttpResponseRedirect, self.client.get(reverse(nombre_url)))
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


class InicioYCallbackOIDCTests(FlujoOIDCMixin, TestCase):
    """Pruebas del inicio de flujo y el callback OIDC con PKCE.

    Requisito relacionado: RF-01 / RF-03 (RNF-01).
    """

    def test_landing_expone_tasas_comerciales_sin_proveedor_tecnico(self):
        """La portada pública comunica compra/venta sin detalles de integración."""

        response = self.client.get(reverse("usuarios:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compra")
        self.assertContains(response, "Venta")
        self.assertNotContains(response, "ExchangeRate-API")
        self.assertNotContains(response, "Fuente de referencia")

    def test_registro_inicia_oidc_con_callback_state_y_pkce(self):
        """Comprueba que el flujo de registro redirija a Keycloak con state y PKCE S256.

        Se espera que la redirección apunte al endpoint de registros y que el flujo
        quede guardado en sesión con su code_verifier.

        Requisito relacionado: RF-01 / RF-03.
        """
        response, params, state, flow = self.iniciar_flujo("usuarios:registro")
        verifier = flow["code_verifier"]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/protocol/openid-connect/registrations", response.url)
        self.assertEqual(params["redirect_uri"], [settings.OIDC_CALLBACK_URL])
        self.assertEqual(params["state"], [state])
        self.assertEqual(flow["tipo_flujo"], FLUJO_REGISTRO)
        self.assertEqual(params["code_challenge"], [challenge])
        self.assertEqual(params["code_challenge_method"], ["S256"])

    def test_login_inicia_oidc_con_callback_state_y_pkce(self):
        """Comprueba que el flujo de login redirija a Keycloak con state y PKCE S256.

        Se espera que la redirección apunte al endpoint de autenticación y que el
        flujo quede guardado con su code_verifier.

        Requisito relacionado: RF-03.
        """
        response, params, state, flow = self.iniciar_flujo("usuarios:login")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/protocol/openid-connect/auth", response.url)
        self.assertEqual(params["redirect_uri"], [settings.OIDC_CALLBACK_URL])
        self.assertEqual(params["state"], [state])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(flow["tipo_flujo"], FLUJO_LOGIN)
        self.assertIn("code_verifier", flow)

    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_callback_registro_identifica_el_flujo_y_no_expone_tokens(
        self, mock_post, mock_validar_token
    ):
        """Comprueba que el callback de registro reconozca el flujo y no exponga tokens.

        Se espera que la respuesta informe el flujo de registro sin incluir el access token.

        Requisito relacionado: RF-01.
        """
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
        self.assertNotIn("access_token", response.json())

    def test_intentos_login_simultaneos_conservan_verifiers_independientes(self):
        """Comprueba que dos intentos de login simultáneos mantengan flujos independientes.

        Se espera que cada intento tenga su propio state y code_verifier sin pisar al otro.
        """
        _, _, state_1, flow_1 = self.iniciar_flujo("usuarios:login")
        _, _, state_2, flow_2 = self.iniciar_flujo("usuarios:login")

        self.assertNotEqual(state_1, state_2)
        self.assertNotEqual(flow_1["code_verifier"], flow_2["code_verifier"])
        self.assertEqual(len(self.client.session[OIDC_FLOWS_SESSION_KEY]), 2)

    def test_callback_rechaza_state_incorrecto(self):
        """Comprueba que el callback rechace un state que no corresponde a ningún flujo.

        Se espera que la solicitud sea rechazada (400) y se limpien los flujos de la sesión.
        """
        self.iniciar_flujo("usuarios:login")

        response = self.client.get(
            reverse("usuarios:callback"),
            {"code": "codigo-prueba", "state": "state-ajeno"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(OIDC_FLOWS_SESSION_KEY, self.client.session)

    def test_callback_rechaza_state_expirado(self):
        """Comprueba que el callback rechace un state que superó el tiempo máximo de vigencia.

        Se espera que la solicitud sea rechazada (400).
        """
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
    def test_callback_rechaza_state_reutilizado(
        self, mock_post, mock_validar_token
    ):
        """Comprueba que un state no pueda reutilizarse en dos callbacks.

        Se espera que el segundo uso del mismo state sea rechazado (400).
        """
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "token-prueba"}
        mock_validar_token.return_value = self.claims_validos()
        params = {"code": "codigo-prueba", "state": state}

        primera = self.client.get(reverse("usuarios:callback"), params)
        segunda = self.client.get(reverse("usuarios:callback"), params)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 400)

    def test_callback_sin_codigo_consume_el_state(self):
        """Comprueba que el callback sin código de autorización consuma el state.

        Se espera que la solicitud sea rechazada (400) y el state deje de estar disponible.
        """
        _, _, state, _ = self.iniciar_flujo("usuarios:login")

        response = self.client.get(reverse("usuarios:callback"), {"state": state})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"], "No se recibió código de autorización"
        )
        self.assertNotIn(OIDC_FLOWS_SESSION_KEY, self.client.session)

    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_callback_login_valido_usa_verifier_y_crea_sesion(
        self, mock_post, mock_validar_token
    ):
        """Comprueba que un callback login válido use el code_verifier guardado y cree la sesión.

        Se espera que el intercambio use el verifier del flujo y que la sesión quede
        autenticada con su refresh token.

        Requisito relacionado: RF-03.
        """
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
        self.assertEqual(
            mock_post.call_args.kwargs["data"]["code_verifier"],
            flow["code_verifier"],
        )
        self.assertTrue(self.client.session[SESSION_AUTENTICADO])
        self.assertEqual(self.client.session[SESSION_REFRESH_TOKEN], "refresh-prueba")

    @patch("usuarios.views.validar_access_token")
    @patch("usuarios.views.requests.post")
    def test_callback_rechaza_access_token_invalido(
        self, mock_post, mock_validar_token
    ):
        """Comprueba que el callback rechace un access token que no valida.

        Se espera que la solicitud sea rechazada (400) y no se cree sesión.
        """
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
    def test_callback_ignora_next_y_usa_destino_fijo(
        self, mock_post, mock_validar_token
    ):
        """Comprueba que el callback ignore el parámetro next y use el destino fijo.

        Se espera que la redirección apunte a la URL de éxito configurada, evitando
        redirecciones abiertas.

        Requisito relacionado: RNF-02.
        """
        _, _, state, _ = self.iniciar_flujo("usuarios:login")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "token-prueba"}
        mock_validar_token.return_value = self.claims_validos()

        response = self.client.get(
            reverse("usuarios:callback"),
            {
                "code": "codigo-prueba",
                "state": state,
                "next": "https://malicioso",
            },
        )

        self.assertRedirects(
            response,
            "http://localhost:3000/inicio",
            fetch_redirect_response=False,
        )


class SesionYAutorizacionTests(TestCase):
    """Pruebas de sesión OIDC y autorización por rol.

    Requisito relacionado: RNF-02.
    """

    client: Any

    def autenticar_con_roles(self, roles, expira_en=None):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        profile = {
            "sub": "usuario-keycloak-1",
            "username": "usuario.prueba",
            "email": "usuario@example.com",
        }
        session[SESSION_USUARIO] = profile
        session["kc_user"] = profile
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = expira_en or int(time.time()) + 300
        session.save()

    def test_perfil_sesion_vigente_devuelve_identidad_y_roles(self):
        """Comprueba que el perfil devuelva los datos del usuario autenticado.

        Se espera que la respuesta incluya la identidad y los roles de la sesión.
        """
        self.autenticar_con_roles(["USUARIO"])

        response = self.client.get(reverse("usuarios:perfil_usuario"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["roles"], ["USUARIO"])

    def test_perfil_sesion_expirada_limpia_autenticacion(self):
        """Comprueba que una sesión OIDC expirada se limpie al consultar el perfil.

        Se espera que la solicitud sea rechazada (401) y se eliminen los datos de
        autenticación de la sesión.
        """
        self.autenticar_con_roles(["ADMINISTRADOR"], int(time.time()) - 1)

        response = self.client.get(reverse("usuarios:perfil_usuario"))

        self.assertEqual(response.status_code, 401)
        self.assertNotIn(SESSION_AUTENTICADO, self.client.session)
        self.assertNotIn(SESSION_ROLES, self.client.session)

    def test_administrador_accede_a_vista_protegida(self):
        """Comprueba que un usuario con rol administrador acceda a una vista protegida.

        Se espera una respuesta exitosa que confirme el acceso.
        """
        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.get(reverse("usuarios:acceso_administrador"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Acceso administrativo permitido")

    def test_usuario_no_autenticado_recibe_401(self):
        """Comprueba que una vista protegida rechace a los usuarios no autenticados.

        Se espera un estado 401 con mensaje de autenticación requerida.
        """
        response = self.client.get(reverse("usuarios:acceso_administrador"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Autenticación requerida")

    def test_usuario_sin_rol_administrador_recibe_403(self):
        """Comprueba que una vista de administrador rechace a un usuario sin ese rol.

        Se espera un estado 403 con mensaje de acceso denegado.
        """
        self.autenticar_con_roles(["USUARIO"])

        response = self.client.get(reverse("usuarios:acceso_administrador"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Acceso denegado")

    def test_multirrol_administrador_cajero_opera_como_administrador(self):
        """El rol administrador prevalece también en páginas y endpoints."""

        self.autenticar_con_roles(["CAJERO", "ADMINISTRADOR"])

        dashboard = self.client.get(reverse("usuarios:dashboard"))
        operaciones = self.client.get(reverse("operaciones_web:inicio"))
        confirmar = self.client.post(
            reverse("operaciones:crear_transaccion"),
            data="{}",
            content_type="application/json",
        )

        self.assertTemplateUsed(dashboard, "frontend/dashboard_administrador.html")
        self.assertTrue(operaciones.context["es_supervisor"])
        self.assertEqual(confirmar.status_code, 403)

    def test_multirrol_analista_usuario_opera_como_analista(self):
        """El analista prevalece y no hereda clientes ni operaciones de usuario."""

        self.autenticar_con_roles(["USUARIO", "ANALISTA_CAMBIARIO"])

        dashboard = self.client.get(reverse("usuarios:dashboard"))
        clientes = self.client.get(reverse("consultar_clientes"))
        operaciones = self.client.get(reverse("operaciones_web:inicio"))

        self.assertTemplateUsed(dashboard, "frontend/dashboard_analista.html")
        self.assertEqual(clientes.status_code, 403)
        self.assertEqual(operaciones.status_code, 403)

    def test_dashboard_analista_no_consulta_asociaciones_de_clientes(self):
        """El dashboard analista se construye sin consultar UsuarioCliente."""

        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

        with CaptureQueriesContext(connection) as consultas:
            response = self.client.get(reverse("usuarios:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/dashboard_analista.html")
        sql_ejecutado = "\n".join(consulta["sql"] for consulta in consultas)
        self.assertNotIn("clientes_usuariocliente", sql_ejecutado.lower())

    def test_multirrol_cajero_usuario_opera_como_cajero(self):
        """El cajero prevalece sobre usuario y conserva el modo operativo."""

        self.autenticar_con_roles(["USUARIO", "CAJERO"])

        dashboard = self.client.get(reverse("usuarios:dashboard"))
        operaciones = self.client.get(reverse("operaciones_web:inicio"))

        self.assertTemplateUsed(dashboard, "frontend/dashboard_cajero.html")
        self.assertEqual(operaciones.status_code, 200)
        self.assertFalse(operaciones.context["es_supervisor"])

    def test_logout_limpia_sesion_y_redirige_a_keycloak(self):
        """Comprueba que el logout limpie la sesión y redirija al cierre de sesión de Keycloak.

        Se espera que la sesión quede limpia y la redirección use el id_token como pista.
        """
        self.autenticar_con_roles(["USUARIO"])
        session = self.client.session
        session["kc_id_token"] = "id-token-prueba"
        session[SESSION_REFRESH_TOKEN] = "refresh-token-prueba"
        session[SESSION_REFRESH_EXPIRA_EN] = int(time.time()) + 1800
        session.save()

        response = cast(HttpResponseRedirect, self.client.get(reverse("usuarios:logout")))
        params = parse_qs(urlsplit(response.url).query)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/protocol/openid-connect/logout", response.url)
        self.assertEqual(params["id_token_hint"], ["id-token-prueba"])
        self.assertNotIn(SESSION_AUTENTICADO, self.client.session)
        self.assertNotIn(SESSION_REFRESH_TOKEN, self.client.session)


@override_settings(OIDC_REFRESH_MARGIN_SECONDS=60)
class RenovacionSesionOIDCTests(FlujoOIDCMixin, TestCase):
    """Pruebas de renovación de la sesión OIDC mediante refresh token.

    Requisito relacionado: RNF-01.
    """

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

    def test_login_sin_refresh_elimina_refresh_anterior(self):
        """Comprueba que un login sin refresh token elimine un refresh previo.

        Se espera que no queden tokens de renovación antiguos en la sesión.
        """
        request = self.preparar_request()

        establecer_sesion_oidc(
            request,
            self.claims_validos(["USUARIO"]),
            rotar_clave=False,
        )

        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)
        self.assertNotIn(SESSION_REFRESH_EXPIRA_EN, request.session)

    @patch("usuarios.services.keycloak.renovar_sesion_oidc", return_value=True)
    def test_sesion_proxima_a_vencer_solicita_refresh(self, mock_renovar):
        """Comprueba que una sesión próxima a vencer solicite la renovación automática.

        Se espera que la sesión se considere vigente y se ejecute la renovación.
        """
        request = self.preparar_request(expira_en=int(time.time()) + 30)

        self.assertTrue(sesion_oidc_vigente(request))
        mock_renovar.assert_called_once_with(request)

    @patch("usuarios.services.keycloak.validar_access_token")
    @patch("usuarios.services.keycloak.requests.post")
    def test_refresh_valido_actualiza_claims_roles_y_rota_token(
        self, mock_post, mock_validar_token
    ):
        """Comprueba que una renovación válida actualice claims y roles y rote el refresh token.

        Se espera que la sesión refleje los datos nuevos y el refresh token rotado.
        """
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        claims_nuevos = self.claims_validos(["USUARIO", "CAJERO"])
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "access-nuevo",
            "refresh_token": "refresh-rotado",
            "refresh_expires_in": 1700,
            "id_token": "id-token-nuevo",
        }
        mock_validar_token.return_value = claims_nuevos

        self.assertTrue(renovar_sesion_oidc(request))

        self.assertEqual(request.session[SESSION_REFRESH_TOKEN], "refresh-rotado")
        self.assertEqual(request.session[SESSION_ROLES], ["CAJERO", "USUARIO"])
        self.assertEqual(request.session[SESSION_EXPIRA_EN], claims_nuevos["exp"])
        self.assertEqual(request.session["kc_id_token"], "id-token-nuevo")

    @patch("usuarios.services.keycloak.validar_access_token")
    @patch("usuarios.services.keycloak.requests.post")
    def test_endpoint_refresh_no_expone_tokens(self, mock_post, mock_validar_token):
        """Comprueba que la renovación vía endpoint no exponga los tokens nuevos.

        Se espera que la respuesta no contenga access ni refresh tokens.
        """
        self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "access-secreto-renovado",
            "refresh_token": "refresh-secreto-rotado",
            "refresh_expires_in": 1700,
        }
        mock_validar_token.return_value = self.claims_validos(["USUARIO"])

        response = self.client.get(reverse("usuarios:perfil_usuario"))

        self.assertEqual(response.status_code, 200)
        contenido = response.content.decode()
        self.assertNotIn("access-secreto-renovado", contenido)
        self.assertNotIn("refresh-secreto-rotado", contenido)
        self.assertNotIn("access_token", contenido)

    @patch("usuarios.services.keycloak.validar_access_token")
    @patch("usuarios.services.keycloak.requests.post")
    def test_refresh_sin_rotacion_conserva_token_actual(
        self, mock_post, mock_validar_token
    ):
        """Comprueba que sin refresh token nuevo en la respuesta se conserve el actual.

        Se espera que la sesión mantenga el refresh y el id_token previos.
        """
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "access-nuevo"}
        mock_validar_token.return_value = self.claims_validos(["USUARIO"])

        self.assertTrue(renovar_sesion_oidc(request))

        self.assertEqual(request.session[SESSION_REFRESH_TOKEN], "refresh-original")
        self.assertEqual(request.session["kc_id_token"], "id-token-original")

    @patch("usuarios.services.keycloak.requests.post")
    def test_invalid_grant_limpia_sesion(self, mock_post):
        """Comprueba que un invalid_grant al renovar limpie la sesión.

        Se espera que la renovación devuelva falso y se eliminen los datos de autenticación.
        """
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Session not active",
        }

        self.assertFalse(renovar_sesion_oidc(request))

        self.assertNotIn(SESSION_AUTENTICADO, request.session)
        self.assertNotIn(SESSION_USUARIO, request.session)
        self.assertNotIn(SESSION_ROLES, request.session)
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)

    @patch("usuarios.services.keycloak.requests.post")
    def test_error_de_conexion_en_refresh_limpia_sesion_y_no_revela_token(
        self, mock_post
    ):
        """Comprueba que un error de conexión durante la renovación limpie la sesión.

        Se espera que la renovación devuelva falso y no queden tokens en la sesión.
        """
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
        """Comprueba que un access token renovado inválido limpie la sesión.

        Se espera que la renovación devuelva falso y no queden tokens.
        """
        request = self.preparar_request(expira_en=int(time.time()) - 1)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "invalido"}
        mock_validar_token.side_effect = InvalidTokenError("Token inválido")

        self.assertFalse(renovar_sesion_oidc(request))

        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)
        self.assertNotIn(SESSION_AUTENTICADO, request.session)

    @patch("usuarios.services.keycloak.requests.post")
    def test_refresh_expirado_localmente_no_contacta_keycloak(self, mock_post):
        """Comprueba que un refresh expirado localmente no dispare llamadas a Keycloak.

        Se espera que la renovación devuelva falso sin realizar solicitudes HTTP.
        """
        request = self.preparar_request(
            expira_en=int(time.time()) - 1,
            refresh_expira_en=int(time.time()) - 1,
        )

        self.assertFalse(renovar_sesion_oidc(request))

        mock_post.assert_not_called()
        self.assertNotIn(SESSION_REFRESH_TOKEN, request.session)


class RolesYJWTTests(TestCase):
    """Pruebas de extracción de roles y validación de tokens JWT de Keycloak.

    Requisito relacionado: RF-27 (RN10).
    """

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

    def configurar_jwks(self, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value.key = (
            self.public_key
        )

    def test_extrae_solo_roles_definidos_por_el_sistema(self):
        """Comprueba que solo se extraigan los roles de negocio definidos por el sistema.

        Se espera que los roles internos de Keycloak o desconocidos sean ignorados.

        Requisito relacionado: RF-27 (RN10).
        """
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

    def test_combina_rol_usuario_heredado_con_roles_directos(self):
        """Comprueba que el rol USUARIO heredado se combine con los roles directos.

        Se espera que ambos queden en la lista de roles del sistema.

        Requisito relacionado: RF-27 (RN10).
        """
        claims = {
            "realm_access": {
                "roles": [
                    "default-roles-global-exchange",
                    "USUARIO",
                    "CAJERO",
                ]
            }
        }

        self.assertEqual(extraer_roles_sistema(claims), ["CAJERO", "USUARIO"])

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_valida_jwt_rs256_valido(self, mock_jwks):
        """Comprueba que un access token RS256 válido sea aceptado.

        Se espera que la validación devuelva los claims del token.
        """
        self.configurar_jwks(mock_jwks)

        claims = validar_access_token(self.crear_token())

        self.assertEqual(claims["sub"], "usuario-keycloak-1")

    @patch(
        "usuarios.services.keycloak.jwt.get_unverified_header",
        return_value={"alg": "none"},
    )
    def test_rechaza_jwt_alg_none(self, _mock_header):
        """Comprueba que se rechace un token sin firma (alg none).

        Se espera que la validación falle al no usarse un algoritmo permitido.
        """
        with self.assertRaises(InvalidAlgorithmError):
            validar_access_token("token-sin-firma")

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_jwt_expirado(self, mock_jwks):
        """Comprueba que se rechace un token cuyo vencimiento ya pasó.

        Se espera que la validación falle por token expirado.
        """
        self.configurar_jwks(mock_jwks)
        token = self.crear_token(exp=int(time.time()) - 30)

        with self.assertRaises(ExpiredSignatureError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_jwt_con_firma_incorrecta(self, mock_jwks):
        """Comprueba que se rechace un token firmado con otra clave.

        Se espera que la validación falle por firma inválida.
        """
        self.configurar_jwks(mock_jwks)
        otra_clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode(
            {
                "sub": "usuario-keycloak-1",
                "iss": settings.KEYCLOAK_EXPECTED_ISSUER,
                "iat": int(time.time()),
                "exp": int(time.time()) + 300,
                "azp": settings.KEYCLOAK_CLIENT_ID,
                "email_verified": True,
            },
            otra_clave,
            algorithm="RS256",
        )

        with self.assertRaises(InvalidSignatureError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_jwt_con_issuer_incorrecto(self, mock_jwks):
        """Comprueba que se rechace un token emitido por otro issuer.

        Se espera que la validación falle por issuer incorrecto.
        """
        self.configurar_jwks(mock_jwks)
        token = self.crear_token(iss="http://keycloak:8080/realms/otro-realm")

        with self.assertRaises(InvalidIssuerError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_jwt_de_otro_cliente(self, mock_jwks):
        """Comprueba que se rechace un token emitido para otro cliente.

        Se espera que la validación falle por audiencia/azp incorrecto.
        """
        self.configurar_jwks(mock_jwks)
        token = self.crear_token(azp="otro-cliente", aud=["account"])

        with self.assertRaises(InvalidAudienceError):
            validar_access_token(token)

    @patch("usuarios.services.keycloak._obtener_cliente_jwks")
    def test_rechaza_jwt_de_cuenta_no_verificada(self, mock_jwks):
        """Comprueba que se rechace un token de una cuenta sin correo verificado.

        Se espera que la validación falle para cuentas no verificadas.

        Requisito relacionado: RF-02.
        """
        self.configurar_jwks(mock_jwks)
        token = self.crear_token(email_verified=False)

        with self.assertRaises(InvalidTokenError):
            validar_access_token(token)


class AsignacionRolTests(TestCase):
    """Pruebas de asignación de roles a usuarios en Keycloak.

    Requisito relacionado: RF-27.
    """

    client: Any

    def autenticar_como(self, roles):
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

    def test_usuario_no_administrador_no_puede_asignar_rol(self):
        """Comprueba que solo los administradores puedan asignar roles.

        Se espera que un usuario sin ese rol reciba acceso denegado (403).

        Requisito relacionado: RNF-02.
        """
        self.autenticar_como(["USUARIO"])

        response = self.client.post(
            reverse("usuarios:asignar_rol"),
            data={"usuario_id": "usuario-1", "rol": "CAJERO"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    @patch("usuarios.views.asignar_rol_usuario")
    def test_administrador_asigna_rol(self, mock_asignar):
        """Comprueba que un administrador pueda asignar un rol a un usuario de Keycloak.

        Se espera que la asignación se realice a través del servicio de Keycloak.

        Requisito relacionado: RF-27.
        """
        self.autenticar_como(["ADMINISTRADOR"])

        response = self.client.post(
            reverse("usuarios:asignar_rol"),
            data={"usuario_id": "usuario-1", "rol": "CAJERO"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        mock_asignar.assert_called_once_with("usuario-1", "CAJERO")

    @patch("usuarios.views.asignar_rol_usuario")
    def test_asignar_rol_duplicado_informa_error(self, mock_asignar):
        """Comprueba que asignar un rol que el usuario ya posee informe un error controlado.

        Se espera que la solicitud sea rechazada (400) con el mensaje del servicio.
        """
        self.autenticar_como(["ADMINISTRADOR"])
        mock_asignar.side_effect = ValueError("El usuario ya posee ese rol.")

        response = self.client.post(
            reverse("usuarios:asignar_rol"),
            data={"usuario_id": "usuario-1", "rol": "CAJERO"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "El usuario ya posee ese rol.")


class UsuariosApiTests(TestCase):
    """Pruebas de la API de gestión de usuarios en Keycloak.

    Requisito relacionado: RF-01 / RF-27.
    """

    def autenticar_como(self, roles):
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
        self.autenticar_como(["ADMINISTRADOR"])

    @patch("usuarios.views.actualizar_roles_usuario")
    @patch("usuarios.views.admin_request")
    def test_api_crea_usuario_y_asigna_rol_directo(
        self, mock_admin_request, mock_actualizar_roles
    ):
        """Comprueba que la API cree un usuario en Keycloak y le asigne sus roles directos.

        Se espera que el usuario se registre y que el rol USUARIO no se asigne como
        directo por ser heredado.

        Requisito relacionado: RF-01 / RF-27.
        """
        mock_admin_request.side_effect = [None, [{"id": "kc-usuario-api"}]]

        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps(
                {
                    "username": "usuario.api",
                    "email": "api@example.com",
                    "password": "temporal-segura",
                    "roles": ["USUARIO", "CAJERO"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        mock_actualizar_roles.assert_called_once_with("kc-usuario-api", ["CAJERO"])

    @patch("usuarios.views.admin_request")
    def test_api_rechaza_usuario_con_datos_invalidos(self, mock_admin_request):
        """Comprueba que la API rechace un usuario con datos incompletos.

        Se espera que la solicitud sea rechazada (400) sin contactar a Keycloak.
        """
        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps(
                {
                    "username": "",
                    "email": "incompleto@example.com",
                    "password": "corta",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        mock_admin_request.assert_not_called()

    @patch("usuarios.views.roles_usuario", return_value=["ADMINISTRADOR"])
    @patch("usuarios.views.admin_request")
    def test_api_devuelve_detalle_usuario(
        self, mock_admin_request, _mock_roles_usuario
    ):
        """Comprueba que la API devuelva los datos y roles de un usuario existente.

        Se espera que la respuesta incluya el perfil y sus roles de negocio.
        """
        mock_admin_request.return_value = {
            "id": "kc-detalle",
            "username": "usuario.detalle",
            "email": "detalle@example.com",
            "firstName": "Detalle",
            "lastName": "User",
            "enabled": True,
        }

        response = self.client.get(
            reverse("usuarios_api:detalle_usuario", args=["kc-detalle"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "usuario.detalle")
        self.assertEqual(response.json()["roles"], ["ADMINISTRADOR"])

    @patch("usuarios.views.actualizar_roles_usuario")
    @patch("usuarios.views.admin_request")
    def test_api_edita_datos_estado_y_roles(
        self, mock_admin_request, mock_actualizar_roles
    ):
        """Comprueba que la API actualice datos, estado de habilitación y roles.

        Se espera que la edición se realice en Keycloak y que los roles se sincronicen.

        Requisito relacionado: RF-27.
        """
        usuario = {
            "id": "kc-editar",
            "username": "usuario.editar",
            "email": "antes@example.com",
            "enabled": True,
        }
        mock_admin_request.side_effect = [usuario, None]

        response = self.client.post(
            reverse("usuarios_api:editar_usuario", args=["kc-editar"]),
            data=json.dumps(
                {
                    "first_name": "Despues",
                    "last_name": "Editado",
                    "email": "despues@example.com",
                    "enabled": False,
                    "roles": ["USUARIO", "CAJERO"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        actualizacion = mock_admin_request.call_args_list[1]
        self.assertEqual(actualizacion.kwargs["method"], "PUT")
        self.assertFalse(actualizacion.kwargs["payload"]["enabled"])
        mock_actualizar_roles.assert_called_once_with(
            "kc-editar", ["USUARIO", "CAJERO"]
        )

    @patch("usuarios.views.admin_request")
    def test_api_deshabilita_usuario_sin_eliminarlo(self, mock_admin_request):
        """Comprueba que la baja de un usuario lo deshabilite conservando sus datos.

        Se espera que el usuario quede con enabled falso sin ser eliminado.
        """
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
        self.assertFalse(actualizacion.kwargs["payload"]["enabled"])

    def test_api_de_usuarios_exige_administrador(self):
        """Comprueba que la API de usuarios exija rol de administrador.

        Se espera que un usuario sin ese rol reciba acceso denegado (403).

        Requisito relacionado: RNF-02.
        """
        self.autenticar_como(["USUARIO"])

        response = self.client.post(
            reverse("usuarios_api:crear_usuario"),
            data=json.dumps(
                {
                    "username": "sin.permiso",
                    "email": "sin@example.com",
                    "password": "temporal-segura",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
