"""Integración HU-28/HU-42/43/44 en PostgreSQL, sin proveedores externos."""
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from cajas import services as caja_services
from cajas.models import CierreCaja, MovimientoCaja, PeriodoCaja, SaldoInicialCaja
from cajas.services import cerrar_caja, realizar_arqueo
from pagos.models import Pago
from .models import Transaccion
from .services import liquidar_transaccion
from .tests import EscenarioLiquidacion, EscenarioLiquidacionHTTP


class IntegracionArqueoMixin(EscenarioLiquidacion):
    def arqueo(self):
        periodo, saldos = caja_services.consultar_saldos_caja(
            periodo_id=self.periodo_liquidacion.pk, usuario_id=self.usuario_id, roles=["CAJERO"],
        )
        return realizar_arqueo(
            periodo_id=periodo.pk, usuario_id=self.usuario_id, roles=["CAJERO"],
            saldos_fisicos=[{"moneda_id": s.moneda.pk, "monto": s.saldo_actual} for s in saldos],
        )

    def cierre(self):
        return cerrar_caja(periodo_id=self.periodo_liquidacion.pk,
                           usuario_id=self.usuario_id, roles=["CAJERO"])


class ArqueoLiquidacionTests(IntegracionArqueoMixin, TestCase):
    def test_movimientos_compra_y_venta_en_arqueo_y_copia_cierre(self):
        """COMPRA y VENTA presenciales generan dos movimientos cada una, reflejados en arqueo y cierre."""
        compra = self.operacion_liquidacion()
        venta = self.operacion_liquidacion("VENTA")
        with mock.patch("pagos.stripe_provider.StripePaymentProvider.iniciar") as stripe:
            liquidar_transaccion(**self.argumentos_liquidacion(compra))
            liquidar_transaccion(**self.argumentos_liquidacion(venta))
            arqueo = self.arqueo()
            cierre = self.cierre()
            stripe.assert_not_called()
        for moneda, esperado in ((self.usd, Decimal("1200")), (self.pyg, Decimal("860"))):
            detalle = arqueo.detalles.get(moneda=moneda)
            copia = cierre.detalles.get(moneda=moneda)
            self.assertEqual(detalle.saldo_teorico, esperado)
            self.assertEqual(copia.saldo_teorico, esperado)
            self.assertEqual(copia.saldo_fisico, esperado)
            self.assertEqual(copia.diferencia, 0)
        self.assertEqual(MovimientoCaja.objects.count(), 4)


class CajaIntegracionHTTPTests(EscenarioLiquidacionHTTP, TestCase):
    def arqueo(self):
        return realizar_arqueo(
            periodo_id=self.periodo_liquidacion.pk, usuario_id=self.usuario_id, roles=["CAJERO"],
            saldos_fisicos=[{"moneda_id": m.pk, "monto": "1000"} for m in (self.usd, self.pyg)],
        )

    def test_cierre_http_redirige_a_historial_accesible(self):
        self.arqueo()
        respuesta = self.client.post(reverse("cajas:cierre", args=[self.periodo_liquidacion.pk]))
        self.assertRedirects(respuesta, reverse("cajas:historial", args=[self.caja_liquidacion.pk]))
        self.periodo_liquidacion.refresh_from_db()
        self.assertEqual(self.periodo_liquidacion.estado, "CERRADO")

    def test_historial_automaticos_conserva_trazabilidad(self):
        """El historial físico muestra referencia, motivo y origen de los movimientos presenciales."""
        liquidar_transaccion(**self.argumentos_liquidacion(self.operacion_http))
        respuesta = self.client.get(reverse("cajas:historial", args=[self.caja_liquidacion.pk]))
        movimiento = MovimientoCaja.objects.get(tipo="EGRESO")
        self.assertContains(respuesta, movimiento.referencia_externa)
        self.assertContains(respuesta, movimiento.motivo)
        self.assertContains(respuesta, movimiento.get_origen_display())
        self.assertContains(respuesta, "Referencia externa")
        self.assertTemplateUsed(respuesta, "frontend/partials/caja_contexto.html")

    def test_selector_vacio_incluye_caja_sin_periodo_abierto(self):
        self.arqueo()
        cerrar_caja(periodo_id=self.periodo_liquidacion.pk, usuario_id=self.usuario_id, roles=["CAJERO"])
        url = reverse("cajas:historial_selector")
        respuesta = self.client.get(url)
        self.assertContains(respuesta, 'value="">Seleccioná una Caja')
        self.assertContains(respuesta, self.caja_liquidacion.codigo)
        self.assertNotContains(respuesta, " selected")
        self.assertEqual(respuesta.content.count(b'aria-current="page"'), 1)
        self.assertRedirects(self.client.get(url, {"caja_id": self.caja_liquidacion.pk}),
                             reverse("cajas:historial", args=[self.caja_liquidacion.pk]))

    def test_selector_rechaza_caja_invalida_y_usuario(self):
        url = reverse("cajas:historial_selector")
        self.assertEqual(self.client.get(url, {"caja_id": "invalido"}).status_code, 400)
        sesion = self.client.session
        from usuarios.services.keycloak import SESSION_ROLES
        sesion[SESSION_ROLES] = ["USUARIO"]
        sesion.save()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_acciones_contextuales_sin_autoseleccion_y_solo_cajero(self):
        for ruta in ("cajas:saldos", "cajas:movimientos"):
            with self.subTest(ruta=ruta):
                self.assertNotContains(self.client.get(reverse(ruta)), "Realizar arqueo")
                respuesta = self.client.get(reverse(ruta), {"periodo_id": self.periodo_liquidacion.pk})
                self.assertContains(respuesta, "Realizar arqueo")
                self.assertContains(respuesta, "Cerrar caja")
                self.assertEqual(respuesta.content.count(b'aria-current="page"'), 1)

    def test_catalogo_previo_cierre_y_post_no_aplica_efectos(self):
        """Cerrar el período después de consultarlo impide el intercambio y conserva la operación pendiente."""
        catalogo = self.client.get(reverse("operaciones:periodos_liquidacion", args=[self.operacion_http.pk]))
        self.assertEqual(catalogo.status_code, 200)
        self.arqueo()
        cerrar_caja(periodo_id=self.periodo_liquidacion.pk, usuario_id=self.usuario_id, roles=["CAJERO"])
        with mock.patch("pagos.stripe_provider.StripePaymentProvider.iniciar") as stripe:
            self.assertEqual(self.post_liquidar().status_code, 400)
            stripe.assert_not_called()
        self.operacion_http.refresh_from_db()
        self.assertEqual(self.operacion_http.estado, "PENDIENTE")
        self.assertFalse(MovimientoCaja.objects.exists())
        catalogo = self.client.get(reverse("operaciones:periodos_liquidacion", args=[self.operacion_http.pk]))
        self.assertEqual(catalogo.json()["periodos"], [])


