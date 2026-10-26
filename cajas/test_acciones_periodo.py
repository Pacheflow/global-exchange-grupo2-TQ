"""Elegibilidad informativa y descubribilidad de acciones del período."""
import time

from django.test import TestCase
from django.template.loader import render_to_string
from django.urls import reverse

from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)
from monedas.models import Moneda
from .models import Caja, CierreCaja, PeriodoCaja, SaldoInicialCaja
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
        """Las cuatro pantallas permiten intentar cerrar; sin arqueo, GET/POST redirigen con alerta única sin cierre."""
        for ruta in ("usuarios:dashboard", "cajas:saldos", "cajas:movimientos", "cajas:saldo"):
            with self.subTest(ruta=ruta):
                url = reverse(ruta, args=[self.periodo.pk]) if ruta == "cajas:saldo" else reverse(ruta)
                respuesta = self.client.get(url, {"periodo_id": self.periodo.pk})
                self.assertContains(respuesta, "Acciones de Caja")
                self.assertContains(respuesta, "Realizar arqueo")
                self.assertContains(respuesta, "Realizá primero un arqueo válido.")
                self.assertNotContains(respuesta, 'disabled aria-describedby="motivo-no-cierre-')
                self.assertContains(respuesta, reverse("cajas:cierre", args=[self.periodo.pk]))
                html = respuesta.content.decode()
                self.assertLess(html.index('aria-label="Contexto de Caja'), html.index('aria-label="Acciones de Caja'))
        url = reverse("cajas:cierre", args=[self.periodo.pk])
        destino = reverse("cajas:saldo", args=[self.periodo.pk])
        aviso = "Debes realizar un arqueo antes de cerrar la caja."
        for metodo in (self.client.get, self.client.post):
            respuesta = metodo(url, follow=True)
            self.assertEqual(respuesta.redirect_chain, [(destino, 302)])
            self.assertContains(respuesta, '<div class="message error">' + aviso + '</div>', count=1)
            self.assertContains(respuesta, '/static/js/app.js')
            self.assertNotContains(self.client.get(destino), aviso)
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.estado, "ABIERTO")
        self.assertFalse(CierreCaja.objects.exists())

    def test_arqueo_vigente_habilita_cierre(self):
        """Un arqueo vigente permite revisar y cerrar mediante POST, mostrando éxito por GET sin repetir el cierre."""
        self.arqueo()
        self.assertEqual(contexto_acciones_periodo(self.periodo), {"puede_cerrar": True, "motivo_no_cierre": ""})
        respuesta = self.client.get(reverse("cajas:saldos"), {"periodo_id": self.periodo.pk})
        self.assertContains(respuesta, reverse("cajas:cierre", args=[self.periodo.pk]))
        self.assertNotContains(respuesta, 'disabled aria-describedby="motivo-no-cierre-')
        url = reverse("cajas:cierre", args=[self.periodo.pk])
        self.assertContains(self.client.get(url), "Confirmar cierre")
        respuesta = self.client.post(url, follow=True)
        destino = reverse("cajas:historial", args=[self.caja.pk])
        self.assertEqual(respuesta.redirect_chain, [(destino, 302)])
        self.assertContains(respuesta, "Caja cerrada correctamente.", count=1)
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.estado, "CERRADO")
        self.assertEqual(CierreCaja.objects.filter(periodo=self.periodo).count(), 1)
        self.assertNotContains(self.client.get(destino), "Caja cerrada correctamente.")

    def test_movimiento_posterior_rechaza_cierre_con_aviso_visible(self):
        """Un movimiento tras ver el cierre invalida el arqueo: POST/GET avisan una vez y conservan el período abierto."""
        self.arqueo()
        url = reverse("cajas:cierre", args=[self.periodo.pk])
        self.assertContains(self.client.get(url), "Confirmar cierre")
        registrar_movimiento_manual(periodo_id=self.periodo.pk, moneda_id=self.moneda.pk,
            tipo="INGRESO", monto="1", motivo="Movimiento posterior", **self.identidad)
        respuesta = self.client.get(reverse("cajas:movimientos"), {"periodo_id": self.periodo.pk})
        self.assertContains(respuesta, "Existen movimientos posteriores al último arqueo.")
        self.assertContains(respuesta, "Volvé a realizar el arqueo antes de cerrar.")
        self.assertFalse(respuesta.context["puede_cerrar"])
        aviso = "La caja tiene movimientos posteriores al último arqueo. Realiza un nuevo arqueo antes de cerrarla."
        destino = reverse("cajas:saldo", args=[self.periodo.pk])
        for metodo in (self.client.post, self.client.get):
            respuesta = metodo(url, follow=True)
            self.assertEqual(respuesta.redirect_chain, [(destino, 302)])
            self.assertContains(respuesta, '<div class="message error">' + aviso + '</div>', count=1)
            self.assertNotContains(self.client.get(destino), aviso)
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.estado, "ABIERTO")
        self.assertFalse(CierreCaja.objects.exists())

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
