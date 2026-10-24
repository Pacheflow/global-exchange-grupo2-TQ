"""HU-27: revisión previa y confirmación de método, sin edición posterior."""
from io import StringIO
from unittest import mock
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from metodos_pago.models import MetodoPago
from pagos.models import Pago
from usuarios.services.keycloak import SESSION_ROLES, SESSION_USUARIO
from .tests import BaseOperacionesTests
from . import test_guillermo as interfaz
from .models import CambioMetodoPago, Transaccion


class SeleccionMetodoTests(BaseOperacionesTests):
    """Protege el contrato público de revisión, sin proveedores externos."""

    def setUp(self):
        """Prepara sesión autorizada y alternativa para la revisión."""
        super().setUp()
        interfaz.FlujosGuillermoTests.autenticar(self)
        self.otro = MetodoPago.objects.create(nombre="Otra opción", naturaleza="EFECTIVO")
        self.url = reverse("operaciones:crear_transaccion")

    def revision(self, tipo="COMPRA"):
        """Previsualiza el método inicial con firma económica, sin registrar una operación."""
        datos = self.parametros_preview(tipo=tipo)
        respuesta = self.client.post(reverse("operaciones:previsualizar_operacion"), datos, content_type="application/json")
        self.assertEqual(respuesta.status_code, 200)
        preview = respuesta.json()
        return {**datos, "clave_idempotencia": self.clave_idempotencia(),
                "version_preview": preview["tasa_comercial"]["version"], "tasa_preview": preview["tasa"],
                "categoria_preview_id": preview["categoria_preview_id"],
                "porcentaje_comision_preview": preview["porcentaje_comision"], "firma_preview": preview["firma_preview"]}

    def confirmar(self, datos):
        """Confirma por HTTP sin omitir la autorización del servidor."""
        return self.client.post(self.url, datos, content_type="application/json")

    def test_compra_venta_guardan_eleccion_sin_edicion_posterior(self):
        """Cambiar el método inicial en resumen guarda el final una vez, sin cambiar preferencia ni economía."""
        self.cliente.metodo_pago_preferido = self.metodo_activo
        self.cliente.save(update_fields=["metodo_pago_preferido"])
        with mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as proveedor:
            for tipo in ("COMPRA", "VENTA"):
                datos = self.revision(tipo)
                originales = self.previsualizar(tipo=tipo)
                self.assertFalse(Transaccion.objects.filter(clave_idempotencia=datos["clave_idempotencia"]).exists())
                datos["metodo_pago_id"] = self.otro.pk
                nueva = self.confirmar(datos)
                self.assertEqual(nueva.status_code, 201, nueva.content)
                repetida = self.confirmar(datos)
                self.assertEqual(repetida.status_code, 200)
                self.assertTrue(repetida.json()["repetida"])
                tx = Transaccion.objects.get(pk=nueva.json()["transaccion"]["id"])
                self.assertEqual(tx.metodo_pago_id, self.otro.pk)
                self.assertEqual(tx.metodo_pago_nombre, self.otro.nombre)
                for campo in ("monto_origen", "monto_destino", "importe_comision", "porcentaje_comision"):
                    self.assertEqual(getattr(tx, campo), getattr(originales, campo))
                self.assertEqual(tx.tasa_aplicada, originales.tasa)
                self.assertEqual(tx.creado_por_keycloak_id, self.usuario_id)
                self.assertIsNotNone(tx.fecha_creacion)
                datos["metodo_pago_id"] = self.metodo_activo.pk
                self.assertEqual(self.confirmar(datos).status_code, 400)
                tx.refresh_from_db()
                self.assertEqual(tx.metodo_pago_id, self.otro.pk)
                detalle = self.client.get(reverse("operaciones:detalle_transaccion", args=[tx.pk]))
                self.assertEqual(detalle.json()["transaccion"]["metodo_pago"]["nombre"], self.otro.nombre)
                self.assertEqual(self.client.post(f"/api/operaciones/{tx.pk}/metodo-pago/", {}).status_code, 404)
            proveedor.assert_not_called()
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.metodo_pago_preferido_id, self.metodo_activo.pk)
        self.assertEqual(Transaccion.objects.count(), 2)
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(CambioMetodoPago.objects.exists())

    def test_inactivo_catalogo_vacio_y_condiciones_originales(self):
        """Desactivar rechaza sin registros; releer catálogo no renueva las condiciones firmadas."""
        datos = self.revision()
        self.otro.desactivar()
        datos["metodo_pago_id"] = self.otro.pk
        respuesta = self.confirmar(datos)
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["codigo"], "METODO_NO_DISPONIBLE")
        self.metodo_activo.desactivar()
        catalogo = self.client.get(reverse("operaciones:metodos_pago_operacion")).json()
        self.assertEqual(catalogo["metodos_pago"], [])
        self.assertIsNone(catalogo["metodo_pago_preferido"])
        self.assertFalse(Transaccion.objects.exists())
        self.metodo_activo.activar()
        datos["metodo_pago_id"] = self.metodo_activo.pk
        self.actualizar_cotizacion()
        self.assertEqual(self.confirmar(datos).status_code, 400)
        self.assertFalse(Transaccion.objects.exists())

    def test_firma_permisos_y_csrf_rechazan_sin_operacion(self):
        """Firmas ajenas/manipuladas, cliente, roles, asociación y CSRF rechazan sin crear operaciones."""
        datos = {**self.revision(), "metodo_pago_id": self.otro.pk}
        for cambio in ({"firma_preview": ""}, {"firma_preview": {}}, {"monto": "1"}, {"version_preview": 99},
                       {"tasa_preview": "1"}, {"moneda_destino_id": self.usd.pk},
                       {"porcentaje_comision_preview": "0"}, {"cliente_id": self.cliente.pk + 100}):
            with self.subTest(cambio=cambio):
                respuesta = self.confirmar({**datos, **cambio})
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.json()["codigo"], "PREVIEW_INVALIDA")
        estricto = Client(enforce_csrf_checks=True)
        estricto.cookies = self.client.cookies
        self.assertEqual(estricto.post(self.url, datos, content_type="application/json").status_code, 403)
        for roles in (["CAJERO"], ["ADMINISTRADOR", "USUARIO"], ["ANALISTA_CAMBIARIO", "USUARIO"]):
            sesion = self.client.session
            sesion[SESSION_ROLES] = roles
            sesion.save()
            self.assertEqual(self.confirmar(datos).status_code, 403)
        interfaz.FlujosGuillermoTests.autenticar(self)
        sesion = self.client.session
        sesion[SESSION_USUARIO] = {"sub": "otra-identidad", "username": "otro"}
        sesion.save()
        self.assertEqual(self.confirmar(datos).json()["codigo"], "PREVIEW_INVALIDA")
        interfaz.FlujosGuillermoTests.autenticar(self)
        sesion = self.client.session
        sesion.pop("selected_client")
        sesion.save()
        self.assertEqual(self.confirmar(datos).status_code, 400)
        interfaz.FlujosGuillermoTests.autenticar(self)
        self.asociacion.rol_en_cliente = "CONSULTA"
        self.asociacion.save()
        self.assertEqual(self.confirmar(datos).status_code, 400)
        self.asociacion.activo = False
        self.asociacion.save()
        self.assertEqual(self.confirmar(datos).status_code, 400)
        self.assertFalse(Transaccion.objects.exists())

    def test_clasificacion_explicita_no_cambia_actividad(self):
        """El comando revisa por defecto; aplicar clasifica sin inferir nombres ni habilitar."""
        nuevo = MetodoPago.objects.create(nombre="Nombre sin significado", activo=False)
        salida = StringIO()
        call_command("clasificar_metodos_pago", asignacion=[f"{nuevo.pk}=ELECTRONICO"], stdout=salida)
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.naturaleza, "SIN_CLASIFICAR")
        self.assertIn("Solo revisión", salida.getvalue())
        call_command("clasificar_metodos_pago", asignacion=[f"{nuevo.pk}=ELECTRONICO"], aplicar=True, stdout=StringIO())
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.naturaleza, "ELECTRONICO")
        self.assertFalse(nuevo.activo)