class CierreLiquidacionConcurrenciaTests(IntegracionArqueoMixin, TransactionTestCase):
    def _competir(self, *, cierre_primero, tipo):
        self.assertEqual(connection.vendor, "postgresql")
        operacion = self.operacion_liquidacion(tipo)
        self.arqueo()
        reservar, liberar, segundo_listo = Event(), Event(), Event()
        datos = {}
        original = caja_services._obtener_periodo_abierto

        def bloquear(*args, **kwargs):
            periodo = original(*args, **kwargs)
            if connection.connection.info.backend_pid == datos.get("primero") and not reservar.is_set():
                reservar.set()
                if not liberar.wait(10):
                    raise AssertionError("No se liberó el ganador de la prueba.")
            return periodo

        def ejecutar(nombre, accion):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    datos[nombre] = cursor.fetchone()[0]
                if nombre == "segundo":
                    segundo_listo.set()
                try:
                    return accion()
                except ValidationError as error:
                    return error
            finally:
                connections["default"].close()

        liquidar = lambda: liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        primero, segundo = (self.cierre, liquidar) if cierre_primero else (liquidar, self.cierre)
        with mock.patch.object(caja_services, "_obtener_periodo_abierto", side_effect=bloquear):
            with ThreadPoolExecutor(max_workers=2) as pool:
                ganador = pool.submit(ejecutar, "primero", primero)
                perdedor = None
                try:
                    self.assertTrue(reservar.wait(5))
                    perdedor = pool.submit(ejecutar, "segundo", segundo)
                    self.assertTrue(segundo_listo.wait(5))
                    limite = time.monotonic() + 5
                    while time.monotonic() < limite:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))",
                                           [datos["primero"], datos["segundo"]])
                            if cursor.fetchone()[0]:
                                break
                        time.sleep(.01)
                    else:
                        self.fail("El segundo servicio no esperó el lock real del primero.")
                finally:
                    liberar.set()
                resultado = ganador.result(15)
                self.assertNotIsInstance(resultado, ValidationError)
                error = perdedor.result(15)
                self.assertIsInstance(error, ValidationError)
        operacion.refresh_from_db()
        self.periodo_liquidacion.refresh_from_db()
        if cierre_primero:
            self.assertEqual(operacion.estado, "PENDIENTE")
            self.assertEqual(self.periodo_liquidacion.estado, "CERRADO")
            self.assertFalse(MovimientoCaja.objects.exists())
            self.assertFalse(Pago.objects.filter(transaccion=operacion).exists())
        else:
            self.assertEqual(operacion.estado, "COMPLETADA")
            self.assertEqual(self.periodo_liquidacion.estado, "ABIERTO")
            self.assertFalse(CierreCaja.objects.exists())
            self.assertEqual(MovimientoCaja.objects.count(), 2)
            self.assertIn("nuevo arqueo", " ".join(error.messages))

    def test_cierre_primero_compra(self):
        self._competir(cierre_primero=True, tipo="COMPRA")

    def test_cierre_primero_venta(self):
        self._competir(cierre_primero=True, tipo="VENTA")

    def test_liquidacion_primero_compra(self):
        self._competir(cierre_primero=False, tipo="COMPRA")

    def test_liquidacion_primero_venta(self):
        self._competir(cierre_primero=False, tipo="VENTA")
