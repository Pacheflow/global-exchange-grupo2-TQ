"""Datos fiscales congelados y descarga web con transporte externo simulado."""
from unittest.mock import Mock, patch

import requests
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from .models import Factura
from .services.factura_segura import FacturaSeguraClient
from .services.facturas import preparar_factura
from .test_facturas import EscenarioFactura


class DatosFiscalesFacturaTests(EscenarioFactura, TestCase):
    def preparar_juridica(self, *, documento="80012345", dv="6", correo="fiscal@example.test"):
        self.factura.delete()
        self.cliente.tipo_persona = "JURIDICA"
        self.cliente.documento = documento
        self.cliente.dv = dv
        self.cliente.correo_facturacion = correo
        self.cliente.save()
        self.factura = preparar_factura(self.op.pk)
        return self.factura.datos_operacion

    def test_juridica_guarda_ruc_base_dv_y_datos_comerciales(self):
        datos = self.preparar_juridica()
        self.assertEqual(datos["tipo_persona"], "JURIDICA")
        self.assertEqual(datos["documento"], "80012345")
        self.assertEqual(datos["ruc"], "80012345")
        self.assertEqual(datos["dv"], "6")
        self.assertEqual(datos["correo_facturacion"], "fiscal@example.test")
        self.assertEqual(datos["transaccion_id"], self.op.pk)
        self.assertEqual(datos["cliente_id"], self.cliente.pk)
        self.assertEqual(datos["cliente"], "Cliente facturas")
        self.assertEqual(datos["tipo"], "COMPRA")
        self.assertEqual(datos["moneda_origen"], "USD")
        self.assertEqual(datos["moneda_destino"], "PYG")
        for campo in ("monto_origen", "monto_destino", "tasa_aplicada",
                      "importe_comision", "porcentaje_comision"):
            self.assertIsInstance(datos[campo], str)

    def test_fisica_conserva_cedula_sin_exigir_ruc_dv_ni_correo(self):
        datos = self.factura.datos_operacion
        self.assertEqual(datos["tipo_persona"], "FISICA")
        self.assertEqual(datos["documento"], "123456")
        self.assertEqual(datos["ruc"], "")
        self.assertEqual(datos["dv"], "")
        self.assertEqual(datos["correo_facturacion"], "")
        self.autenticar()
        respuesta = self.client.get(reverse("facturacion:detalle", args=[self.factura.pk]))
        self.assertContains(respuesta, "Persona Física")
        self.assertContains(respuesta, "Documento: 123456")
        self.assertNotContains(respuesta, "RUC:")
        self.assertNotContains(respuesta, "DV:")
        self.assertNotContains(respuesta, "Correo de facturación:")

    def test_correo_es_opcional_tambien_para_juridica(self):
        self.assertEqual(self.preparar_juridica(correo="")["correo_facturacion"], "")

    def test_snapshot_no_cambia_al_editar_cliente_y_repreparar(self):
        datos_originales = self.preparar_juridica().copy()
        self.cliente.nombre_razon_social = "Cliente modificado después"
        self.cliente.documento = "80099999"
        self.cliente.dv = "1"
        self.cliente.correo_facturacion = "nuevo@example.test"
        self.cliente.save()
        repetida = preparar_factura(self.op.pk)
        self.assertEqual(repetida.pk, self.factura.pk)
        self.assertEqual(repetida.datos_operacion, datos_originales)
        self.autenticar()
        respuesta = self.client.get(reverse("facturacion:detalle", args=[repetida.pk]))
        for valor in ("Cliente facturas", "Persona Jurídica", "RUC: 80012345",
                      "DV: 6", "fiscal@example.test"):
            self.assertContains(respuesta, valor)
        for valor in ("Cliente modificado después", "80099999", "nuevo@example.test"):
            self.assertNotContains(respuesta, valor)

    def test_documento_legacy_no_infiere_dv_al_crear_snapshot(self):
        datos = self.preparar_juridica(documento="80012345-6", dv="")
        self.assertEqual(datos["documento"], "80012345-6")
        self.assertEqual(datos["ruc"], "80012345-6")
        self.assertEqual(datos["dv"], "")

    def test_snapshot_historico_no_completa_datos_desde_cliente_actual(self):
        datos = self.preparar_juridica().copy()
        for clave in ("ruc", "dv", "correo_facturacion"):
            datos.pop(clave)
        self.factura.datos_operacion = datos
        self.factura.save(update_fields=["datos_operacion"])
        self.cliente.documento = "80099999"
        self.cliente.save()
        self.autenticar()
        respuesta = self.client.get(reverse("facturacion:detalle", args=[self.factura.pk]))
        self.assertContains(respuesta, "RUC: 80012345")
        self.assertNotContains(respuesta, "80099999")
        self.assertNotContains(respuesta, "DV:")
        self.assertNotContains(respuesta, "fiscal@example.test")
        self.assertEqual(preparar_factura(self.op.pk).datos_operacion, datos)


