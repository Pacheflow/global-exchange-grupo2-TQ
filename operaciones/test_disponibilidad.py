"""Disponibilidad informativa sin reservas ni proveedores externos."""
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cajas.models import Caja, MovimientoCaja, PeriodoCaja, SaldoInicialCaja
from cajas.services import hay_disponibilidad
from cajas.test_utils import crear_fondos_prueba
from fondos.test_utils import crear_fondos_prueba as crear_fondos_online
from fondos.models import MovimientoFondo
from pagos.models import Pago
from . import tests as escenarios
from .models import Transaccion
from .services import liquidar_transaccion


class DisponibilidadOperacionTests(escenarios.BaseOperacionesTests):
    con_fondos_operacion = False

    def test_preview_sin_fondos_y_confirmacion_compra_venta_sin_escrituras(self):
        """Sin fondos, ambos tipos se previsualizan pero confirmar rechaza sin operación, Pago ni movimientos."""
        for tipo in ("COMPRA", "VENTA"):
            with self.subTest(tipo=tipo):
                self.assertGreater(self.previsualizar(tipo=tipo).monto_destino, 0)
                with self.assertRaises(ValidationError) as error:
                    self.crear(tipo=tipo)
                self.assertEqual(error.exception.code, "DISPONIBILIDAD_INSUFICIENTE")
        self.assertFalse(Transaccion.objects.exists())
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_caja_cerrada_deshabilitada_o_sin_moneda_no_cubre(self):
        """Solo Caja habilitada con período abierto y moneda destino participa de la disponibilidad."""
        periodo = crear_fondos_prueba((self.pyg,), Decimal("100"))
        for campo, valor in (("periodo", "CERRADO"), ("caja", "DESHABILITADA")):
            with self.subTest(campo=campo):
                if campo == "periodo":
                    PeriodoCaja.objects.filter(pk=periodo.pk).update(estado=valor)
                else:
                    Caja.objects.filter(pk=periodo.caja_id).update(estado=valor)
                self.assertFalse(hay_disponibilidad(moneda_id=self.pyg.pk, monto=Decimal("100")))
                PeriodoCaja.objects.filter(pk=periodo.pk).update(estado="ABIERTO")
                Caja.objects.filter(pk=periodo.caja_id).update(estado="HABILITADA")
        self.assertFalse(hay_disponibilidad(moneda_id=self.usd.pk, monto=Decimal("1")))

    def test_no_suma_cajas_y_acepta_una_suficiente_con_saldo_exacto(self):
        """Dos saldos 40 y 60 no cubren 100; una caja con 100 sí, sin mezclar monedas."""
        crear_fondos_prueba((self.pyg,), Decimal("40"))
        periodo = crear_fondos_prueba((self.pyg, self.usd), Decimal("60"))
        self.assertFalse(hay_disponibilidad(moneda_id=self.pyg.pk, monto=Decimal("100")))
        SaldoInicialCaja.objects.filter(periodo=periodo, moneda=self.pyg).update(monto=100)
        self.assertTrue(hay_disponibilidad(moneda_id=self.pyg.pk, monto=Decimal("100")))
        self.assertFalse(hay_disponibilidad(moneda_id=self.pyg.pk, monto=Decimal("100.000001")))

    def test_movimientos_y_consulta_unica_sin_locks(self):
        """Ingresos y egresos del destino alteran el saldo; otra moneda no cuenta y la lectura no bloquea."""
        periodo = crear_fondos_prueba((self.pyg, self.usd), Decimal("100"))
        for tipo, moneda, monto in (("INGRESO", self.pyg, "20"), ("EGRESO", self.pyg, "10"),
                                   ("INGRESO", self.usd, "500")):
            MovimientoCaja.objects.create(periodo=periodo, tipo=tipo, moneda=moneda, monto=Decimal(monto),
                                           motivo="Fixture", registrado_por_keycloak_id="cajero")
        with CaptureQueriesContext(connection) as consultas:
            self.assertTrue(hay_disponibilidad(moneda_id=self.pyg.pk, monto=Decimal("110")))
        self.assertEqual(len(consultas), 1)
        self.assertNotIn("FOR UPDATE", consultas[0]["sql"].upper())
        self.assertFalse(hay_disponibilidad(moneda_id=self.pyg.pk, monto=Decimal("111")))

    def test_confirmacion_usa_destino_neto_y_no_cobra(self):
        """El saldo exacto del destino recalculado tras comisión permite COMPRA pendiente y VENTA completada sin Pago."""
        for tipo in ("COMPRA", "VENTA"):
            with self.subTest(tipo=tipo):
                preview = self.previsualizar(tipo=tipo)
                crear_fondos_online((self.pyg,), preview.monto_destino)
                with mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as stripe:
                    tx = self.crear(tipo=tipo).transaccion
                self.assertEqual(tx.monto_destino, preview.monto_destino)
                self.assertEqual(tx.estado, "COMPLETADA" if tipo == "VENTA" else "PENDIENTE")
                stripe.assert_not_called()
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_idempotencia_con_fondos_agotados_conserva_registro_y_rechaza_otra_huella(self):
        """Tras crear, repetir la misma clave ignora fondos nuevos pero cambiar el importe sigue rechazado."""
        crear_fondos_online((self.pyg,))
        clave = self.clave_idempotencia()
        tx = self.crear(clave_idempotencia=clave).transaccion
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto=0.000001)
        repetida = self.crear(clave_idempotencia=clave)
        self.assertTrue(repetida.repetida)
        self.assertEqual(repetida.transaccion.pk, tx.pk)
        with self.assertRaises(ValidationError):
            self.crear(clave_idempotencia=clave, monto="101")
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_online_no_puede_liquidarse_en_caja(self):
        """Una COMPRA online rechaza liquidación física sin crear movimientos de Caja."""
        crear_fondos_online((self.pyg,))
        tx = self.crear().transaccion
        periodo = crear_fondos_prueba((self.pyg,))
        with self.assertRaises(ValidationError) as error:
            liquidar_transaccion(transaccion_id=tx.pk, periodo_id=periodo.pk, usuario_id="cajero", roles=["CAJERO"])
        self.assertEqual(error.exception.code, "REVISION_PENDIENTE")
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_http_distingue_falta_de_fondos_y_fallo_tecnico(self):
        """Confirmar sin fondos devuelve mensaje controlado; fallo técnico da 500 sin afirmar falta de fondos."""
        from .test_guillermo import FlujosGuillermoTests
        FlujosGuillermoTests.autenticar(self)
        url = reverse("operaciones:crear_transaccion")
        respuesta = self.client.post(url, self.parametros_confirmacion_http(), content_type="application/json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["error"],
                         "No hay disponibilidad suficiente para atender esta operación. Intenta más tarde.")
        with mock.patch("fondos.services.hay_disponibilidad", side_effect=DatabaseError("privado")):
            respuesta = self.client.post(url, self.parametros_confirmacion_http(), content_type="application/json")
        self.assertEqual(respuesta.status_code, 500)
        self.assertNotIn("disponibilidad", respuesta.json()["error"])
        self.assertNotContains(respuesta, "privado", status_code=500)
        self.assertFalse(Transaccion.objects.exists())
