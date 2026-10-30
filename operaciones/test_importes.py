"""Regresiones de frontera: importes exactos, respuestas 400 y ausencia de efectos."""
import time
from decimal import Decimal, localcontext
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.urls import reverse

from cajas.models import MovimientoCaja
from fondos.models import ReservaFondo
from pagos.models import Pago
from pagos.services import iniciar_pago
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)

from .importes import especificacion_montos, validar_monto_operacion
from .models import Transaccion
from .services import _calcular_operacion, crear_transaccion
from .tests import BaseOperacionesTests as _BaseOperacionesTests


class LimitesImportesTests(SimpleTestCase):
    def assert_codigo(self, monto, codigo, **flujo):
        with self.assertRaises(ValidationError) as error:
            validar_monto_operacion(monto, **flujo)
        self.assertEqual(error.exception.code, codigo)

    def test_cero_negativos_vacios_no_numericos_y_no_finitos(self):
        for monto in ("0", "-1", "", "texto", None, True, "NaN", "sNaN", "Infinity", "-Infinity"):
            with self.subTest(monto=monto):
                self.assert_codigo(monto, "MONTO_INVALIDO")

    def test_limite_persistible_exacto_y_ceros_sobrantes(self):
        for monto in ("999999999999.999999", "1.230000000000", "1e11", "0.000001000"):
            with self.subTest(monto=monto):
                aceptado = validar_monto_operacion(monto)
                self.assertEqual(aceptado, Decimal(monto))
                # La forma retornada debe poder guardarse con DecimalField(18, 6).
                Transaccion._meta.get_field("monto_origen").run_validators(aceptado)

    def test_exceso_incluye_exponentes_extremos_sin_expandirlos(self):
        for monto in ("1000000000000", "999999999999.9999991", "1e30", "1e1000000000"):
            with self.subTest(monto=monto):
                self.assert_codigo(monto, "MONTO_EXCESIVO")

    def test_precision_rechaza_sin_redondeo_y_exponentes_negativos_extremos(self):
        for monto in ("1.0000001", "0.0000001", "1e-9999999"):
            with self.subTest(monto=monto):
                self.assert_codigo(monto, "MONTO_PRECISION")

    def test_compra_online_usa_maximo_y_precision_stripe_por_moneda(self):
        for codigo in ("USD", "EUR", "BRL", "ARS", "PYG"):
            with self.subTest(moneda=codigo):
                flujo = dict(tipo="COMPRA", moneda_codigo=codigo)
                maximo = "99999999" if codigo == "PYG" else "999999.99"
                exceso = "100000000" if codigo == "PYG" else "1000000"
                impreciso = "1.1" if codigo == "PYG" else "1.001"
                self.assertEqual(validar_monto_operacion(maximo, **flujo), Decimal(maximo))
                self.assertEqual(validar_monto_operacion("1.00000000", **flujo), Decimal("1"))
                self.assert_codigo(exceso, "MONTO_EXCESIVO", **flujo)
                self.assert_codigo(impreciso, "MONTO_PRECISION", **flujo)

    def test_venta_y_presencial_conservan_precision_y_capacidad_modelo(self):
        for flujo in (dict(tipo="VENTA", moneda_codigo="USD"),
                      dict(tipo="COMPRA", moneda_codigo="PYG", presencial=True)):
            with self.subTest(flujo=flujo):
                monto = "999999999999.999999"
                self.assertEqual(validar_monto_operacion(monto, **flujo), Decimal(monto))
        limites = especificacion_montos()
        self.assertEqual(limites["general"]["decimales"], 6)
        self.assertEqual(limites["compra_online"]["PYG"]["decimales"], 0)

    def test_producto_grande_se_rechaza_como_validacion_controlada(self):
        with localcontext() as contexto:
            contexto.prec = 28
            with self.assertRaises(ValidationError) as error:
                _calcular_operacion(Decimal("999999999999.999999"),
                                    Decimal("99999999999999.9999999999"), Decimal("10"))
        self.assertEqual(error.exception.code, "MONTO_EXCESIVO")

    def test_bruto_no_persistido_puede_superar_limite_si_neto_y_comision_caben(self):
        bruto, comision, neto = _calcular_operacion(Decimal("999999999999"), Decimal("2"), Decimal("50"))
        self.assertEqual(bruto, Decimal("1999999999998"))
        self.assertEqual(comision, Decimal("999999999999"))
        self.assertEqual(neto, comision)

    def test_comision_excesiva_y_destino_cero_o_excesivo_son_invalidos(self):
        for monto, tasa, porcentaje, codigo in (
            ("999999999999", "2", "100", "MONTO_EXCESIVO"),
            ("999999999999", "2", "0", "MONTO_EXCESIVO"),
            ("0.000001", "0.0000000001", "0", "MONTO_INVALIDO"),
            ("1", "1", "100", "MONTO_INVALIDO"),
        ):
            with self.subTest(monto=monto, tasa=tasa, porcentaje=porcentaje):
                with self.assertRaises(ValidationError) as error:
                    _calcular_operacion(Decimal(monto), Decimal(tasa), Decimal(porcentaje))
                self.assertEqual(error.exception.code, codigo)

    def test_redondeo_half_up_se_conserva_con_contexto_global_reducido(self):
        with localcontext() as contexto:
            contexto.prec = 6
            bruto, comision, neto = _calcular_operacion(Decimal("1.000001"), Decimal("0.5"), Decimal("10"))
        self.assertEqual((bruto, comision, neto),
                         (Decimal("0.500001"), Decimal("0.050000"), Decimal("0.450001")))


