import json
import time

from django.test import TestCase

from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import Moneda


class MonedaCatalogoEsencialTests(TestCase):
    def setUp(self):
        Moneda.objects.all().delete()

    def autenticar(self, roles=None):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-prueba-001",
            "preferred_username": "admin.prueba",
        }
        session[SESSION_ROLES] = roles or ["ADMINISTRADOR"]
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session.save()

    def test_usuario_no_administrador_no_puede_gestionar_monedas(self):
        self.autenticar(["USUARIO"])
        response = self.client.get("/api/monedas/")
        self.assertEqual(response.status_code, 403)

    def test_administrador_crea_moneda_y_normaliza_codigo(self):
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
        self.assertEqual(moneda.nombre, "Dólar estadounidense")
        self.assertEqual(moneda.simbolo, "$")
        self.assertEqual(moneda.estado, "ACTIVA")

    def test_no_permite_codigo_duplicado(self):
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

    def test_rechaza_datos_obligatorios_vacios(self):
        self.autenticar()
        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {"codigo": "", "nombre": "", "simbolo": "", "estado": "ACTIVA"}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Moneda.objects.exists())

    def test_administrador_edita_moneda(self):
        self.autenticar()
        moneda = Moneda.objects.create(
            codigo="USD", nombre="Dólar", simbolo="$", estado="ACTIVA"
        )
        response = self.client.post(
            f"/api/monedas/{moneda.id}/editar/",
            data=json.dumps(
                {"codigo": "EUR", "nombre": "Euro", "simbolo": "€", "estado": "ACTIVA"}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        moneda.refresh_from_db()
        self.assertEqual(moneda.codigo, "EUR")
        self.assertEqual(moneda.nombre, "Euro")
        self.assertEqual(moneda.simbolo, "€")

    def test_administrador_desactiva_y_reactiva_sin_eliminar(self):
        self.autenticar()
        moneda = Moneda.objects.create(
            codigo="USD", nombre="Dólar", simbolo="$", estado="ACTIVA"
        )
        url = f"/api/monedas/{moneda.id}/estado/"
        desactivar = self.client.post(
            url,
            data=json.dumps({"estado": "INACTIVA"}),
            content_type="application/json",
        )
        moneda.refresh_from_db()
        self.assertEqual(desactivar.status_code, 200)
        self.assertEqual(moneda.estado, "INACTIVA")
        self.assertTrue(Moneda.objects.filter(pk=moneda.pk).exists())

        reactivar = self.client.post(
            url,
            data=json.dumps({"estado": "ACTIVA"}),
            content_type="application/json",
        )
        moneda.refresh_from_db()
        self.assertEqual(reactivar.status_code, 200)
        self.assertEqual(moneda.estado, "ACTIVA")

    def test_catalogo_publico_devuelve_solo_monedas_activas(self):
        Moneda.objects.create(
            codigo="PYG", nombre="Guaraní", simbolo="Gs.", estado="ACTIVA"
        )
        Moneda.objects.create(
            codigo="BRL", nombre="Real brasileño", simbolo="R$", estado="INACTIVA"
        )
        response = self.client.get("/api/monedas/activas/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["monedas"]), 1)
        moneda = response.json()["monedas"][0]
        self.assertEqual(moneda["codigo"], "PYG")
        self.assertEqual(
            set(moneda), {"id", "codigo", "nombre", "simbolo", "estado"}
        )
