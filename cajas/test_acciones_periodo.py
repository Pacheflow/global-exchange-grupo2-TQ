"""Elegibilidad informativa y descubribilidad de acciones del período."""
import time

from django.test import TestCase
from django.template.loader import render_to_string
from django.urls import reverse

from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)
from monedas.models import Moneda
from .models import Caja, PeriodoCaja, SaldoInicialCaja
from .presentacion import contexto_acciones_periodo
from .services import realizar_arqueo, registrar_movimiento_manual


class AccionesPeriodoTests(TestCase):
    def setUp(self):
        self.caja = Caja.objects.create(codigo="ACCIONES", nombre="Caja acciones",
            creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin")
        self.periodo = PeriodoCaja.objects.create(caja=self.caja, responsable_keycloak_id="cajero")
        self.moneda, _ = Moneda.objects.get_or_create(codigo="USD",
            defaults={"nombre": "Dólar", "simbolo": "$"})
        SaldoInicialCaja.objects.create(periodo=self.periodo, moneda=self.moneda, monto="100")
        self.identidad = {"usuario_id": "cajero", "roles": ["CAJERO"]}
        self.autenticar("CAJERO")

    def autenticar(self, rol):
        sesion = self.client.session
        sesion.update({SESSION_AUTENTICADO: True, SESSION_EXPIRA_EN: time.time()+3600,
                       SESSION_ROLES: [rol], SESSION_USUARIO: {"sub": "cajero"}})
        sesion["kc_user"] = {"sub": "cajero", "preferred_username": "cajero"}
        sesion.save()

    def arqueo(self):
        return realizar_arqueo(periodo_id=self.periodo.pk,
            saldos_fisicos=[{"moneda_id": self.moneda.pk, "monto": "100"}], **self.identidad)

    def test_abierto_sin_arqueo_acciones_consistentes_en_cuatro_pantallas(self):
        for ruta in ("usuarios:dashboard", "cajas:saldos", "cajas:movimientos", "cajas:saldo"):
            with self.subTest(ruta=ruta):
                url = reverse(ruta, args=[self.periodo.pk]) if ruta == "cajas:saldo" else reverse(ruta)
                respuesta = self.client.get(url, {"periodo_id": self.periodo.pk})
                self.assertContains(respuesta, "Acciones de Caja")
                self.assertContains(respuesta, "Realizar arqueo")
                self.assertContains(respuesta, "Realizá primero un arqueo válido.")
                self.assertContains(respuesta, 'disabled aria-describedby="motivo-no-cierre-')
                self.assertNotContains(respuesta, reverse("cajas:cierre", args=[self.periodo.pk]))
                html = respuesta.content.decode()
                self.assertLess(html.index('aria-label="Contexto de Caja'), html.index('aria-label="Acciones de Caja'))

    def test_arqueo_vigente_habilita_cierre(self):
        self.arqueo()
        self.assertEqual(contexto_acciones_periodo(self.periodo), {"puede_cerrar": True, "motivo_no_cierre": ""})
        respuesta = self.client.get(reverse("cajas:saldos"), {"periodo_id": self.periodo.pk})
        self.assertContains(respuesta, reverse("cajas:cierre", args=[self.periodo.pk]))
        self.assertNotContains(respuesta, 'disabled aria-describedby="motivo-no-cierre-')

    def test_movimiento_posterior_desactiva_cierre_con_explicacion(self):
        self.arqueo()
        registrar_movimiento_manual(periodo_id=self.periodo.pk, moneda_id=self.moneda.pk,
            tipo="INGRESO", monto="1", motivo="Movimiento posterior", **self.identidad)
        respuesta = self.client.get(reverse("cajas:movimientos"), {"periodo_id": self.periodo.pk})
        self.assertContains(respuesta, "Existen movimientos posteriores al último arqueo.")
        self.assertContains(respuesta, "Volvé a realizar el arqueo antes de cerrar.")
        self.assertFalse(respuesta.context["puede_cerrar"])

    def test_cerrado_y_otros_roles_no_obtienen_acciones(self):
        self.periodo.estado = "CERRADO"
        self.assertFalse(contexto_acciones_periodo(self.periodo)["puede_cerrar"])
        html = render_to_string("frontend/partials/caja_acciones_periodo.html",
            {"periodo": self.periodo, "kc_rol_efectivo": "CAJERO", "puede_cerrar": True})
        self.assertNotIn("Acciones de Caja", html)
        self.periodo.estado = "ABIERTO"
        for rol in ("ADMINISTRADOR", "USUARIO"):
            html = render_to_string("frontend/partials/caja_acciones_periodo.html",
                {"periodo": self.periodo, "kc_rol_efectivo": rol, "puede_cerrar": True})
            self.assertNotIn("Realizar arqueo", html)
            self.assertNotIn("Cerrar caja", html)
        self.autenticar("ADMINISTRADOR")
        self.assertNotContains(self.client.get(reverse("cajas:saldos"),
            {"periodo_id": self.periodo.pk}), "Acciones de Caja")

    def test_historiales_identificados_y_acceso_ver_periodo(self):
        self.assertContains(self.client.get(reverse("operaciones_web:historial")),
            "COMPRA y VENTA completadas o canceladas")
        for url in (reverse("cajas:historial_selector"), reverse("cajas:historial", args=[self.caja.pk])):
            self.assertContains(self.client.get(url), "Períodos, movimientos, arqueos y cierres")
        respuesta = self.client.get(reverse("cajas:operar"))
        self.assertContains(respuesta, "Ver período")
        self.assertContains(respuesta, reverse("cajas:saldo", args=[self.periodo.pk]))
