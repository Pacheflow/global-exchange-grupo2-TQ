"""Contrato ESI TEST: payload resumido, extracción y numeración persistente."""
from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from clientes.models import Cliente
from facturacion.contracts.factura_segura_test import ContratoFacturaSeguraTest
from facturacion.models import NumeroFiscalAsignado, RangoNumeracionFiscal
from facturacion.services.factura_segura import ResultadoOperacion
from facturacion.services.facturas import preparar_factura
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from operaciones.models import Transaccion
from tasas.models import ConsultaProveedorTasas, TasaComercial, TasaReferencia


CONFIG_TEST = dict(
    FACTURA_SEGURA_RUC="2595733", FACTURA_EMISOR_DV="3",
    FACTURA_EMISOR_TIPO_CONTRIBUYENTE="1", FACTURA_EMISOR_NOMBRE="GLOBAL EXCHANGE TEST",
    FACTURA_EMISOR_DIRECCION="ASUNCION", FACTURA_EMISOR_NUMERO_CASA="0",
    FACTURA_EMISOR_DEPARTAMENTO_CODIGO="1", FACTURA_EMISOR_DEPARTAMENTO="CAPITAL",
    FACTURA_EMISOR_CIUDAD_CODIGO="1", FACTURA_EMISOR_CIUDAD="ASUNCION (DISTRITO)",
    FACTURA_EMISOR_TELEFONO="(021)5887000", FACTURA_EMISOR_EMAIL="esi@example.test",
    FACTURA_EMISOR_ACTIVIDAD_CODIGO="64990",
    FACTURA_EMISOR_ACTIVIDAD_DESCRIPCION="SERVICIOS FINANCIEROS TEST",
    FACTURA_TIMBRADO="02595733", FACTURA_TIMBRADO_FECHA_INICIO="2025-03-27",
    FACTURA_ESTABLECIMIENTO="001", FACTURA_PUNTO_EXPEDICION="003",
    FACTURA_NUMERO_DESDE="338", FACTURA_NUMERO_HASTA="349",
    FACTURA_TIPO_IMPUESTO="1", FACTURA_AFECTACION_IVA="1",
    FACTURA_PROPORCION_IVA="100", FACTURA_TASA_IVA="10",
)


