import json
import time

from django.test import TestCase
from django.urls import reverse

from monedas.models import Moneda
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import TasaComercial


class TasaComercialTests(TestCase):
    """Pruebas de HU-21 - Administrar tasas comerciales."""

    def setUp(self):
        self.usd = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar estadounidense",
            simbolo="$",
            estado="ACTIVA",
        )

        self.pyg = Moneda.objects.create(
            codigo="PYG",
            nombre="Guaraní",
            simbolo="Gs.",
            estado="ACTIVA",
        )

        self.eur = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
            estado="INACTIVA",
        )

        self.url = reverse(
            "tasas:administrar_tasa_comercial"
        )

    def autenticar_con_roles(self, roles):
        """Crea una sesión válida para las pruebas."""
        session = self.client.session

        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "analista-keycloak-1",
            "username": "analista.prueba",
            "email": "analista@example.com",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 3600

        session.save()

    def enviar_tasa(self, datos):
        """Envía una tasa comercial como JSON."""
        return self.client.post(
            self.url,
            data=json.dumps(datos),
            content_type="application/json",
        )

    def test_usuario_anonimo_no_puede_modificar_tasa(self):
        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_usuario_con_rol_incorrecto_recibe_403(self):
        self.autenticar_con_roles(["USUARIO"])

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_analista_puede_registrar_tasa(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(TasaComercial.objects.count(), 1)

        tasa = TasaComercial.objects.get()

        self.assertEqual(tasa.version, 1)
        self.assertTrue(tasa.vigente)
        self.assertEqual(
            tasa.usuario_id,
            "analista-keycloak-1",
        )

    def test_rechaza_tasa_menor_o_igual_a_cero(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "0",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_rechaza_moneda_inactiva(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.eur.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_no_permite_misma_moneda_en_el_par(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.usd.id,
                "compra": "1",
                "venta": "1.1",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_primera_tasa_necesita_compra_y_venta(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_modificacion_conserva_historico(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        primera = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(primera.status_code, 201)

        segunda = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7250",
            }
        )

        self.assertEqual(segunda.status_code, 201)
        self.assertEqual(TasaComercial.objects.count(), 2)

        version_1 = TasaComercial.objects.get(
            version=1
        )

        version_2 = TasaComercial.objects.get(
            version=2
        )

        self.assertFalse(version_1.vigente)
        self.assertTrue(version_2.vigente)

        self.assertEqual(
            str(version_1.compra),
            "7200.000000",
        )

        self.assertEqual(
            str(version_2.compra),
            "7250.000000",
        )

        self.assertEqual(
            version_2.venta,
            version_1.venta,
        )

    def test_modificacion_registra_auditoria(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 201)

        tasa = TasaComercial.objects.get()

        self.assertEqual(
            tasa.usuario_id,
            "analista-keycloak-1",
        )

        self.assertEqual(
            tasa.usuario_username,
            "analista.prueba",
        )

        self.assertIsNotNone(
            tasa.fecha_registro
        )

    def test_validacion_fallida_no_modifica_tasa_vigente(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        primera = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(primera.status_code, 201)

        tasa_original = TasaComercial.objects.get(
            vigente=True
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "venta": "0",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 1)

        tasa_original.refresh_from_db()

        self.assertTrue(
            tasa_original.vigente
        )

        self.assertEqual(
            str(tasa_original.compra),
            "7200.000000",
        )

        self.assertEqual(
            str(tasa_original.venta),
            "7300.000000",
        )

    def test_historial_devuelve_versiones_registradas(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "venta": "7350",
            }
        )

        response = self.client.get(
            reverse(
                "tasas:historial_tasas_comerciales"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            len(response.json()["tasas"]),
            2,
        )