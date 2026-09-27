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
    """Pruebas de administración de tasas comerciales de compra y venta.

    Requisito relacionado: HU-21 / RF-23 (RN3).
    """

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
        """Comprueba que el administrador no pueda registrar tasas comerciales.

        Se espera que la solicitud sea rechazada (403) y no se cree ninguna tasa.

        Requisito relacionado: RF-23 (RN3).
        """
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
        """Comprueba que el analista cambiario pueda registrar una tasa comercial.

        Se espera que la tasa se cree conservando el usuario responsable y la fecha
        de registro.

        Requisito relacionado: RF-23 (RN3) / RNF-08.
        """
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
        """Comprueba que no se permita registrar una tasa de compra no positiva.

        Se espera que la solicitud sea rechazada (400) y no se registre ninguna tasa.
        """
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
        """Comprueba que no se permita usar una moneda inactiva en una tasa comercial.

        Se espera que la solicitud sea rechazada (400) y no se registre ninguna tasa.
        """
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
        """Comprueba que no se permita registrar una tasa entre la misma moneda.

        Se espera que la solicitud sea rechazada (400) y no se registre ninguna tasa.
        """
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
        """Comprueba que la primera tasa de un par exija valores de compra y venta.

        Se espera que la tasa incompleta sea rechazada (400) y no se registre ninguna.
        """
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
        """Comprueba que modificar una tasa comercial genere una nueva versión.

        Se espera que la versión nueva quede vigente y la anterior permanezca en el historial.

        Requisito relacionado: RF-08.
        """
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
        """Comprueba que una modificación inválida no rompa la tasa vigente.

        Se espera que la solicitud sea rechazada (400) y la tasa anterior continúe vigente.
        """
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
        """Comprueba que el historial presente las versiones de una tasa en orden descendente.

        Se espera que la versión más reciente aparezca primero.

        Requisito relacionado: RF-08.
        """
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
        """Comprueba que el administrador no pueda desactivar tasas comerciales.

        Se espera que la solicitud sea rechazada (403) y la tasa continúe vigente.

        Requisito relacionado: RNF-02.
        """
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
        """Comprueba que el analista pueda desactivar una tasa sin eliminar su historial.

        Se espera que la tasa deje de estar vigente pero siga visible en el historial.
        """
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
        """Comprueba que el versionado continúe después de desactivar una tasa.

        Se espera que la nueva tasa use la versión siguiente y que solo una tasa del
        par quede vigente.
        """
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