@override_settings(**CONFIG_TEST)
class ContratoFacturaSeguraTestTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Receptor Test", documento="1234567-8",
            correo_facturacion="receptor@example.test", tipo_persona="FISICA",
        )
        usd = self.usd = Moneda.objects.get(codigo="USD")
        pyg = self.pyg = Moneda.objects.get(codigo="PYG")
        tasa = TasaComercial.objects.create(
            moneda_origen=usd, moneda_destino=pyg, compra=7000, venta=7100,
            usuario_id="analista", usuario_username="analista",
        )
        metodo = self.metodo = MetodoPago.objects.create(
            nombre="Stripe TEST fiscal", naturaleza="ELECTRONICO"
        )
        self.operacion = Transaccion.objects.create(
            cliente=self.cliente, clave_idempotencia=str(uuid4()),
            creado_por_keycloak_id="usuario", creado_por_username="usuario",
            version_flujo=1, canal="ONLINE", naturaleza_metodo="ELECTRONICO",
            tipo="COMPRA", moneda_origen=usd, moneda_destino=pyg,
            monto_origen=100, monto_destino=693000, tasa_comercial=tasa,
            tasa_aplicada=7000, porcentaje_comision=1, importe_comision=7000,
            metodo_pago=metodo, metodo_pago_nombre=metodo.nombre, estado="COMPLETADA",
        )
        self.factura = preparar_factura(self.operacion.pk)
        self.contrato = ContratoFacturaSeguraTest()

    def test_construye_json_resumido_y_reserva_primer_numero(self):
        de = self.contrato.construir_de(self.factura.datos_operacion)

        self.assertEqual(de["dRucEm"], "2595733")
        self.assertEqual(de["dDVEmi"], "3")
        self.assertEqual(de["dNumTim"], "02595733")
        self.assertEqual(de["dEst"], "001")
        self.assertEqual(de["dPunExp"], "003")
        self.assertEqual(de["dNumDoc"], "0000338")
        self.assertEqual(de["iTipTra"], "6")
        self.assertEqual(de["cMoneOpe"], "PYG")
        self.assertEqual(de["dRucRec"], "1234567")
        self.assertEqual(de["dDVRec"], "8")
        self.assertEqual(de["gPaConEIni"][0]["dMonTiPag"], "7000")
        self.assertEqual(de["gCamItem"][0]["dPUniProSer"], "7000")
        self.assertEqual(de["gCamItem"][0]["dTasaIVA"], "10")
        self.assertEqual(NumeroFiscalAsignado.objects.get(factura=self.factura).numero, 338)

    def test_reconstruir_reutiliza_numero_y_no_avanza_dos_veces(self):
        primero = self.contrato.construir_de(self.factura.datos_operacion)
        segundo = self.contrato.construir_de(self.factura.datos_operacion)
        self.assertEqual(primero["dNumDoc"], segundo["dNumDoc"])
        self.assertEqual(NumeroFiscalAsignado.objects.count(), 1)
        self.assertEqual(RangoNumeracionFiscal.objects.get().siguiente_numero, 339)

    def test_extrae_de_calculado_del_contrato_real(self):
        de = {"iTiDE": "1", "dNumDoc": "0000338"}
        resultado = ResultadoOperacion(
            codigo=0, descripcion="OK", operacion_id="esi-id",
            resultados=({"DE": de},),
        )
        self.assertEqual(self.contrato.extraer_de_calculado(resultado), de)

        with self.assertRaises(ValidationError):
            self.contrato.extraer_de_calculado(
                ResultadoOperacion(0, "OK", "esi-id", ({"otro": {}},))
            )

    def test_rechaza_receptor_sin_correo_antes_de_reservar(self):
        snapshot = self.factura.datos_operacion.copy()
        snapshot["correo_facturacion"] = ""
        with self.assertRaises(ValidationError):
            self.contrato.construir_de(snapshot)
        self.assertFalse(NumeroFiscalAsignado.objects.exists())

    def test_convierte_comision_extranjera_y_factura_siempre_en_pyg(self):
        tasa = TasaComercial.objects.create(
            moneda_origen=self.pyg, moneda_destino=self.usd,
            compra="0.0002", venta="0.0002", usuario_id="analista",
        )
        operacion = Transaccion.objects.create(
            cliente=self.cliente, clave_idempotencia=str(uuid4()),
            creado_por_keycloak_id="usuario", version_flujo=1, canal="ONLINE",
            naturaleza_metodo="ELECTRONICO", tipo="VENTA",
            moneda_origen=self.pyg, moneda_destino=self.usd,
            monto_origen=500000, monto_destino=99, tasa_comercial=tasa,
            tasa_aplicada="0.0002", porcentaje_comision=1, importe_comision=1,
            metodo_pago=self.metodo, metodo_pago_nombre=self.metodo.nombre,
            estado="COMPLETADA",
        )
        factura = preparar_factura(operacion.pk)
        self.assertEqual(factura.datos_operacion["importe_comision_pyg"], "5000")
        self.assertEqual(factura.datos_operacion["tasa_conversion_pyg"], "5000")

        de = self.contrato.construir_de(factura.datos_operacion)
        self.assertEqual(de["cMoneOpe"], "PYG")
        self.assertEqual(de["dTiCam"], "1")
        self.assertEqual(de["gPaConEIni"][0]["cMoneTiPag"], "PYG")
        self.assertEqual(de["gPaConEIni"][0]["dMonTiPag"], "5000")
        self.assertEqual(de["gCamItem"][0]["dPUniProSer"], "5000")

    def test_convierte_moneda_cruzada_con_referencia_persistida(self):
        eur = Moneda.objects.get(codigo="EUR")
        ahora = timezone.now()
        consulta = ConsultaProveedorTasas.objects.create(
            fuente="PROVEEDOR_TEST", moneda_base=self.usd,
            fecha_hora_fuente=ahora, respuesta={"base": "USD"},
        )
        for moneda, valor in ((eur, "0.8"), (self.pyg, "8000")):
            TasaReferencia.objects.create(
                moneda_base=self.usd, moneda_cotizada=moneda, valor=valor,
                fuente="PROVEEDOR_TEST", fecha_hora_fuente=ahora,
                vigente_hasta=ahora + timedelta(hours=1), consulta=consulta,
            )
        tasa = TasaComercial.objects.create(
            moneda_origen=self.usd, moneda_destino=eur,
            compra="0.8", venta="0.81", usuario_id="analista",
        )
        operacion = Transaccion.objects.create(
            cliente=self.cliente, clave_idempotencia=str(uuid4()),
            creado_por_keycloak_id="usuario", version_flujo=1, canal="ONLINE",
            naturaleza_metodo="ELECTRONICO", tipo="COMPRA",
            moneda_origen=self.usd, moneda_destino=eur,
            monto_origen=250, monto_destino=198, tasa_comercial=tasa,
            tasa_aplicada="0.8", porcentaje_comision=1, importe_comision=2,
            metodo_pago=self.metodo, metodo_pago_nombre=self.metodo.nombre,
            estado="COMPLETADA",
        )

        factura = preparar_factura(operacion.pk)

        self.assertEqual(factura.datos_operacion["importe_comision_pyg"], "20000")
        self.assertEqual(factura.datos_operacion["tasa_conversion_pyg"], "10000")
        self.assertEqual(
            factura.datos_operacion["fuente_conversion_pyg"], "PROVEEDOR_TEST:USD"
        )