class FronteraImportesTests(_BaseOperacionesTests):
    con_fondos_operacion = False

    def setUp(self):
        super().setUp()
        sesion = self.client.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = int(time.time()) + 600
        sesion[SESSION_ROLES] = ["USUARIO"]
        sesion[SESSION_USUARIO] = {"sub": self.usuario_id, "username": self.usuario_username}
        sesion["selected_client"] = {"id": self.cliente.pk, "name": self.cliente.nombre_razon_social}
        sesion.save()

    def assert_sin_efectos(self):
        self.assertFalse(Transaccion.objects.exists())
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(ReservaFondo.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_preview_400_montos_invalidos_sin_fondos_caja_ni_stripe(self):
        with mock.patch("fondos.services.reservar") as reservar, \
             mock.patch("operaciones.services.registrar_movimiento_automatico") as caja, \
             mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as stripe:
            for monto, codigo in (("0", "MONTO_INVALIDO"), ("-1", "MONTO_INVALIDO"),
                                  ("abc", "MONTO_INVALIDO"), ("1.001", "MONTO_PRECISION"),
                                  ("1e1000000000", "MONTO_EXCESIVO"), ("1000000", "MONTO_EXCESIVO"),
                                  ("2344352346345645547567", "MONTO_EXCESIVO")):
                with self.subTest(monto=monto):
                    respuesta = self.client.post(reverse("operaciones:previsualizar_operacion"),
                                                 self.parametros_preview(monto=monto), content_type="application/json")
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertEqual(respuesta.json()["codigo"], codigo)
            reservar.assert_not_called()
            caja.assert_not_called()
            stripe.assert_not_called()
        self.assert_sin_efectos()

    def test_creacion_400_incluso_sin_firma_con_exponente_enorme(self):
        datos = self.parametros_crear(monto="1e1000000000")
        respuesta = self.client.post(reverse("operaciones:crear_transaccion"), datos, content_type="application/json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["codigo"], "MONTO_EXCESIVO")
        self.assertEqual(respuesta.json()["error"], "El monto ingresado supera el límite permitido para una operación.")
        self.assert_sin_efectos()

    def test_creacion_revalida_limites_en_servicio_y_con_firma_valida(self):
        with mock.patch("fondos.services.hay_disponibilidad") as fondos, \
             mock.patch("operaciones.services.hay_disponibilidad") as caja, \
             mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as stripe:
            for monto, codigo in (("1000000", "MONTO_EXCESIVO"), ("1.001", "MONTO_PRECISION")):
                with self.subTest(monto=monto):
                    with self.assertRaises(ValidationError) as error:
                        crear_transaccion(**self.parametros_crear(monto=monto))
                    self.assertEqual(error.exception.code, codigo)
                    respuesta = self.client.post(reverse("operaciones:crear_transaccion"),
                                                 self.parametros_confirmacion_http(monto=monto), content_type="application/json")
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertEqual(respuesta.json()["codigo"], codigo)
            fondos.assert_not_called()
            caja.assert_not_called()
            stripe.assert_not_called()
        self.assert_sin_efectos()

    def test_preview_maximo_online_y_metadata_sin_mutar_saldos(self):
        respuesta = self.client.post(reverse("operaciones:previsualizar_operacion"),
                                     self.parametros_preview(monto="999999.990000"), content_type="application/json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Decimal(respuesta.json()["monto_origen"]), Decimal("999999.99"))
        self.assertEqual(respuesta.json()["limites_monto"],
                         {"maximo": "999999.99", "decimales": 2, "minimo": "0.01"})
        self.assert_sin_efectos()

    def test_preview_y_creacion_rechazan_conversion_excesiva_antes_fondos(self):
        self.tasa.compra = Decimal("99999999999999")
        self.tasa.save(update_fields=["compra"])
        datos = self.parametros_confirmacion_http(monto="999999.99")
        with mock.patch("fondos.services.hay_disponibilidad") as fondos:
            for ruta in ("previsualizar_operacion", "crear_transaccion"):
                respuesta = self.client.post(reverse("operaciones:" + ruta), datos, content_type="application/json")
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.json()["codigo"], "MONTO_EXCESIVO")
            fondos.assert_not_called()
        self.assert_sin_efectos()

    def test_precision_valida_se_persiste_sin_ceros_excedentes(self):
        with mock.patch("fondos.services.hay_disponibilidad", return_value=True):
            transaccion = self.crear(monto="100.120000000000").transaccion
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.monto_origen, Decimal("100.12"))
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(ReservaFondo.objects.exists())

    def test_pago_de_operacion_manual_invalida_no_reserva_ni_invoca_proveedor(self):
        with mock.patch("fondos.services.hay_disponibilidad", return_value=True):
            transaccion = self.crear().transaccion
        # Emula una operación insertada fuera de la frontera de creación.
        Transaccion.objects.filter(pk=transaccion.pk).update(monto_origen=Decimal("1000000"))
        provider = mock.Mock()
        with mock.patch("pagos.services._exigir_autocommit"), \
             mock.patch("pagos.services.reservar") as reservar:
            with self.assertRaises(ValidationError) as error:
                iniciar_pago(transaccion_id=transaccion.pk, usuario_id=self.usuario_id,
                             roles=["USUARIO"], cliente_seleccionado_id=self.cliente.pk, provider=provider)
            self.assertEqual(error.exception.code, "MONTO_EXCESIVO")
            reservar.assert_not_called()
        self.assertEqual(provider.mock_calls, [])
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(ReservaFondo.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_json_con_entero_de_miles_de_digitos_devuelve_400(self):
        cuerpo = '{"monto":' + '9' * 5000 + '}'
        for ruta in ("previsualizar_operacion", "crear_transaccion"):
            with self.subTest(ruta=ruta):
                respuesta = self.client.post(reverse("operaciones:" + ruta), cuerpo,
                                             content_type="application/json")
                self.assertEqual(respuesta.status_code, 400)
        self.assert_sin_efectos()

    def test_monto_excesivo_preserva_fondos_existentes_y_sus_movimientos(self):
        from fondos.models import Fondo, MovimientoFondo
        from fondos.test_utils import crear_fondos_prueba

        crear_fondos_prueba((self.usd, self.pyg))
        def snapshot():
            return {
                "fondos": list(Fondo.objects.order_by("pk").values()),
                "movimientos": list(MovimientoFondo.objects.order_by("pk").values()),
                "reservas": list(ReservaFondo.objects.order_by("pk").values()),
            }
        antes = snapshot()
        self.assertTrue(antes["movimientos"])
        datos = self.parametros_confirmacion_http(monto="2344352346345645547567")
        for ruta in ("previsualizar_operacion", "crear_transaccion"):
            with self.subTest(ruta=ruta):
                respuesta = self.client.post(reverse("operaciones:" + ruta), datos,
                                             content_type="application/json")
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.json()["codigo"], "MONTO_EXCESIVO")
                self.assertEqual(snapshot(), antes)
        self.assert_sin_efectos()
