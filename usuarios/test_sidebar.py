"""El sidebar marca una sola entrada según la ruta resuelta por Django."""

import re

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse


class SidebarActivoTests(SimpleTestCase):
    def comprobar_activo(self, ruta, etiqueta, *, rol="administrador", args=None):
        request = RequestFactory().get(reverse(ruta, args=args))
        request.resolver_match = resolve(request.path)
        html = render_to_string("frontend/partials/sidebar.html", {
            "request": request, "rol": rol, "rol_label": rol,
        })
        enlaces = re.findall(
            r'<a\b([^>]*)>.*?<span class="ge-frontend-nav-label">(.*?)</span></a>',
            html, flags=re.S)
        activos = [(atributos, texto) for atributos, texto in enlaces
                   if 'class="is-active"' in atributos]
        self.assertEqual([texto for _, texto in activos], [etiqueta])
        if etiqueta != "Fondos":  # Preserva el marcado existente de esa entrada.
            self.assertIn('aria-current="page"', activos[0][0])
        self.assertEqual(sum('aria-current="page"' in atributos
                             for atributos, _ in enlaces), 0 if etiqueta == "Fondos" else 1)

    def test_operaciones_solo_activa_operaciones(self):
        self.comprobar_activo("operaciones_web:inicio", "Operaciones")

    def test_reporte_solo_activa_transacciones(self):
        self.comprobar_activo("operaciones_web:reporte_administrativo_transacciones", "Transacciones")

    def test_detalle_reporte_solo_activa_transacciones(self):
        self.comprobar_activo("operaciones_web:detalle_reporte_transaccion", "Transacciones", args=[123])

    def test_otras_entradas_administrativas_se_conservan(self):
        for ruta, etiqueta in (("usuarios:dashboard", "Dashboard"),
                               ("usuarios:list", "Usuarios"),
                               ("consultar_clientes", "Clientes"),
                               ("usuarios:monedas", "Monedas"),
                               ("usuarios:tasas", "Tasas"),
                               ("usuarios:pagos", "Métodos de pago"),
                               ("cajas:inicio", "Cajas"),
                               ("fondos:inicio", "Fondos")):
            with self.subTest(ruta=ruta):
                self.comprobar_activo(ruta, etiqueta)

    def test_paneles_de_otros_roles_conservan_seleccion(self):
        for rol in ("analista", "cajero", "usuario"):
            with self.subTest(rol=rol):
                self.comprobar_activo("usuarios:dashboard", "Resumen", rol=rol)
        self.comprobar_activo("operaciones_web:inicio", "Operaciones", rol="cajero")

    def test_historico_de_tasas_se_conserva_al_integrar_el_dashboard(self):
        """El menú de Axel mantiene el acceso a HU-18 para los cuatro roles."""
        for rol in ("administrador", "analista", "cajero", "usuario"):
            with self.subTest(rol=rol):
                self.comprobar_activo("tasas_web:historico", "Histórico de tasas", rol=rol)

    def test_notificaciones_no_activa_el_historico_de_tasas(self):
        """Las dos pantallas comparten namespace, pero tienen selecciones distintas."""
        self.comprobar_activo("tasas_web:configurar_notificaciones", "Notificaciones de tasas")
