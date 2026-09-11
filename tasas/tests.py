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
        Moneda.objects.all().delete()
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

    def crear_tasa_vigente(self):
        """Crea mediante la API la tasa base usada en pruebas de baja."""
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

    def test_administrador_no_puede_crear_ni_modificar_tasa(self):
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

    def test_administrador_puede_consultar_el_historial_sin_modificar_tasas(self):
        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.get(
            reverse("tasas:historial_tasas_comerciales")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["monedas"][0]["codigo"], "PYG")
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

        historial = self.client.get(
            reverse("tasas:historial_tasas_comerciales")
        )
        self.assertEqual(historial.status_code, 200)
        self.assertEqual(len(historial.json()["tasas"]), 1)
        self.assertTrue(historial.json()["tasas"][0]["vigente"])

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
        versiones = response.json()["tasas"]
        self.assertEqual([tasa["version"] for tasa in versiones], [2, 1])
        self.assertEqual([tasa["vigente"] for tasa in versiones], [True, False])
        self.assertEqual(
            {tasa["usuario_username"] for tasa in versiones},
            {"analista.prueba"},
        )

    def test_no_existe_eliminacion_de_tasas_comerciales(self):
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])
        self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(TasaComercial.objects.count(), 1)

    def test_endpoint_de_referencia_no_acepta_edicion_manual(self):
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

        response = self.client.post(reverse("tasas:consultar"), {})

        self.assertEqual(response.status_code, 405)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_analista_puede_desactivar_tasa_comercial(self):
        tasa = self.crear_tasa_vigente()

        response = self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["tasa"]["vigente"])
        tasa.refresh_from_db()
        self.assertFalse(tasa.vigente)

    def test_administrador_no_puede_desactivar_tasa_comercial(self):
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

    def test_tasa_desactivada_permanece_en_historial(self):
        tasa = self.crear_tasa_vigente()
        self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        response = self.client.get(
            reverse("tasas:historial_tasas_comerciales"),
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["tasas"]), 1)
        self.assertEqual(response.json()["tasas"][0]["id"], tasa.id)
        self.assertFalse(response.json()["tasas"][0]["vigente"])

    def test_desactivacion_no_elimina_fisicamente_el_registro(self):
        tasa = self.crear_tasa_vigente()

        self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(TasaComercial.objects.count(), 1)
        self.assertTrue(TasaComercial.objects.filter(pk=tasa.id).exists())
        self.assertFalse(TasaComercial.objects.get(pk=tasa.id).vigente)

    def test_nueva_tasa_tras_baja_reanuda_versionado_del_par(self):
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
        self.assertEqual(TasaComercial.objects.count(), 2)
        self.assertEqual(response.json()["tasa"]["version"], 2)
        self.assertEqual(TasaComercial.objects.filter(vigente=True).count(), 1)
        self.assertFalse(TasaComercial.objects.get(pk=tasa.id).vigente)
