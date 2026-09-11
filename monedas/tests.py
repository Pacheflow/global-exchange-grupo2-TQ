import json
import time
from unittest.mock import patch

from django.test import TestCase

from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import Moneda


class MonedaBackendTests(TestCase):
    """
    Pruebas de Backend para HU-36 - Configurar Monedas.
    """

    def setUp(self):
        # Los casos CRUD necesitan un catálogo vacío; la migración de datos
        # iniciales se valida por separado en MonedasInicialesTests.
        Moneda.objects.all().delete()

    def autenticar(self, roles=None):
        """
        Crea una sesión OIDC válida para las pruebas.
        """

        roles = roles or ["ADMINISTRADOR"]

        session = self.client.session

        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-prueba-001",
            "preferred_username": "admin.prueba",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 3600

        session.save()

    def test_usuario_no_autenticado_recibe_401(self):
        response = self.client.get("/api/monedas/")

        self.assertEqual(response.status_code, 401)

    def test_usuario_sin_rol_administrador_recibe_403(self):
        self.autenticar(["USUARIO"])

        response = self.client.get("/api/monedas/")

        self.assertEqual(response.status_code, 403)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_crear_moneda(self, _mock_sesion):
        self.autenticar()

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": "USD",
                    "nombre": "Dólar estadounidense",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Moneda.objects.count(), 1)

        moneda = Moneda.objects.get()

        self.assertEqual(moneda.codigo, "USD")
        self.assertEqual(moneda.nombre, "Dólar estadounidense")
        self.assertEqual(moneda.simbolo, "$")
        self.assertEqual(moneda.estado, "ACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_codigo_se_normaliza(self, _mock_sesion):
        self.autenticar()

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": " usd ",
                    "nombre": "Dólar estadounidense",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        moneda = Moneda.objects.get()

        self.assertEqual(moneda.codigo, "USD")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_codigo_duplicado_despues_de_normalizar(self, _mock_sesion):
        self.autenticar()

        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar estadounidense",
            simbolo="$",
            estado="ACTIVA",
        )

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": " usd ",
                    "nombre": "Otra descripción",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Moneda.objects.count(), 1)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_rechaza_datos_obligatorios(self, _mock_sesion):
        self.autenticar()

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": "",
                    "nombre": "",
                    "simbolo": "",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Moneda.objects.count(), 0)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_editar_moneda(self, _mock_sesion):
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/editar/",
            data=json.dumps(
                {
                    "codigo": "EUR",
                    "nombre": "Euro",
                    "simbolo": "€",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.codigo, "EUR")
        self.assertEqual(moneda.nombre, "Euro")
        self.assertEqual(moneda.simbolo, "€")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_desactivar_moneda(self, _mock_sesion):
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/estado/",
            data=json.dumps(
                {"estado": "INACTIVA"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.estado, "INACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_desactivar_no_elimina_informacion_historica(self, _mock_sesion):
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        moneda_id = moneda.id

        response = self.client.post(
            f"/api/monedas/{moneda_id}/estado/",
            data=json.dumps(
                {"estado": "INACTIVA"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.id, moneda_id)
        self.assertEqual(moneda.codigo, "USD")
        self.assertEqual(moneda.nombre, "Dólar")
        self.assertEqual(moneda.estado, "INACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_reactivar_moneda(self, _mock_sesion):
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="INACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/estado/",
            data=json.dumps(
                {"estado": "ACTIVA"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.estado, "ACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_listar_solo_monedas_activas(self, _mock_sesion):
        self.autenticar()

        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        Moneda.objects.create(
            codigo="BRL",
            nombre="Real brasileño",
            simbolo="R$",
            estado="INACTIVA",
        )

        response = self.client.get("/api/monedas/activas/")

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(len(data["monedas"]), 1)
        self.assertEqual(data["monedas"][0]["codigo"], "USD")

    def test_catalogo_activo_es_publico(self):
        Moneda.objects.create(
            codigo="PYG",
            nombre="Guaraní",
            simbolo="Gs.",
            estado="ACTIVA",
        )

        response = self.client.get("/api/monedas/activas/")

        self.assertEqual(response.status_code, 200)
        moneda = response.json()["monedas"][0]
        self.assertEqual(moneda["codigo"], "PYG")
        self.assertEqual(
            set(moneda),
            {"id", "codigo", "nombre", "simbolo", "estado"},
        )
        self.assertNotIn("fecha_registro", moneda)
        self.assertNotIn("fecha_actualizacion", moneda)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_editar_con_codigo_existente_devuelve_409(self, _mock_sesion):
        self.autenticar()

        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        moneda = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
            estado="ACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/editar/",
            data=json.dumps(
                {
                    "codigo": "USD",
                    "nombre": "Euro",
                    "simbolo": "€",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_no_se_elimina_moneda_al_desactivar(self, _mock_sesion):
        self.autenticar()

        moneda = Moneda.objects.create(
                codigo="USD",
                nombre="Dólar",
                simbolo="$",
                estado="ACTIVA",
            )

        moneda_id = moneda.id

        response = self.client.post(
                f"/api/monedas/{moneda_id}/estado/",
                data=json.dumps(
                    {
                        "estado": "INACTIVA",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
                Moneda.objects.filter(id=moneda_id).exists()
            )

        moneda.refresh_from_db()

        self.assertEqual(moneda.estado, "INACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    @patch("monedas.views.MonedaForm.save")
    def test_error_al_guardar_informa_la_situacion(
            self,
            mock_save,
            _mock_sesion,
        ):
        self.autenticar()

        mock_save.side_effect = Exception("Error de persistencia")

        response = self.client.post(
                "/api/monedas/crear/",
                data=json.dumps(
                    {
                        "codigo": "USD",
                        "nombre": "Dólar",
                        "simbolo": "$",
                        "estado": "ACTIVA",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 500)

        self.assertEqual(
                response.json()["error"],
                "No fue posible guardar la moneda.",
            )


    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    @patch("monedas.views.MonedaForm.save")
    def test_error_al_actualizar_informa_la_situacion(
        self,
        mock_save,
        _mock_sesion,
    ):
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        mock_save.side_effect = Exception("Error de persistencia")

        response = self.client.post(
            f"/api/monedas/{moneda.id}/editar/",
            data=json.dumps(
                {
                    "codigo": "USD",
                    "nombre": "Dólar estadounidense",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 500)

        self.assertEqual(
            response.json()["error"],
            "No fue posible actualizar la moneda.",
        )


class MonedasInicialesTests(TestCase):
    """Comprueba el catálogo mínimo instalado por la migración de datos."""

    def test_migracion_carga_las_cinco_monedas_activas(self):
        self.assertEqual(
            set(Moneda.objects.values_list("codigo", "estado")),
            {
                ("USD", "ACTIVA"),
                ("PYG", "ACTIVA"),
                ("BRL", "ACTIVA"),
                ("EUR", "ACTIVA"),
                ("ARS", "ACTIVA"),
            },
        )
