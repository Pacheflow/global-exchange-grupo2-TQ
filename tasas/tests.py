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
    def setUp(self):
        Moneda.objects.all().delete()
        self.usd = Moneda.objects.create(
            codigo="USD", nombre="Dólar estadounidense", simbolo="$", estado="ACTIVA"
        )
        self.pyg = Moneda.objects.create(
            codigo="PYG", nombre="Guaraní", simbolo="Gs.", estado="ACTIVA"
        )
        self.eur = Moneda.objects.create(
            codigo="EUR", nombre="Euro", simbolo="€", estado="INACTIVA"
        )
        self.url = reverse("tasas:administrar_tasa_comercial")

    def autenticar_con_roles(self, roles):
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
        return self.client.post(
            self.url,
            data=json.dumps(datos),
            content_type="application/json",
        )

    def crear_tasa_vigente(self):
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])
        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )
        self.assertEqual(response.status_code, 201)
        return TasaComercial.objects.get()

    def test_administrador_no_puede_modificar_tasa(self):
        self.autenticar_con_roles(["ADMINISTRADOR"])

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

    def test_analista_registra_tasa_con_auditoria(self):
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

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
        self.assertEqual(tasa.usuario_id, "analista-keycloak-1")
        self.assertEqual(tasa.usuario_username, "analista.prueba")
        self.assertIsNotNone(tasa.fecha_registro)

    def test_rechaza_tasa_no_positiva(self):
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

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
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

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

    def test_rechaza_par_con_la_misma_moneda(self):
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

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

    def test_primera_tasa_requiere_compra_y_venta(self):
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_modificacion_crea_version_y_conserva_historico(self):
        self.crear_tasa_vigente()

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7250",
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(TasaComercial.objects.count(), 2)
        self.assertFalse(TasaComercial.objects.get(version=1).vigente)
        self.assertTrue(TasaComercial.objects.get(version=2).vigente)

    def test_modificacion_invalida_conserva_tasa_vigente(self):
        tasa_original = self.crear_tasa_vigente()

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
        self.assertTrue(tasa_original.vigente)

    def test_historial_devuelve_versiones_en_orden(self):
        self.crear_tasa_vigente()
        self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "venta": "7350",
            }
        )

        response = self.client.get(reverse("tasas:historial_tasas_comerciales"))

        self.assertEqual(response.status_code, 200)
        versiones = response.json()["tasas"]
        self.assertEqual(versiones[0]["version"], 2)
        self.assertEqual(versiones[1]["version"], 1)

    def test_administrador_no_puede_desactivar_tasa(self):
        tasa = self.crear_tasa_vigente()
        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        tasa.refresh_from_db()
        self.assertTrue(tasa.vigente)

    def test_analista_desactiva_tasa_sin_eliminarla_y_permanece_en_historial(self):
        tasa = self.crear_tasa_vigente()

        response = self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        historial = self.client.get(reverse("tasas:historial_tasas_comerciales"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TasaComercial.objects.count(), 1)
        self.assertEqual(historial.json()["tasas"][0]["id"], tasa.id)
        self.assertFalse(historial.json()["tasas"][0]["vigente"])

    def test_nueva_tasa_tras_baja_continua_versionado(self):
        tasa = self.crear_tasa_vigente()
        self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7250",
                "venta": "7350",
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["tasa"]["version"], 2)
        self.assertEqual(TasaComercial.objects.filter(vigente=True).count(), 1)
