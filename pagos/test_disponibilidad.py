"""Validación previa al cobro, exclusivamente con proveedor simulado y BD de tests."""
from copy import deepcopy
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TransactionTestCase

from fondos.models import MovimientoFondo
from . import test_services as escenarios
from .models import Pago
from .providers import CodigoResultado, EstadoPago, ResultadoPago
from .services import consultar_estado_pago, iniciar_pago, recuperar_pago, reintentar_pago


class DisponibilidadPagoTests(TransactionTestCase):
    # Solo reutiliza fixtures/helpers, sin heredar las pruebas del módulo anterior.
    setUp = escenarios.PagoServiceTests.setUp
    crear_transaccion = escenarios.PagoServiceTests.crear_transaccion
    argumentos = escenarios.PagoServiceTests.argumentos
    resultado = staticmethod(escenarios.PagoServiceTests.resultado)

    def test_inicio_sin_fondos_no_reserva_pago_y_permite_intento_posterior(self):
        """Sin fondos no hay Pago ni llamada; fondos posteriores permiten iniciar y aprobar el mismo destino."""
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto="0.000001")
        with self.assertRaises(ValidationError) as error:
            iniciar_pago(**self.argumentos())
        self.assertEqual(error.exception.code, "DISPONIBILIDAD_INSUFICIENTE")
        self.assertFalse(Pago.objects.exists())
        self.provider.iniciar.assert_not_called()
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto=self.transaccion.monto_destino * 10)
        self.assertEqual(iniciar_pago(**self.argumentos()).estado, EstadoPago.APROBADO)
        self.provider.iniciar.assert_called_once()

    def test_reintento_sin_fondos_conserva_error_y_traza_hasta_intento_explicito(self):
        """Un Pago ERROR conserva identidad y trazabilidad al faltar fondos; reintenta solo tras recuperarlos."""
        self.provider.iniciar.side_effect = None
        self.provider.iniciar.return_value = ResultadoPago(EstadoPago.ERROR, CodigoResultado.ERROR_SIN_EJECUCION)
        iniciar_pago(**self.argumentos())
        pago = Pago.objects.get()
        traza = deepcopy(pago.trazabilidad)
        self.provider.iniciar.reset_mock()
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto="0.000001")
        with self.assertRaises(ValidationError):
            reintentar_pago(**self.argumentos())
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.ERROR)
        self.assertEqual(pago.trazabilidad, traza)
        self.provider.iniciar.assert_not_called()
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto=self.transaccion.monto_destino * 10)
        self.provider.iniciar.side_effect = lambda s: self.resultado(s)
        self.assertEqual(reintentar_pago(**self.argumentos()).pago_id, pago.pk)
        self.provider.iniciar.assert_called_once()

    def test_aprobado_consulta_y_recuperacion_no_dependen_de_fondos(self):
        """Sin fondos posteriores, APROBADO se reutiliza y la consulta local/recuperación no vuelven a cobrar."""
        aprobado = iniciar_pago(**self.argumentos())
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto="0.000001")
        self.assertEqual(iniciar_pago(**self.argumentos()).pago_id, aprobado.pago_id)
        self.assertEqual(reintentar_pago(**self.argumentos()).pago_id, aprobado.pago_id)
        argumentos_locales = {k: v for k, v in self.argumentos().items() if k != "provider"}
        self.assertEqual(consultar_estado_pago(**argumentos_locales).estado, EstadoPago.APROBADO)
        self.provider.iniciar.assert_called_once()
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto=self.transaccion.monto_destino * 10)
        tx = self.crear_transaccion()
        self.provider.iniciar.side_effect = TimeoutError("simulado")
        iniciar_pago(**self.argumentos(transaccion_id=tx.pk))
        llamadas = self.provider.iniciar.call_count
        self.provider.conciliar_sin_referencia.side_effect = lambda s: self.resultado(s, referencia="pi_recuperado")
        self.assertEqual(recuperar_pago(**self.argumentos(transaccion_id=tx.pk)).estado, EstadoPago.APROBADO)
        self.assertEqual(self.provider.iniciar.call_count, llamadas)
        self.provider.conciliar_sin_referencia.assert_called_once()

    def test_fallo_tecnico_no_reserva_pago_ni_se_normaliza_como_falta_de_fondos(self):
        """Un fallo de consulta se propaga antes de reservar: no altera datos ni llama al proveedor."""
        with mock.patch("pagos.services.reservar", side_effect=DatabaseError("simulado")):
            with self.assertRaises(DatabaseError):
                iniciar_pago(**self.argumentos())
        self.assertFalse(Pago.objects.exists())
        self.provider.iniciar.assert_not_called()
