from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase, override_settings

from .models import IntentoEmisionFacturaSegura
from .services.emision import generar_documento_una_vez

from .services.factura_segura import (
    FacturaSeguraAutenticacionError,
    FacturaSeguraClient,
    FacturaSeguraConfiguracionError,
    FacturaSeguraNoDisponible,
    FacturaSeguraProveedorError,
    FacturaSeguraRespuestaInvalida,
    FacturaSeguraResultadoIndeterminado,
    FacturaSeguraValidacionError,
    obtener_factura_segura_client,
    ResultadoGeneracion,
)


API_URL = "https://apitest.facturasegura.com.py/misife00/v1/esi"
TOKEN = "token-esi-test"
RUC = "80012345"
CDC = "12345678901234567890123456789012345678901234"


class RespuestaFalsa:
    def __init__(self, *, status=200, payload=None, contenido=b"", content_type="application/json"):
        self.status_code = status
        self._payload = payload
        self._contenido = contenido
        self.headers = {"Content-Type": content_type}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def iter_content(self, chunk_size):
        del chunk_size
        yield self._contenido


class FacturaSeguraClientTests(SimpleTestCase):
    def cliente(self, session=None, **cambios):
        datos = dict(api_url=API_URL, token=TOKEN, ruc_emisor=RUC, timeout=5,
                     max_download_bytes=1024 * 1024, session=session or mock.Mock())
        datos.update(cambios)
        return FacturaSeguraClient(**datos)

    def test_configuracion_exige_https_token_ruc_y_limites(self):
        casos = (
            {"api_url": "http://factura.test/esi"},
            {"api_url": "https://usuario:clave@factura.test/esi"},
            {"token": ""}, {"token": "token con espacios"},
            {"ruc_emisor": "800-ABC"}, {"timeout": 0},
            {"max_download_bytes": 100},
        )
        for cambios in casos:
            with self.subTest(cambios=cambios), self.assertRaises(FacturaSeguraConfiguracionError):
                self.cliente(**cambios)

    def test_calcular_envia_solo_operation_y_params_con_token_en_header(self):
        session = mock.Mock()
        session.post.return_value = RespuestaFalsa(payload={
            "code": 0, "description": "Calculado",
            "operation_info": {"id": "op-1"}, "results": [{"DE": {"total": 10}}],
        })
        resultado = self.cliente(session).calcular_de({"dNomRec": "Cliente"})
        self.assertEqual(resultado.operacion_id, "op-1")
        argumentos = session.post.call_args
        self.assertEqual(argumentos.kwargs["json"], {
            "operation": "calcular_de", "params": {"DE": {"dNomRec": "Cliente"}},
        })
        self.assertEqual(argumentos.kwargs["headers"]["Authentication-Token"], TOKEN)
        self.assertNotIn(TOKEN, str(argumentos.kwargs["json"]))
        self.assertFalse(argumentos.kwargs["allow_redirects"])

    def test_generar_devuelve_cdc_y_no_reintenta(self):
        session = mock.Mock()
        session.post.return_value = RespuestaFalsa(payload={
            "code": 0, "description": "Generado",
            "operation_info": {"id": 99}, "results": [{"CDC": CDC}],
        })
        resultado = self.cliente(session).generar_de({"DE": "calculado"})
        self.assertEqual(resultado.cdc, CDC)
        self.assertEqual(resultado.operacion_id, "99")
        self.assertEqual(session.post.call_count, 1)

    def test_timeout_de_generar_es_indeterminado_y_sin_reintento(self):
        session = mock.Mock()
        session.post.side_effect = requests.Timeout("detalle sensible")
        with self.assertRaises(FacturaSeguraResultadoIndeterminado) as error:
            self.cliente(session).generar_de({"DE": "calculado"})
        self.assertNotIn("sensible", str(error.exception))
        self.assertEqual(session.post.call_count, 1)

    def test_timeout_de_consulta_es_no_disponible(self):
        session = mock.Mock()
        session.post.side_effect = requests.Timeout()
        with self.assertRaises(FacturaSeguraNoDisponible):
            self.cliente(session).consultar_estado(CDC)

    def test_consulta_envia_cdc_y_ruc(self):
        session = mock.Mock()
        session.post.return_value = RespuestaFalsa(payload={
            "code": 0, "description": "Aprobado", "results": [{"estado_sifen": "Aprobado"}],
        })
        self.cliente(session).consultar_estado(CDC)
        self.assertEqual(session.post.call_args.kwargs["json"], {
            "operation": "get_estado_sifen", "params": {"CDC": CDC, "dRucEm": RUC},
        })

    def test_codigo_negativo_conserva_trazabilidad_controlada(self):
        session = mock.Mock()
        session.post.return_value = RespuestaFalsa(payload={
            "code": -7, "description": "Documento rechazado",
            "operation_info": {"id": "op-error"}, "results": [],
        })
        with self.assertRaises(FacturaSeguraProveedorError) as error:
            self.cliente(session).calcular_de({"dato": 1})
        self.assertEqual(error.exception.codigo, -7)
        self.assertEqual(error.exception.descripcion, "Documento rechazado")
        self.assertEqual(error.exception.operacion_id, "op-error")
        self.assertNotIn("Documento rechazado", str(error.exception))

    def test_autenticacion_respuesta_y_redireccion_se_clasifican(self):
        for respuesta, excepcion in (
            (RespuestaFalsa(status=401), FacturaSeguraAutenticacionError),
            (RespuestaFalsa(status=302), FacturaSeguraRespuestaInvalida),
            (RespuestaFalsa(payload=ValueError()), FacturaSeguraRespuestaInvalida),
            (RespuestaFalsa(payload={"code": "0", "description": "x"}), FacturaSeguraRespuestaInvalida),
        ):
            session = mock.Mock()
            session.post.return_value = respuesta
            with self.subTest(status=respuesta.status_code), self.assertRaises(excepcion):
                self.cliente(session).calcular_de({"dato": 1})

    def test_valida_de_y_cdc_antes_de_hacer_io(self):
        session = mock.Mock()
        cliente = self.cliente(session)
        for de in (None, {}, [], {1: "valor"}, {"monto": object()}, {"monto": float("nan")}):
            with self.subTest(de=de), self.assertRaises(FacturaSeguraValidacionError):
                cliente.calcular_de(de)
        with self.assertRaises(FacturaSeguraValidacionError):
            cliente.consultar_estado("cdc-invalido")
        session.post.assert_not_called()

    def test_descarga_kude_valida_tipo_tamano_y_no_sigue_redirects(self):
        session = mock.Mock()
        session.get.return_value = RespuestaFalsa(
            contenido=b"%PDF-1.7 prueba", content_type="application/pdf",
        )
        archivo = self.cliente(session).descargar_kude(CDC)
        self.assertEqual(archivo.contenido, b"%PDF-1.7 prueba")
        self.assertEqual(archivo.content_type, "application/pdf")
        self.assertTrue(archivo.nombre.endswith(".pdf"))
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertTrue(session.get.call_args.kwargs["stream"])

        session.get.return_value = RespuestaFalsa(contenido=b"html", content_type="text/html")
        with self.assertRaises(FacturaSeguraRespuestaInvalida):
            self.cliente(session).descargar_kude(CDC)

        session.get.return_value = RespuestaFalsa(contenido=b"x" * 1025, content_type="application/pdf")
        with self.assertRaises(FacturaSeguraRespuestaInvalida):
            self.cliente(session, max_download_bytes=1024).descargar_kude(CDC)

    @override_settings(
        FACTURA_SEGURA_API_URL=API_URL,
        FACTURA_SEGURA_TOKEN=TOKEN,
        FACTURA_SEGURA_RUC=RUC,
        FACTURA_SEGURA_TIMEOUT_SECONDS=5,
        FACTURA_SEGURA_MAX_DOWNLOAD_BYTES=1024 * 1024,
    )
    def test_factory_usa_configuracion_del_servidor(self):
        session = mock.Mock()
        cliente = obtener_factura_segura_client(session=session)
        self.assertEqual(cliente.api_url, API_URL)
        self.assertEqual(cliente.ruc_emisor, RUC)
        self.assertIs(cliente.session, session)


