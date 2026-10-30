"""Menú e historial del usuario y contrato del formulario de efectivo."""
from django.urls import reverse

from clientes.models import Cliente
from metodos_pago.models import MetodoPago
from usuarios.services.keycloak import SESSION_ROLES
from . import test_guillermo as interfaz
from . import tests as escenarios


class InterfazFlujosTests(escenarios.BaseOperacionesTests):
    """Reutiliza fixtures y servicios reales; no modifica permisos ni contabilidad."""

    def setUp(self):
        super().setUp()
        interfaz.FlujosGuillermoTests.autenticar(self)

    def test_menu_usuario_simplificado_y_historial_sin_formulario(self):
        pagina = self.client.get(reverse("operaciones_web:historial"))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, '<span class="ge-frontend-nav-label">Historial</span>', html=True)
        for etiqueta in ("Pagos", "Notificaciones", "Configuración"):
            self.assertNotContains(pagina, f'<span class="ge-frontend-nav-label">{etiqueta}</span>', html=True)
        self.assertNotContains(pagina, "data-operation-form")
        self.assertNotContains(pagina, 'data-history-limit="5"')
        self.assertContains(pagina, "Método de pago")

    def test_operaciones_recientes_e_historial_completo_respetan_cliente(self):
        propias = [escenarios.HistorialTransaccionesTests._transaccion_manual(self, self.cliente) for _ in range(7)]
        ajeno = Cliente.objects.create(nombre_razon_social="No autorizado", tipo_persona="FISICA", documento="99988", estado="ACTIVO", categoria=self.categoria)
        oculta = escenarios.HistorialTransaccionesTests._transaccion_manual(self, ajeno)
        pagina = self.client.get(reverse("operaciones_web:inicio"))
        self.assertContains(pagina, "Últimas operaciones")
        self.assertContains(pagina, "Ver historial completo")
        self.assertContains(pagina, 'data-history-limit="5"')
        self.assertContains(pagina, "data-operation-form")
        endpoint = reverse("operaciones:historial_transacciones")
        recientes = self.client.get(endpoint, {"recientes": "5"}).json()["transacciones"]
        historial = self.client.get(endpoint).json()["transacciones"]
        self.assertEqual([tx["id"] for tx in recientes], [tx.pk for tx in reversed(propias[-5:])])
        self.assertEqual(len(historial), 7)
        self.assertNotIn(oculta.pk, [tx["id"] for tx in historial])
        self.assertEqual(self.client.get(reverse("operaciones:detalle_transaccion", args=[oculta.pk])).status_code, 404)

    def test_historial_no_amplia_roles_y_conserva_cajero(self):
        session = self.client.session
        session[SESSION_ROLES] = ["CAJERO"]
        session.save()
        pagina = self.client.get(reverse("operaciones_web:historial"))
        self.assertContains(pagina, "Consulta de solo lectura")
        self.assertContains(pagina, 'data-history-url="' + reverse("operaciones:historial_transacciones") + '?vista=historial"')
        self.assertNotContains(pagina, "data-operation-form")
        session[SESSION_ROLES] = ["ANALISTA_CAMBIARIO"]
        session.save()
        self.assertEqual(self.client.get(reverse("operaciones_web:historial")).status_code, 403)

    def test_catalogo_cajero_solo_efectivo_activo_y_preview_real(self):
        efectivo = MetodoPago.objects.create(nombre="Efectivo QA", naturaleza="EFECTIVO", activo=True)
        MetodoPago.objects.create(nombre="Efectivo inactivo QA", naturaleza="EFECTIVO", activo=False)
        session = self.client.session
        session[SESSION_ROLES] = ["CAJERO"]
        session.save()
        endpoint = reverse("operaciones:metodos_presenciales")
        catalogo = self.client.get(endpoint).json()
        self.assertEqual([metodo["id"] for metodo in catalogo["metodos_pago"]], [efectivo.pk])
        self.assertEqual(catalogo["metodo_pago_preferido"]["id"], efectivo.pk)
        datos = self.parametros_preview(metodo_pago_id=efectivo.pk)
        preview = self.client.post(reverse("operaciones:preview_presencial"), datos, content_type="application/json")
        self.assertEqual(preview.status_code, 200, preview.content)
        datos["metodo_pago_id"] = self.metodo_activo.pk
        self.assertEqual(self.client.post(reverse("operaciones:preview_presencial"), datos, content_type="application/json").status_code, 400)
        otro = MetodoPago.objects.create(nombre="Otra ventanilla QA", naturaleza="EFECTIVO", activo=True)
        self.assertIsNone(self.client.get(endpoint).json()["metodo_pago_preferido"])
        MetodoPago.objects.filter(pk__in=[efectivo.pk, otro.pk]).update(activo=False)
        self.assertEqual(self.client.get(endpoint).json()["metodos_pago"], [])