class FacturaDisponibilidadHTTPTests(EscenarioFactura, TestCase):
    def setUp(self):
        super().setUp()
        self.autenticar()
        self.transporte = Mock(spec=["get", "post"])
        respuesta = Mock(status_code=200, headers={"Content-Type": "application/pdf"})
        respuesta.iter_content.return_value = [b"%PDF-1.4\nprueba"]
        self.transporte.get.return_value = respuesta
        self.adaptador = FacturaSeguraClient(api_url="https://fiscal.example.test/esi",
            token="token-ficticio-prueba", ruc_emisor="80011222", session=self.transporte)

    def test_listado_pendiente_ofrece_consulta_sin_pdf(self):
        respuesta = self.client.get(reverse("facturacion:listado"))
        self.assertContains(respuesta, "Pendiente de emisión")
        self.assertContains(respuesta, f'href="{reverse("facturacion:detalle", args=[self.factura.pk])}"')
        self.assertNotContains(respuesta, "Descargar PDF")
        self.transporte.get.assert_not_called()
        self.proveedor.generar_de.assert_not_called()

    def test_generada_expone_enlaces_backend_y_cdc_sin_url_del_proveedor(self):
        self.generar()
        for nombre in ("listado", "detalle"):
            args = [] if nombre == "listado" else [self.factura.pk]
            respuesta = self.client.get(reverse(f"facturacion:{nombre}", args=args))
            self.assertContains(respuesta, f'href="{reverse("facturacion:descargar", args=[self.factura.pk, "pdf"])}"')
            self.assertNotContains(respuesta, self.adaptador.api_url)
            self.assertNotContains(respuesta, self.adaptador.token)
        detalle = self.client.get(reverse("facturacion:detalle", args=[self.factura.pk]))
        self.assertContains(detalle, f"CDC: {self.factura.cdc}")
        self.assertContains(detalle, "Descargar XML")
        self.assertContains(detalle, "Ver comprobante PDF")
        self.assertContains(detalle, f"Operación: COMPRA")
        self.assertContains(detalle, "Estado de emisión:")
        self.transporte.get.assert_not_called()

    def test_estados_no_generados_no_ofrecen_descarga(self):
        for estado in ("PENDIENTE", "EN_PROCESO", "ERROR", "INDETERMINADA"):
            with self.subTest(estado=estado):
                Factura.objects.filter(pk=self.factura.pk).update(estado=estado)
                listado = self.client.get(reverse("facturacion:listado"))
                detalle = self.client.get(reverse("facturacion:detalle", args=[self.factura.pk]))
                self.assertNotContains(listado, "Descargar PDF")
                self.assertNotContains(detalle, "Descargar PDF")
                self.assertNotContains(detalle, "Descargar XML")
                self.assertContains(detalle, "El comprobante todavía no está disponible.")
        self.transporte.get.assert_not_called()

    def test_plantillas_exigen_cdc_ademas_de_estado_generada(self):
        # La BD impide este estado incompleto; también se protege la presentación.
        self.factura.estado = "GENERADA"
        self.factura.cdc = ""
        contexto = {"factura": self.factura,
                    "pagina": Paginator([self.factura], 20).page(1)}
        for plantilla in ("frontend/facturas.html", "frontend/factura_detalle.html"):
            with self.subTest(plantilla=plantilla):
                html = render_to_string(plantilla, contexto)
                self.assertNotIn("Descargar PDF", html)

    def test_descarga_pdf_autorizada_usa_adapter_con_transporte_simulado(self):
        self.generar()
        with patch("facturacion.services.facturas.obtener_factura_segura_client", return_value=self.adaptador):
            respuesta = self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, "pdf"]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn("attachment", respuesta["Content-Disposition"])
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.assertEqual(b"".join(respuesta.streaming_content), b"%PDF-1.4\nprueba")
        self.transporte.get.assert_called_once()
        self.assertIn(f"/dwn_kude/80011222/{self.factura.cdc}", self.transporte.get.call_args.args[0])
        self.assertFalse(self.transporte.get.call_args.kwargs["allow_redirects"])
        self.transporte.post.assert_not_called()

    def test_descarga_sin_asociacion_activa_devuelve_404_sin_transporte(self):
        self.generar()
        with patch("facturacion.services.facturas.obtener_factura_segura_client", return_value=self.adaptador):
            self.autenticar(usuario="otro")
            respuesta = self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, "pdf"]))
            self.assertEqual(respuesta.status_code, 404)
            self.autenticar()
            self.asociacion.activo = False
            self.asociacion.save(update_fields=["activo"])
            respuesta = self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, "pdf"]))
            self.assertEqual(respuesta.status_code, 404)
        self.transporte.get.assert_not_called()
        self.transporte.post.assert_not_called()

    def test_otros_roles_no_descargan_ni_contactan_proveedor(self):
        self.generar()
        with patch("facturacion.services.facturas.obtener_factura_segura_client", return_value=self.adaptador):
            for rol in ("CAJERO", "ADMINISTRADOR", "ANALISTA_CAMBIARIO"):
                with self.subTest(rol=rol):
                    self.autenticar(rol=rol)
                    respuesta = self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, "pdf"]))
                    self.assertEqual(respuesta.status_code, 403)
        self.transporte.get.assert_not_called()
        self.transporte.post.assert_not_called()

    def test_timeout_descarga_responde_503_sin_detalles_privados(self):
        self.generar()
        self.transporte.get.side_effect = requests.Timeout("detalle-privado-prueba token-ficticio-prueba")
        with patch("facturacion.services.facturas.obtener_factura_segura_client", return_value=self.adaptador):
            with self.assertLogs("facturacion.views", level="ERROR") as logs:
                respuesta = self.client.get(reverse("facturacion:descargar", args=[self.factura.pk, "pdf"]))
        self.assertEqual(respuesta.status_code, 503)
        self.assertContains(respuesta, "No se pudo obtener el comprobante.", status_code=503)
        self.assertNotContains(respuesta, "detalle-privado-prueba", status_code=503)
        self.assertNotContains(respuesta, self.adaptador.token, status_code=503)
        self.assertNotIn("detalle-privado-prueba", str(logs.output))
        self.assertNotIn(self.adaptador.token, str(logs.output))
        self.transporte.post.assert_not_called()