class EmisionIdempotenteTests(TestCase):
    def resultado(self):
        return ResultadoGeneracion(
            codigo=0, descripcion="Generado", operacion_id="op-1",
            resultados=({"CDC": CDC},), cdc=CDC,
        )

    def test_genera_una_vez_y_reutiliza_sin_nuevo_io(self):
        client = mock.Mock()
        client.generar_de.return_value = self.resultado()
        primero = generar_documento_una_vez(
            clave_idempotencia="factura:transaccion:123:v1",
            de_calculado={"documento": 1}, client=client,
        )
        segundo = generar_documento_una_vez(
            clave_idempotencia="factura:transaccion:123:v1",
            de_calculado={"documento": 1}, client=client,
        )
        self.assertFalse(primero.reutilizado)
        self.assertTrue(segundo.reutilizado)
        self.assertEqual(segundo.intento.estado, IntentoEmisionFacturaSegura.Estado.GENERADA)
        self.assertEqual(segundo.intento.cdc, CDC)
        self.assertEqual(client.generar_de.call_count, 1)

    def test_misma_clave_con_otro_documento_se_rechaza(self):
        client = mock.Mock()
        client.generar_de.return_value = self.resultado()
        generar_documento_una_vez(
            clave_idempotencia="factura:transaccion:124:v1",
            de_calculado={"documento": 1}, client=client,
        )
        with self.assertRaises(FacturaSeguraValidacionError):
            generar_documento_una_vez(
                clave_idempotencia="factura:transaccion:124:v1",
                de_calculado={"documento": 2}, client=client,
            )
        self.assertEqual(client.generar_de.call_count, 1)

    def test_timeout_queda_indeterminado_y_no_reemite(self):
        client = mock.Mock()
        client.generar_de.side_effect = FacturaSeguraResultadoIndeterminado("timeout")
        primero = generar_documento_una_vez(
            clave_idempotencia="factura:transaccion:125:v1",
            de_calculado={"documento": 1}, client=client,
        )
        segundo = generar_documento_una_vez(
            clave_idempotencia="factura:transaccion:125:v1",
            de_calculado={"documento": 1}, client=client,
        )
        self.assertEqual(primero.intento.estado, IntentoEmisionFacturaSegura.Estado.INDETERMINADA)
        self.assertTrue(segundo.reutilizado)
        self.assertEqual(client.generar_de.call_count, 1)

    def test_rechazo_confirmado_guarda_codigo_operacion_y_descripcion(self):
        client = mock.Mock()
        client.generar_de.side_effect = FacturaSeguraProveedorError(
            codigo=-9, descripcion="Rechazo fiscal", operacion_id="op-9",
        )
        resultado = generar_documento_una_vez(
            clave_idempotencia="factura:transaccion:126:v1",
            de_calculado={"documento": 1}, client=client,
        )
        intento = resultado.intento
        self.assertEqual(intento.estado, IntentoEmisionFacturaSegura.Estado.ERROR)
        self.assertEqual(intento.codigo_proveedor, -9)
        self.assertEqual(intento.operacion_id, "op-9")
        self.assertEqual(intento.descripcion_proveedor, "Rechazo fiscal")
