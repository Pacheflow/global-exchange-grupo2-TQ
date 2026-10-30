"""Facturas web: errores externos, aislamiento financiero, permisos e idempotencia."""
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event
from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente, UsuarioCliente
from fondos.models import OperacionCompletada
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from operaciones.models import Transaccion
from tasas.models import TasaComercial
from usuarios.services.keycloak import SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO
from .models import Factura, EnvioFactura
from .services.factura_segura import ArchivoFactura, ResultadoGeneracion, FacturaSeguraResultadoIndeterminado, FacturaSeguraProveedorError, FacturaSeguraAutenticacionError
from .services.facturas import preparar_factura, emitir_factura


class EscenarioFactura:
    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(nombre_razon_social="Cliente facturas", documento="123456",
            tipo_persona="FISICA")
        self.asociacion = UsuarioCliente.objects.create(cliente=self.cliente, keycloak_user_id="usuario",
            username="usuario", rol_en_cliente="RESPONSABLE")
        usd, _ = Moneda.objects.get_or_create(codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"})
        pyg, _ = Moneda.objects.get_or_create(codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"})
        tasa = TasaComercial.objects.create(moneda_origen=usd, moneda_destino=pyg, compra=7000,
            venta=7100, usuario_id="admin", usuario_username="admin")
        metodo = MetodoPago.objects.create(nombre="Tarjeta factura", naturaleza="ELECTRONICO")
        self.op = Transaccion.objects.create(cliente=self.cliente, clave_idempotencia=str(uuid4()),
            creado_por_keycloak_id="usuario", tipo="COMPRA", moneda_origen=usd, moneda_destino=pyg,
            monto_origen=100, monto_destino=700000, tasa_comercial=tasa, tasa_aplicada=7000,
            porcentaje_comision=0, importe_comision=0, metodo_pago=metodo, metodo_pago_nombre=metodo.nombre,
            estado="COMPLETADA")
        self.factura = preparar_factura(self.op.pk)
        # Fixture de contrato, deliberadamente no exportado como JSON fiscal real.
        self.contrato = Mock()
        self.contrato.construir_de.return_value = {"prueba": "sin valor fiscal"}
        self.contrato.extraer_de_calculado.return_value = {"prueba": "calculada"}
        self.proveedor = Mock()
        self.proveedor.generar_de.return_value = ResultadoGeneracion(codigo=0, descripcion="OK",
            operacion_id="test-id", resultados=(), cdc="1" * 44)
        self.proveedor.descargar_kude.return_value = ArchivoFactura(b"%PDF-1.4\nprueba", "application/pdf", "kude.pdf")
        self.proveedor.descargar_xml.return_value = ArchivoFactura(b"<DE/>", "application/xml", "de.xml")

    def generar(self):
        self.factura = emitir_factura(self.factura.pk, contrato=self.contrato, client=self.proveedor)
        return self.factura

    def autenticar(self, cliente_http=None, usuario="usuario", rol="USUARIO"):
        cliente_http = cliente_http or self.client
        sesion = cliente_http.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = time.time() + 600
        sesion[SESSION_ROLES] = [rol]
        sesion[SESSION_USUARIO] = {"sub": usuario, "email": "sesion@example.test"}
        sesion.save()


@override_settings(FACTURACION_CONTRATO="")
class FacturaTests(EscenarioFactura, TestCase):
    def test_preparar_repetida_conserva_unica_factura_y_snapshot(self):
        self.cliente.nombre_razon_social = "Nombre modificado"
        self.cliente.save()
        repetida = preparar_factura(self.op.pk)
        self.assertEqual(repetida.pk, self.factura.pk)
        self.assertEqual(Factura.objects.count(), 1)
        self.assertEqual(repetida.datos_operacion["cliente"], "Cliente facturas")

    def test_solo_transacciones_completadas(self):
        self.op.estado = "PENDIENTE"
        self.op.save()
        with self.assertRaises(ValidationError):
            preparar_factura(self.op.pk)
        with self.assertRaises(ValidationError):
            self.generar()
        self.proveedor.generar_de.assert_not_called()

    def test_sin_contrato_no_emite_ni_inventa_datos(self):
        factura = emitir_factura(self.factura.pk, client=self.proveedor)
        self.assertEqual(factura.estado, "PENDIENTE")
        self.assertEqual(factura.codigo_error, "CONTRATO_FISCAL_PENDIENTE")
        self.proveedor.calcular_de.assert_not_called()

    def test_generacion_asocia_y_no_duplica(self):
        factura = self.generar()
        self.generar()
        self.assertEqual(factura.estado, "GENERADA")
        self.assertEqual(factura.cdc, "1" * 44)
        self.assertEqual(factura.intento.clave_idempotencia, f"factura:transaccion:{self.op.pk}:v1")
        self.proveedor.generar_de.assert_called_once()
        self.assertEqual(self.contrato.construir_de.call_args.args[0]["transaccion_id"], self.op.pk)

    def test_timeout_no_reemite_y_preserva_transaccion(self):
        self.proveedor.generar_de.side_effect = FacturaSeguraResultadoIndeterminado("timeout")
        self.assertEqual(self.generar().estado, "INDETERMINADA")
        self.generar()
        self.proveedor.generar_de.assert_called_once()
        self.op.refresh_from_db()
        self.assertEqual(self.op.estado, "COMPLETADA")

    def test_rechazo_registrado_sin_eliminar_transaccion(self):
        self.proveedor.generar_de.side_effect = FacturaSeguraProveedorError(codigo=-1,
            descripcion="Detalle privado", operacion_id="id-error")
        factura = self.generar()
        self.assertEqual(factura.estado, "ERROR")
        self.assertEqual(factura.intento.codigo_proveedor, -1)
        self.assertTrue(Transaccion.objects.filter(pk=self.op.pk, estado="COMPLETADA").exists())

    def test_error_calculo_registrado_sin_emitir(self):
        self.proveedor.calcular_de.side_effect = ValueError("detalle privado")
        with self.assertLogs("facturacion.services.facturas", level="ERROR") as logs:
            factura = self.generar()
        self.assertEqual(factura.estado, "ERROR")
        self.assertNotIn("detalle privado", str(logs.output))
        self.proveedor.generar_de.assert_not_called()

    def test_token_rechazado_registra_error_confirmado_sin_reemitir(self):
        self.proveedor.generar_de.side_effect = FacturaSeguraAutenticacionError("rechazado")
        with self.assertLogs("facturacion.services.facturas", level="ERROR"):
            factura = self.generar()
        self.assertEqual(factura.estado, "ERROR")
        self.assertEqual(factura.intento.estado, "ERROR")
        self.generar()
        self.proveedor.generar_de.assert_called_once()


    def test_preparacion_se_difiere_al_commit(self):
        with patch("facturacion.signals.preparar_despues_de_commit") as preparar:
            with self.captureOnCommitCallbacks(execute=True):
                OperacionCompletada.objects.create(operacion=self.op)
                preparar.assert_not_called()
            preparar.assert_called_once_with(self.op.pk)

    def test_rollback_no_programa_facturacion(self):
        with patch("facturacion.signals.preparar_despues_de_commit") as preparar:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    with transaction.atomic():
                        OperacionCompletada.objects.create(operacion=self.op)
                        raise ValueError("rollback")
                except ValueError:
                    pass
            preparar.assert_not_called()

    def test_preparacion_fallida_no_borra_operacion(self):
        with patch("facturacion.services.facturas.preparar_factura", side_effect=RuntimeError("fallo")):
            with self.assertLogs("facturacion.services.facturas", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    OperacionCompletada.objects.create(operacion=self.op)
        self.assertTrue(OperacionCompletada.objects.filter(operacion=self.op).exists())
        self.assertTrue(Transaccion.objects.filter(pk=self.op.pk, estado="COMPLETADA").exists())

    def test_procesador_recupera_evento_pendiente_sin_contrato(self):
        self.factura.delete()
        OperacionCompletada.objects.create(operacion=self.op)
        call_command("procesar_facturas", stdout=StringIO())
        recuperada = Factura.objects.get(transaccion=self.op)
        self.assertEqual(recuperada.estado, "PENDIENTE")
        self.assertEqual(recuperada.codigo_error, "CONTRATO_FISCAL_PENDIENTE")


class FacturaHTTPTests(EscenarioFactura, TestCase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_listado_y_detalle_accesibles_sin_emitir(self):
        self.assertContains(self.client.get(reverse("facturacion:listado")), "Consultar factura")
        self.assertContains(self.client.get(reverse("facturacion:detalle", args=[self.factura.pk])), "Pendiente de emisión")
        self.proveedor.generar_de.assert_not_called()

    def test_ajeno_o_desasociado_no_ve_factura_ni_descarga(self):
        for usuario in ("otro", "usuario"):
            self.autenticar(usuario=usuario)
            self.asociacion.activo = False
            self.asociacion.save()
            for nombre, args in (("detalle", [self.factura.pk]), ("visualizar", [self.factura.pk]),
                                  ("descargar", [self.factura.pk, "pdf"])):
                self.assertEqual(self.client.get(reverse(f"facturacion:{nombre}", args=args)).status_code, 404)
            self.assertNotContains(self.client.get(reverse("facturacion:listado")), "Consultar factura")

    def test_anonimo_y_rol_ajeno(self):
        self.client.session.flush()
        self.assertEqual(self.client.get(reverse("facturacion:listado")).status_code, 302)
        self.autenticar(rol="CAJERO")
        self.assertEqual(self.client.get(reverse("facturacion:listado")).status_code, 403)

    def test_solo_consulta_puede_leer(self):
        self.asociacion.rol_en_cliente = "CONSULTA"
        self.asociacion.save()
        self.assertEqual(self.client.get(reverse("facturacion:detalle", args=[self.factura.pk])).status_code, 200)

    def test_descarga_pdf_xml_y_visualizacion_privadas(self):
        self.generar()
        with patch("facturacion.services.facturas.obtener_factura_segura_client", return_value=self.proveedor):
            for formato in ("pdf", "xml"):
                response = self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, formato]))
                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response["Content-Disposition"])
                self.assertIn("no-store", response["Cache-Control"])
                self.assertTrue(b"".join(response.streaming_content))
            response = self.client.get(reverse("facturacion:visualizar", args=[self.factura.pk]))
            self.assertIn("inline", response["Content-Disposition"])
            self.assertTrue(b"".join(response.streaming_content))

    def test_descarga_pendiente_o_formato_desconocido_rechazados(self):
        self.assertEqual(self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, "pdf"])).status_code, 409)
        self.generar()
        self.assertEqual(self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, "exe"])).status_code, 409)

    def test_descarga_error_no_expone_detalle(self):
        self.generar()
        with patch("facturacion.services.facturas.obtener_factura_segura_client", side_effect=RuntimeError("secreto")):
            with self.assertLogs("facturacion.views", level="ERROR"):
                response = self.client.get(reverse("facturacion:visualizar", args=[self.factura.pk]))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"secreto", response.content)


    def test_facturas_solo_web_sin_acciones_de_correo(self):
        """La sección permite consultar y descargar sin ofrecer envío ni destino."""
        self.generar()
        for url in [reverse("facturacion:listado"), reverse("facturacion:detalle", args=[self.factura.pk])]:
            respuesta = self.client.get(url)
            self.assertNotContains(respuesta, "Enviar factura")
            self.assertNotContains(respuesta, "Configurar correo")
            self.assertNotContains(respuesta, "Envío por correo")
        detalle = self.client.get(reverse("facturacion:detalle", args=[self.factura.pk]))
        self.assertContains(detalle, "Descargar PDF")
        self.assertContains(detalle, "Descargar XML")
        self.assertContains(detalle, "Ver comprobante PDF")

    def test_endpoints_de_correo_retirados(self):
        """Las URLs anteriores no permiten enviar ni configurar correo."""
        for url in [f"/facturas/{self.factura.pk}/enviar/", f"/facturas/cliente/{self.cliente.pk}/correo/"]:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url).status_code, 404)

    def test_procesador_no_envia_correo_para_facturas_generadas(self):
        """Una factura generada queda disponible en web sin contactar SMTP."""
        self.generar()
        with patch("django.core.mail.mailers.create_connection") as smtp:
            call_command("procesar_facturas", stdout=StringIO())
        smtp.assert_not_called()
        self.assertFalse(EnvioFactura.objects.exists())
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, "GENERADA")


class FacturaConcurrenciaTests(EscenarioFactura, TransactionTestCase):
    def test_dos_emisiones_concurrentes_llaman_una_vez(self):
        entrando, continuar = Event(), Event()
        resultado = self.proveedor.generar_de.return_value

        def generar(de):
            entrando.set()
            if not continuar.wait(10):
                raise RuntimeError("timeout test")
            return resultado

        def ejecutar():
            close_old_connections()
            try:
                return emitir_factura(self.factura.pk, contrato=self.contrato, client=self.proveedor).estado
            finally:
                close_old_connections()

        self.proveedor.generar_de.side_effect = generar
        with ThreadPoolExecutor(max_workers=2) as pool:
            primera = pool.submit(ejecutar)
            try:
                self.assertTrue(entrando.wait(10))
                self.assertEqual(pool.submit(ejecutar).result(timeout=10), "EN_PROCESO")
            finally:
                continuar.set()
            self.assertEqual(primera.result(timeout=10), "GENERADA")
        self.proveedor.generar_de.assert_called_once()
