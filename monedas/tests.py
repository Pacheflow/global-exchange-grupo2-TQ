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
    """Pruebas esenciales del catálogo de monedas administrado por el rol ADMINISTRADOR.

    Requisito relacionado: HU-36 / RF-25.
    """

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
        """Comprueba que únicamente los administradores puedan gestionar las monedas.

        Se espera que un usuario sin ese rol reciba acceso denegado (403).

        Requisito relacionado: RNF-02.
        """
        self.autenticar(["USUARIO"])
        response = self.client.get("/api/monedas/")
        self.assertEqual(response.status_code, 403)

    def test_administrador_crea_moneda_y_normaliza_codigo(self):
        """Comprueba que un administrador pueda registrar una moneda válida.

        Se espera que el código se normalice a mayúsculas sin espacios externos.
        """
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
        """Comprueba que el código de una moneda sea único sin distinguir mayúsculas.

        Se espera que la creación de una moneda con código duplicado sea rechazada
        con conflicto (409).
        """
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
        """Comprueba que no se permita registrar una moneda con datos obligatorios vacíos.

        Se espera que la solicitud sea rechazada (400) y no se cree la moneda.
        """
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
        """Comprueba que un administrador pueda editar los datos de una moneda.

        Se espera que los cambios se persistan correctamente.
        """
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
        """Comprueba que una moneda pueda desactivarse y reactivarse sin eliminar su registro.

        Se espera que el cambio de estado se refleje y que la moneda persista.
        """
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
        """Comprueba que el catálogo público exponga únicamente las monedas activas.

        Se espera que las monedas inactivas no aparezcan y que la respuesta incluya
        los campos necesarios para consulta y simulación.
        """
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
