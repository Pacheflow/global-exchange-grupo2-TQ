import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from threading import Barrier, Event
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cajas.models import Caja, MovimientoCaja, PeriodoCaja, SaldoInicialCaja
from cajas.services import registrar_movimiento_automatico
from clientes.models import CategoriaCliente, Cliente, UsuarioCliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from pagos.models import Pago
from pagos.providers import CodigoResultado, EstadoPago, PaymentProvider, ResultadoPago
from pagos.services import iniciar_pago, reintentar_pago
from tasas.models import TasaComercial
from tasas.services import actualizar_tasa_comercial
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import Transaccion
from .services import (
    cancelar_transaccion,
    crear_transaccion,
    listar_transacciones,
    liquidar_transaccion,
    previsualizar_operacion,
)
from .views import _serializar_transaccion


class EscenarioLiquidacion:
    """Fixtures locales de operación y Caja; no invocan proveedores externos."""

    def setUp(self):
        super().setUp()
        BaseOperacionesTests.setUp(self)
        self.caja_liquidacion = Caja.objects.create(
            codigo="LIQUIDACION", nombre="Caja liquidación",
            creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin",
        )
        self.periodo_liquidacion = PeriodoCaja.objects.create(
            caja=self.caja_liquidacion, responsable_keycloak_id=self.usuario_id,
        )
        for moneda in (self.usd, self.pyg):
            SaldoInicialCaja.objects.create(
                periodo=self.periodo_liquidacion, moneda=moneda, monto=Decimal("1000"),
            )

    def operacion_liquidacion(self, tipo="COMPRA"):
        return Transaccion.objects.create(
            clave_idempotencia=str(uuid.uuid4()), cliente=self.cliente,
            creado_por_keycloak_id=self.usuario_id, tipo=tipo,
            moneda_origen=self.usd, moneda_destino=self.pyg,
            monto_origen=Decimal("100"), monto_destino=Decimal("70"),
            tasa_comercial=self.tasa, tasa_aplicada=Decimal("1"),
            porcentaje_comision=Decimal("30"), importe_comision=Decimal("30"),
            metodo_pago=self.metodo_activo, metodo_pago_nombre=self.metodo_activo.nombre,
            estado="PENDIENTE",
        )

    def pago_liquidacion(self, operacion, estado=Pago.Estado.APROBADO):
        aprobado = estado == Pago.Estado.APROBADO
        return Pago.objects.create(
            transaccion=operacion, metodo_pago=self.metodo_activo, proveedor="stripe",
            monto=operacion.monto_origen, moneda_codigo=self.usd.codigo,
            base_importe=Pago.BaseImporte.ORIGEN, estado=estado,
            iniciado_por_keycloak_id=self.usuario_id,
            referencia_externa=f"pi_liquidacion{operacion.pk}" if aprobado else None,
            aprobado_en=timezone.now() if aprobado else None,
        )

    def argumentos_liquidacion(self, operacion, **cambios):
        datos = dict(
            transaccion_id=operacion.pk, periodo_id=self.periodo_liquidacion.pk,
            usuario_id=self.usuario_id, username=self.usuario_username,
            roles=["USUARIO"], cliente_seleccionado_id=self.cliente.pk,
        )
        datos.update(cambios)
        return datos

    def movimientos_previos(self, operacion, pago=None, *, monto_destino=None):
        """Prepara efectos idénticos ya confirmados para probar recuperación local."""
        datos = dict(
            periodo_id=self.periodo_liquidacion.pk, usuario_id=self.usuario_id,
            motivo="Efecto previo", referencia_externa=(
                pago.referencia_externa if pago else f"transaccion:{operacion.pk}"
            ),
        )
        prefijo = f"ge:hu28:transaccion:{operacion.pk}:caja:"
        if operacion.tipo == "VENTA":
            registrar_movimiento_automatico(
                **datos, tipo="INGRESO", moneda_id=self.usd.pk, monto=operacion.monto_origen,
                clave_idempotencia=f"{prefijo}ingreso-origen:v1",
            )
        registrar_movimiento_automatico(
            **datos, tipo="EGRESO", moneda_id=self.pyg.pk,
            monto=monto_destino or operacion.monto_destino,
            clave_idempotencia=f"{prefijo}egreso-destino:v1",
        )


class LiquidarTransaccionTests(EscenarioLiquidacion, TestCase):
    """Liquidación local, autorización, idempotencia y rollback de la obligación."""

    def test_compra_aprobada_registra_solo_egreso_destino(self):
        operacion = self.operacion_liquidacion()
        pago = self.pago_liquidacion(operacion)
        resultado = liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        self.assertFalse(resultado.repetida)
        self.assertEqual(resultado.transaccion.estado, "COMPLETADA")
        movimiento = MovimientoCaja.objects.get()
        self.assertEqual((movimiento.tipo, movimiento.moneda_id, movimiento.monto),
                         ("EGRESO", self.pyg.pk, operacion.monto_destino))
        self.assertEqual(movimiento.clave_idempotencia,
                         f"ge:hu28:transaccion:{operacion.pk}:caja:egreso-destino:v1")
        self.assertEqual(movimiento.referencia_externa, pago.referencia_externa)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)

    def test_compra_sin_pago_o_no_aprobado_no_liquida(self):
        for estado in (None, Pago.Estado.EN_PROCESO, Pago.Estado.ERROR,
                       Pago.Estado.RECHAZADO, Pago.Estado.INDETERMINADO):
            with self.subTest(estado=estado):
                operacion = self.operacion_liquidacion()
                if estado:
                    self.pago_liquidacion(operacion, estado)
                with self.assertRaises(ValidationError) as error:
                    liquidar_transaccion(**self.argumentos_liquidacion(operacion))
                self.assertEqual(error.exception.code, "PAGO_NO_APROBADO")
                operacion.refresh_from_db()
                self.assertEqual(operacion.estado, "PENDIENTE")
                self.assertFalse(MovimientoCaja.objects.exists())

    def test_compra_sin_saldo_conserva_pago_aprobado(self):
        operacion = self.operacion_liquidacion()
        pago = self.pago_liquidacion(operacion)
        SaldoInicialCaja.objects.filter(moneda=self.pyg).update(monto=0)
        with self.assertRaisesMessage(ValidationError, "insuficiente"):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        operacion.refresh_from_db()
        pago.refresh_from_db()
        self.assertEqual(operacion.estado, "PENDIENTE")
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)
        self.assertFalse(MovimientoCaja.objects.exists())

    def _repetir_sin_tocar_caja(self, tipo):
        operacion = self.operacion_liquidacion(tipo)
        if tipo == "COMPRA":
            self.pago_liquidacion(operacion)
        liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        ids = list(MovimientoCaja.objects.values_list("pk", flat=True))
        with mock.patch("operaciones.services.registrar_movimiento_automatico") as registrar:
            with mock.patch("cajas.services._obtener_periodo_abierto") as obtener:
                resultado = liquidar_transaccion(**self.argumentos_liquidacion(operacion, periodo_id=-1))
        self.assertTrue(resultado.repetida)
        registrar.assert_not_called()
        obtener.assert_not_called()
        self.assertCountEqual(MovimientoCaja.objects.values_list("pk", flat=True), ids)

    def test_compra_completada_reutiliza_sin_tocar_caja(self):
        self._repetir_sin_tocar_caja("COMPRA")

    def test_venta_registra_ambos_movimientos_y_completa(self):
        operacion = self.operacion_liquidacion("VENTA")
        resultado = liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        self.assertFalse(resultado.repetida)
        self.assertEqual(resultado.transaccion.estado, "COMPLETADA")
        self.assertFalse(Pago.objects.exists())
        self.assertCountEqual(
            MovimientoCaja.objects.values_list("tipo", "moneda_id", "monto", "clave_idempotencia"),
            [("INGRESO", self.usd.pk, operacion.monto_origen,
              f"ge:hu28:transaccion:{operacion.pk}:caja:ingreso-origen:v1"),
             ("EGRESO", self.pyg.pk, operacion.monto_destino,
              f"ge:hu28:transaccion:{operacion.pk}:caja:egreso-destino:v1")],
        )

    def test_venta_egreso_insuficiente_revierte_ingreso(self):
        operacion = self.operacion_liquidacion("VENTA")
        SaldoInicialCaja.objects.filter(moneda=self.pyg).update(monto=0)
        with self.assertRaisesMessage(ValidationError, "insuficiente"):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        operacion.refresh_from_db()
        self.assertEqual(operacion.estado, "PENDIENTE")
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_venta_completada_reutiliza_sin_tocar_caja(self):
        self._repetir_sin_tocar_caja("VENTA")

    def test_periodo_invalido_cerrado_o_moneda_ausente_no_deja_parciales(self):
        operacion = self.operacion_liquidacion("VENTA")
        with self.assertRaisesMessage(ValidationError, "no existe"):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion, periodo_id=-1))
        self.periodo_liquidacion.estado = "CERRADO"
        self.periodo_liquidacion.save(update_fields=["estado"])
        with self.assertRaisesMessage(ValidationError, "abierto"):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        self.periodo_liquidacion.estado = "ABIERTO"
        self.periodo_liquidacion.save(update_fields=["estado"])
        SaldoInicialCaja.objects.filter(moneda=self.pyg).delete()
        with self.assertRaisesMessage(ValidationError, "no pertenece"):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        operacion.refresh_from_db()
        self.assertEqual(operacion.estado, "PENDIENTE")
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_identidad_roles_cliente_y_asociacion_se_validan(self):
        operacion = self.operacion_liquidacion("VENTA")
        for cambios in (
            {"usuario_id": ""}, {"usuario_id": "otro"}, {"roles": ["ADMINISTRADOR", "CAJERO"]},
            {"roles": ["ANALISTA_CAMBIARIO"]}, {"roles": None},
            {"cliente_seleccionado_id": self.cliente.pk + 100},
        ):
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                liquidar_transaccion(**self.argumentos_liquidacion(operacion, **cambios))
        self.asociacion.activo = False
        self.asociacion.save()
        with self.assertRaises(ValidationError):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        self.asociacion.activo = True
        self.asociacion.save()
        self.cliente.estado = "INACTIVO"
        self.cliente.save()
        with self.assertRaises(ValidationError):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        operacion.refresh_from_db()
        self.assertEqual(operacion.estado, "PENDIENTE")
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_compra_rechaza_obligacion_distinta_del_pago(self):
        operacion = self.operacion_liquidacion()
        self.pago_liquidacion(operacion)
        operacion.monto_origen += Decimal("1")
        operacion.save(update_fields=["monto_origen"])
        with self.assertRaises(ValidationError) as error:
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        self.assertEqual(error.exception.code, "OBLIGACION_CAMBIADA")
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_conflicto_idempotencia_revierte_ingreso_nuevo(self):
        operacion = self.operacion_liquidacion("VENTA")
        # Solo existe un egreso anterior con payload incompatible.
        registrar_movimiento_automatico(
            periodo_id=self.periodo_liquidacion.pk, tipo="EGRESO", moneda_id=self.pyg.pk,
            monto="1", motivo="Previo", usuario_id=self.usuario_id,
            referencia_externa=f"transaccion:{operacion.pk}",
            clave_idempotencia=f"ge:hu28:transaccion:{operacion.pk}:caja:egreso-destino:v1",
        )
        with self.assertRaisesMessage(ValidationError, "otros datos"):
            liquidar_transaccion(**self.argumentos_liquidacion(operacion))
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        operacion.refresh_from_db()
        self.assertEqual(operacion.estado, "PENDIENTE")

    def test_pendiente_reutiliza_movimientos_identicos_y_completa(self):
        for tipo in ("COMPRA", "VENTA"):
            with self.subTest(tipo=tipo):
                operacion = self.operacion_liquidacion(tipo)
                pago = self.pago_liquidacion(operacion) if tipo == "COMPRA" else None
                self.movimientos_previos(operacion, pago)
                ids = list(MovimientoCaja.objects.values_list("pk", flat=True))
                resultado = liquidar_transaccion(**self.argumentos_liquidacion(operacion))
                self.assertFalse(resultado.repetida)
                self.assertEqual(resultado.transaccion.estado, "COMPLETADA")
                self.assertCountEqual(MovimientoCaja.objects.values_list("pk", flat=True), ids)

    def test_fallo_local_al_completar_revierte_todos_los_movimientos(self):
        for tipo in ("COMPRA", "VENTA"):
            with self.subTest(tipo=tipo):
                operacion = self.operacion_liquidacion(tipo)
                pago = self.pago_liquidacion(operacion) if tipo == "COMPRA" else None
                with mock.patch.object(Transaccion, "save", side_effect=RuntimeError("Fallo local")):
                    with self.assertRaises(RuntimeError):
                        liquidar_transaccion(**self.argumentos_liquidacion(operacion))
                operacion.refresh_from_db()
                self.assertEqual(operacion.estado, "PENDIENTE")
                self.assertFalse(MovimientoCaja.objects.exists())
                if pago:
                    pago.refresh_from_db()
                    self.assertEqual(pago.estado, Pago.Estado.APROBADO)


class LiquidarTransaccionConcurrenciaTests(EscenarioLiquidacion, TransactionTestCase):
    """Una Transacción serializa dos liquidadores reales antes de cualquier efecto."""

    def test_dos_liquidaciones_concurrentes_compra_y_venta_no_duplican(self):
        self.assertEqual(connection.vendor, "postgresql")
        for tipo in ("COMPRA", "VENTA"):
            with self.subTest(tipo=tipo):
                operacion = self.operacion_liquidacion(tipo)
                if tipo == "COMPRA":
                    self.pago_liquidacion(operacion)
                argumentos = self.argumentos_liquidacion(operacion)
                pids, barrera = Queue(), Barrier(3)

                def liquidar():
                    close_old_connections()
                    try:
                        with connections["default"].cursor() as cursor:
                            cursor.execute("SET lock_timeout = '10s'")
                            cursor.execute("SELECT pg_backend_pid()")
                            pids.put(cursor.fetchone()[0])
                        barrera.wait(timeout=5)
                        return liquidar_transaccion(**argumentos)
                    finally:
                        connections["default"].close()

                with ThreadPoolExecutor(max_workers=2) as ejecutor:
                    with transaction.atomic():
                        Transaccion.objects.select_for_update(of=("self",)).get(pk=operacion.pk)
                        futuros = [ejecutor.submit(liquidar) for _ in range(2)]
                        barrera.wait(timeout=5)
                        for _ in futuros:
                            pid = pids.get(timeout=5)
                            limite = time.monotonic() + 5
                            bloqueado = False
                            while time.monotonic() < limite:
                                with connection.cursor() as cursor:
                                    cursor.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid])
                                    bloqueado = cursor.fetchone()[0]
                                if bloqueado:
                                    break
                                time.sleep(0.01)
                            self.assertTrue(bloqueado, "El liquidador no esperó el lock real.")
                    resultados = [futuro.result(timeout=15) for futuro in futuros]
                self.assertCountEqual([resultado.repetida for resultado in resultados], [False, True])
                operacion.refresh_from_db()
                self.assertEqual(operacion.estado, "COMPLETADA")
                claves = [f"ge:hu28:transaccion:{operacion.pk}:caja:egreso-destino:v1"]
                if tipo == "VENTA":
                    claves.append(f"ge:hu28:transaccion:{operacion.pk}:caja:ingreso-origen:v1")
                self.assertEqual(MovimientoCaja.objects.filter(clave_idempotencia__in=claves).count(), len(claves))
        self.assertEqual(MovimientoCaja.objects.count(), 3)


class EscenarioLiquidacionHTTP(EscenarioLiquidacion):
    def setUp(self):
        super().setUp()
        self.operacion_http = self.operacion_liquidacion()
        self.pago_http = self.pago_liquidacion(self.operacion_http)
        self.url_liquidar = reverse("operaciones:liquidar_transaccion", args=[self.operacion_http.pk])
        self.autenticar_liquidacion(self.client)

    def autenticar_liquidacion(self, cliente_http):
        sesion = cliente_http.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = time.time() + 600
        sesion[SESSION_ROLES] = ["USUARIO"]
        sesion[SESSION_USUARIO] = {"sub": self.usuario_id, "preferred_username": self.usuario_username}
        sesion["selected_client"] = {"id": self.cliente.pk}
        sesion.save()

    def post_liquidar(self, **datos):
        return self.client.post(self.url_liquidar, {"periodo_id": self.periodo_liquidacion.pk, **datos},
                                content_type="application/json")


class LiquidacionHTTPTests(EscenarioLiquidacionHTTP, TestCase):
    """Contrato y mapeo HTTP; los tests del coordinador cubren atomicidad profunda."""

    def test_compra_liquida_y_devuelve_solo_resultado_controlado(self):
        respuesta = self.post_liquidar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {
            "transaccion_id": self.operacion_http.pk, "estado": "COMPLETADA", "repetida": False,
        })

    def test_venta_liquida_correctamente(self):
        operacion = self.operacion_liquidacion("VENTA")
        self.url_liquidar = reverse("operaciones:liquidar_transaccion", args=[operacion.pk])
        respuesta = self.post_liquidar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"transaccion_id": operacion.pk, "estado": "COMPLETADA", "repetida": False})

    def test_repeticion_devuelve_repetida(self):
        self.assertEqual(self.post_liquidar().status_code, 200)
        respuesta = self.post_liquidar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["repetida"])

    def test_body_vacio_malformado_lista_o_sin_periodo_se_rechaza(self):
        with mock.patch("operaciones.views.liquidar_transaccion") as servicio:
            for cuerpo in ("", "{", "[]", "null", "{}"):
                with self.subTest(cuerpo=cuerpo):
                    respuesta = self.client.post(self.url_liquidar, cuerpo, content_type="application/json")
                    self.assertEqual(respuesta.status_code, 400)
            respuesta = self.client.post(self.url_liquidar, {"periodo_id": 1})
            self.assertEqual(respuesta.status_code, 400)
        servicio.assert_not_called()

    def test_campos_extra_incluidos_importes_y_monedas_se_rechazan(self):
        with mock.patch("operaciones.views.liquidar_transaccion") as servicio:
            for campo in ("monto", "moneda", "tipo", "caja_id", "pago_id", "provider",
                          "referencia_externa", "estado", "otro"):
                with self.subTest(campo=campo):
                    self.assertEqual(self.post_liquidar(**{campo: "inyectado"}).status_code, 400)
        servicio.assert_not_called()

    def test_periodo_debe_ser_entero_positivo_sin_aceptar_booleanos(self):
        with mock.patch("operaciones.views.liquidar_transaccion") as servicio:
            for valor in (0, -1, True, False, None, "1", 1.5, [], {}):
                with self.subTest(valor=valor):
                    self.assertEqual(self.post_liquidar(periodo_id=valor).status_code, 400)
        servicio.assert_not_called()

    def test_contexto_sin_cliente_o_invalido_es_400(self):
        for seleccion in (None, {}, {"id": "1"}, {"id": True}, {"id": -1}):
            with self.subTest(seleccion=seleccion):
                sesion = self.client.session
                sesion["selected_client"] = seleccion
                sesion.save()
                with mock.patch("operaciones.views.liquidar_transaccion") as servicio:
                    self.assertEqual(self.post_liquidar().status_code, 400)
                servicio.assert_not_called()

    def test_no_autorizada_e_inexistente_devuelven_mismo_404(self):
        sesion = self.client.session
        sesion[SESSION_USUARIO] = {"sub": "sin-asociacion"}
        sesion.save()
        denegada = self.post_liquidar()
        self.autenticar_liquidacion(self.client)
        inexistente = self.client.post(
            reverse("operaciones:liquidar_transaccion", args=[999999]),
            {"periodo_id": self.periodo_liquidacion.pk}, content_type="application/json",
        )
        self.assertEqual(denegada.status_code, 404)
        self.assertEqual(inexistente.status_code, 404)
        self.assertEqual(denegada.json(), inexistente.json())
        sesion = self.client.session
        sesion["selected_client"] = {"id": self.cliente.pk + 100}
        sesion.save()
        self.assertEqual(self.post_liquidar().json(), inexistente.json())
        with mock.patch("operaciones.views.liquidar_transaccion", side_effect=PermissionDenied("Interno")):
            self.assertEqual(self.post_liquidar().json(), inexistente.json())

    def test_saldo_insuficiente_es_400_controlado(self):
        SaldoInicialCaja.objects.filter(moneda=self.pyg).update(monto=0)
        respuesta = self.post_liquidar()
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["codigo"], "SALDO_INSUFICIENTE")

    def test_compra_sin_pago_aprobado_es_400(self):
        operacion = self.operacion_liquidacion()
        self.url_liquidar = reverse("operaciones:liquidar_transaccion", args=[operacion.pk])
        self.pago_liquidacion(operacion, Pago.Estado.ERROR)
        respuesta = self.post_liquidar()
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["codigo"], "PAGO_NO_APROBADO")

    def test_periodo_cerrado_o_inexistente_es_400_controlado(self):
        respuesta = self.post_liquidar(periodo_id=999999)
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["codigo"], "PERIODO_NO_DISPONIBLE")
        self.periodo_liquidacion.estado = "CERRADO"
        self.periodo_liquidacion.save(update_fields=["estado"])
        respuesta = self.post_liquidar()
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["codigo"], "PERIODO_NO_DISPONIBLE")

    def test_conflicto_idempotencia_es_409(self):
        self.movimientos_previos(self.operacion_http, self.pago_http, monto_destino=Decimal("1"))
        respuesta = self.post_liquidar()
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["codigo"], "CONFLICTO_IDEMPOTENCIA")

    def test_errores_desconocidos_no_filtran_detalles(self):
        for error, status in ((RuntimeError("detalle privado"), 500),
                              (ValidationError("detalle privado"), 500)):
            with self.subTest(status=status), mock.patch("operaciones.views.liquidar_transaccion", side_effect=error):
                respuesta = self.post_liquidar()
                self.assertEqual(respuesta.status_code, status)
                self.assertEqual(respuesta.json(), {"error": "No se pudo liquidar la operación."})
                self.assertNotContains(respuesta, "detalle privado", status_code=status)

    def test_autenticacion_roles_metodo_y_csrf_se_conservan(self):
        anonimo = Client()
        self.assertEqual(anonimo.post(self.url_liquidar, {}, content_type="application/json").status_code, 401)
        self.assertEqual(self.client.get(self.url_liquidar).status_code, 405)
        sesion = self.client.session
        sesion[SESSION_ROLES] = ["ADMINISTRADOR", "CAJERO"]
        sesion.save()
        self.assertEqual(self.post_liquidar().status_code, 403)
        estricto = Client(enforce_csrf_checks=True)
        self.autenticar_liquidacion(estricto)
        self.assertEqual(estricto.post(self.url_liquidar, {"periodo_id": 1}, content_type="application/json").status_code, 403)

    def test_delega_contexto_servidor_sin_llamar_stripe(self):
        with mock.patch("operaciones.views.liquidar_transaccion", wraps=liquidar_transaccion) as servicio:
            with mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as stripe_cliente:
                with mock.patch("pagos.views.obtener_payment_provider") as proveedor:
                    self.assertEqual(self.post_liquidar().status_code, 200)
        servicio.assert_called_once_with(
            transaccion_id=self.operacion_http.pk, periodo_id=self.periodo_liquidacion.pk,
            usuario_id=self.usuario_id, username=self.usuario_username,
            roles=["USUARIO"], cliente_seleccionado_id=self.cliente.pk,
        )
        stripe_cliente.assert_not_called()
        proveedor.assert_not_called()


class LiquidacionHTTPAtomicidadTests(EscenarioLiquidacionHTTP, TransactionTestCase):
    def test_view_invoca_coordinador_sin_transaccion_externa(self):
        def ejecutar(**argumentos):
            self.assertFalse(connection.in_atomic_block)
            return liquidar_transaccion(**argumentos)
        with mock.patch("operaciones.views.liquidar_transaccion", side_effect=ejecutar):
            self.assertEqual(self.post_liquidar().status_code, 200)


class PeriodosLiquidacionHTTPTests(EscenarioLiquidacionHTTP, TestCase):
    """Catálogo elegible, permisos e invariantes de solo lectura."""

    def setUp(self):
        super().setUp()
        self.url_periodos = reverse("operaciones:periodos_liquidacion", args=[self.operacion_http.pk])

    def test_compra_aprobada_devuelve_contrato_minimo(self):
        respuesta = self.client.get(self.url_periodos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {
            "transaccion_id": self.operacion_http.pk,
            "periodos": [{"periodo_id": self.periodo_liquidacion.pk, "estado": "ABIERTO",
                          "caja": {"id": self.caja_liquidacion.pk, "codigo": self.caja_liquidacion.codigo,
                                   "nombre": self.caja_liquidacion.nombre}}],
        })

    def test_venta_pendiente_no_requiere_pago(self):
        operacion = self.operacion_liquidacion("VENTA")
        self.assertFalse(Pago.objects.filter(transaccion=operacion).exists())
        respuesta = self.client.get(reverse("operaciones:periodos_liquidacion", args=[operacion.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["transaccion_id"], operacion.pk)
        self.assertEqual(respuesta.json()["periodos"][0]["periodo_id"], self.periodo_liquidacion.pk)

    def test_caja_deshabilitada_no_aparece(self):
        self.caja_liquidacion.estado = "DESHABILITADA"
        self.caja_liquidacion.save(update_fields=["estado"])
        respuesta = self.client.get(self.url_periodos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["periodos"], [])

    def test_periodo_cerrado_no_aparece(self):
        self.periodo_liquidacion.estado = "CERRADO"
        self.periodo_liquidacion.save(update_fields=["estado"])
        respuesta = self.client.get(self.url_periodos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["periodos"], [])

    def test_sin_periodos_devuelve_lista_vacia(self):
        SaldoInicialCaja.objects.all().delete()
        self.periodo_liquidacion.delete()
        respuesta = self.client.get(self.url_periodos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"transaccion_id": self.operacion_http.pk, "periodos": []})

    def test_compra_sin_pago_o_no_aprobado_no_obtiene_catalogo(self):
        for estado in (None, Pago.Estado.ERROR, Pago.Estado.RECHAZADO,
                       Pago.Estado.EN_PROCESO, Pago.Estado.INDETERMINADO):
            with self.subTest(estado=estado):
                operacion = self.operacion_liquidacion()
                if estado:
                    self.pago_liquidacion(operacion, estado)
                respuesta = self.client.get(reverse("operaciones:periodos_liquidacion", args=[operacion.pk]))
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.json()["codigo"], "PAGO_NO_APROBADO")
                self.assertNotIn("periodos", respuesta.json())

    def test_completada_y_cancelada_no_obtienen_catalogo(self):
        for estado in ("COMPLETADA", "CANCELADA"):
            with self.subTest(estado=estado):
                datos = {"estado": estado}
                if estado == "CANCELADA":
                    datos.update(cancelado_por_keycloak_id=self.usuario_id,
                                 cancelado_por_username=self.usuario_username,
                                 cancelado_en=timezone.now(), motivo_cancelacion="Cancelación de prueba")
                Transaccion.objects.filter(pk=self.operacion_http.pk).update(**datos)
                respuesta = self.client.get(self.url_periodos)
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.json()["codigo"], "OPERACION_NO_PENDIENTE")
                self.assertNotIn("periodos", respuesta.json())

    def test_cliente_no_seleccionado_o_malformado_es_400(self):
        for seleccion in (None, {}, {"id": "1"}, {"id": True}, {"id": 0}):
            with self.subTest(seleccion=seleccion):
                sesion = self.client.session
                sesion["selected_client"] = seleccion
                sesion.save()
                self.assertEqual(self.client.get(self.url_periodos).status_code, 400)

    def test_no_autorizada_e_inexistente_son_indistinguibles(self):
        inexistente = self.client.get(reverse("operaciones:periodos_liquidacion", args=[999999]))
        self.assertEqual(inexistente.status_code, 404)
        self.asociacion.activo = False
        self.asociacion.save()
        denegada = self.client.get(self.url_periodos)
        self.assertEqual(denegada.status_code, 404)
        self.assertEqual(denegada.json(), inexistente.json())
        self.asociacion.activo = True
        self.asociacion.save()
        sesion = self.client.session
        sesion[SESSION_USUARIO] = {"sub": "sin-asociacion"}
        sesion.save()
        denegada = self.client.get(self.url_periodos)
        self.assertEqual(denegada.status_code, 404)
        self.assertEqual(denegada.json(), inexistente.json())

    def test_get_solo_lee_sin_locks_saldos_ni_proveedor(self):
        # Cero fondos no excluye un período: este catálogo no autoriza el egreso.
        SaldoInicialCaja.objects.all().update(monto=0)
        with mock.patch("operaciones.views.liquidar_transaccion") as liquidar:
            with mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as stripe_cliente:
                with CaptureQueriesContext(connection) as consultas:
                    respuesta = self.client.get(self.url_periodos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.json()["periodos"]), 1)
        self.assertTrue(consultas.captured_queries)
        for consulta in consultas.captured_queries:
            sql = consulta["sql"].lstrip().upper()
            self.assertNotIn("FOR UPDATE", sql)
            self.assertFalse(sql.startswith(("INSERT", "UPDATE", "DELETE")), sql)
            self.assertNotIn("CAJAS_SALDOINICIALCAJA", sql)
            self.assertNotIn("CAJAS_MOVIMIENTOCAJA", sql)
        liquidar.assert_not_called()
        stripe_cliente.assert_not_called()

    def test_autenticacion_roles_y_metodo(self):
        self.assertEqual(Client().get(self.url_periodos).status_code, 401)
        self.assertEqual(self.client.post(self.url_periodos).status_code, 405)
        for roles, status in ((["CAJERO"], 200), (["USUARIO"], 200),
                              (["ADMINISTRADOR", "CAJERO"], 403), (["ANALISTA_CAMBIARIO"], 403)):
            with self.subTest(roles=roles):
                sesion = self.client.session
                sesion[SESSION_ROLES] = roles
                sesion.save()
                self.assertEqual(self.client.get(self.url_periodos).status_code, status)

    def test_error_inesperado_es_500_generico(self):
        with mock.patch("operaciones.views.obtener_detalle_transaccion", side_effect=RuntimeError("Interno")):
            respuesta = self.client.get(self.url_periodos)
        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(respuesta.json(), {"error": "No se pudieron consultar los períodos de liquidación."})


class BaseOperacionesTests(TestCase):
    """Base común con el escenario de una operación de cambio."""

    def setUp(self):
        self.usuario_id = "usuario-keycloak-123"
        self.usuario_username = "operador"

        self.categoria = CategoriaCliente.objects.get_or_create(
            nombre="Minorista",
        )[0]
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente de prueba",
            tipo_persona="FISICA",
            documento="123456",
            estado="ACTIVO",
            categoria=self.categoria,
        )
        self.asociacion = UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        self.usd = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar", "simbolo": "$"},
        )[0]
        self.pyg = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní", "simbolo": "Gs."},
        )[0]
        self.otra = Moneda.objects.get_or_create(
            codigo="EUR",
            defaults={"nombre": "Euro", "simbolo": "€"},
        )[0]

        self.metodo_activo = MetodoPago.objects.create(
            nombre="Efectivo",
            activo=True,
        )
        self.metodo_inactivo = MetodoPago.objects.create(
            nombre="Cheque",
            activo=False,
        )

        self.tasa = TasaComercial.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal("7000.000000"),
            venta=Decimal("7250.000000"),
            vigente=True,
            usuario_id=self.usuario_id,
            usuario_username=self.usuario_username,
        )

    def clave_idempotencia(self):
        """Devuelve una clave única de idempotencia para cada ejecución."""
        return str(uuid.uuid4())

    def parametros_preview(self, **datos):
        """Devuelve parámetros válidos para una previsualización."""
        valores = {
            "usuario_id": self.usuario_id,
            "usuario_username": self.usuario_username,
            "cliente_id": self.cliente.id,
            "tipo": "COMPRA",
            "moneda_origen_id": self.usd.id,
            "moneda_destino_id": self.pyg.id,
            "monto": "100",
            "metodo_pago_id": self.metodo_activo.id,
        }
        valores.update(datos)
        return valores

    def previsualizar(self, **datos):
        """Invoca el servicio de previsualización con parámetros base."""
        return previsualizar_operacion(**self.parametros_preview(**datos))

    def parametros_crear(self, **datos):
        """Devuelve parámetros válidos para confirmar una operación."""
        valores = self.parametros_preview(**datos)
        valores.setdefault("clave_idempotencia", self.clave_idempotencia())
        valores.setdefault("version_preview", self.tasa.version)
        valores.setdefault("categoria_preview_id", self.cliente.categoria_id)
        valores.setdefault(
            "porcentaje_comision_preview",
            self.categoria.porcentaje_comision,
        )
        return valores

    def crear(self, **datos):
        """Invoca el servicio de confirmación con parámetros base."""
        return crear_transaccion(**self.parametros_crear(**datos))

    def actualizar_cotizacion(self, compra="7600.000000", venta="7800.000000"):
        """Registra una nueva versión vigente de la tasa del par."""
        self.tasa = actualizar_tasa_comercial(
            moneda_origen_id=self.usd.id,
            moneda_destino_id=self.pyg.id,
            usuario_id=self.usuario_id,
            usuario_username=self.usuario_username,
            compra=Decimal(compra),
            venta=Decimal(venta),
        )
        return self.tasa


class PrevisualizarOperacionTests(BaseOperacionesTests):
    """Pruebas del servicio de previsualización de operaciones."""

    def test_compra_utiliza_tasa_de_compra(self):
        """Comprueba que una operación de compra utilice la tasa de compra.
        Se espera que el cálculo aplique el valor de compra vigente del par.
        """
        resultado = self.previsualizar()

        self.assertEqual(resultado.tasa, Decimal("7000.000000"))
        self.assertEqual(resultado.monto_convertido, Decimal("700000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("630000.000000"))

    def test_venta_utiliza_tasa_de_venta(self):
        """Comprueba que una operación de venta utilice la tasa de venta.
        Se espera que el cálculo aplique el valor de venta vigente del par.
        """
        resultado = self.previsualizar(tipo="VENTA")

        self.assertEqual(resultado.tasa, Decimal("7250.000000"))
        self.assertEqual(resultado.monto_convertido, Decimal("725000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("652500.000000"))

    def test_preview_expone_version_de_tasa(self):
        """Comprueba que la previsualización exponga la versión de la tasa.
        Se espera que la versión mostrada para confirmar sea la vigente.
        """
        resultado = self.previsualizar()

        self.assertIsInstance(resultado.tasa_comercial.version, int)
        self.assertEqual(resultado.tasa_comercial.version, self.tasa.version)

    def test_tasa_redondeada_es_la_misma_que_se_calcula_y_persiste(self):
        """La tasa visible, calculada y guardada debe ser idéntica."""

        self.tasa.compra = Decimal("5846.292042")
        self.tasa.save(update_fields=["compra"])

        preview = self.previsualizar(monto="1")
        creada = self.crear(monto="1").transaccion

        self.assertEqual(preview.tasa, Decimal("5846"))
        self.assertEqual(preview.monto_convertido, Decimal("5846.000000"))
        self.assertEqual(creada.tasa_aplicada, Decimal("5846"))
        self.assertEqual(creada.monto_destino, preview.monto_destino)

    def test_calculo_utiliza_decimal_exacto(self):
        """Comprueba que el cálculo de la conversión utilice Decimal.

        Se espera que los montos calculados sean Decimal y exactos.
        """
        resultado = self.previsualizar(monto="100.50")

        self.assertIsInstance(resultado.monto_origen, Decimal)
        self.assertIsInstance(resultado.tasa, Decimal)
        self.assertIsInstance(resultado.monto_convertido, Decimal)
        self.assertIsInstance(resultado.monto_destino, Decimal)
        self.assertEqual(resultado.monto_convertido, Decimal("703500.000000"))
        self.assertEqual(resultado.importe_comision, Decimal("70350.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("633150.000000"))

    def test_cliente_inexistente_es_rechazado(self):
        """Comprueba que un cliente inexistente sea rechazado.

        Se espera que la operación sea rechazada.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(cliente_id=999999)

    def test_cliente_inactivo_es_rechazado(self):
        """Comprueba que un cliente inactivo no admita operaciones.

        Se espera que la operación sea rechazada.
        """
        self.cliente.estado = "INACTIVO"
        self.cliente.save(update_fields=["estado"])

        with self.assertRaises(ValidationError):
            self.previsualizar()

    def test_usuario_sin_clientes_es_rechazado(self):
        """Comprueba que un usuario sin clientes no pueda operar.

        Se espera que la operación sea rechazada por falta de autorización.

        Requisito relacionado: RNF-02.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(
                usuario_id="usuario-keycloak-sin-clientes",
            )

    def test_cliente_no_autorizado_es_rechazado(self):
        """Comprueba que un usuario no pueda operar con un cliente no autorizado.

        Se espera que la operación sea rechazada.

        Requisito relacionado: RNF-02.
        """
        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente ajeno",
            tipo_persona="JURIDICA",
            documento="654321",
            estado="ACTIVO",
            categoria=self.categoria,
        )

        with self.assertRaises(ValidationError):
            self.previsualizar(cliente_id=cliente_ajeno.id)

    def test_asociacion_inactiva_es_rechazada(self):
        """Comprueba que una asociación desactivada no admita operaciones.

        Se espera que la operación sea rechazada.

        Requisito relacionado: RNF-02.
        """
        self.asociacion.activo = False
        self.asociacion.save(update_fields=["activo"])

        with self.assertRaises(ValidationError):
            self.previsualizar()

    def test_moneda_inactiva_es_rechazada(self):
        """Comprueba que una moneda inactiva no admita operaciones.

        Se espera que la operación sea rechazada.
        """
        self.pyg.estado = "INACTIVA"
        self.pyg.save(update_fields=["estado"])

        with self.assertRaises(ValidationError):
            self.previsualizar()

    def test_metodo_pago_inactivo_es_rechazado(self):
        """Comprueba que un método de pago inactivo sea rechazado.

        Se espera que la operación sea rechazada.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(metodo_pago_id=self.metodo_inactivo.id)

    def test_metodo_preferido_inactivo_obliga_elegir_otro(self):
        """Comprueba que el método preferido inactivo no sea usable.

        Se espera que la operación con el preferido inactivo sea rechazada
        y que elegir otro método activo sea válido.
        """
        self.cliente.metodo_pago_preferido = self.metodo_inactivo
        self.cliente.save(update_fields=["metodo_pago_preferido"])

        with self.assertRaises(ValidationError):
            self.previsualizar(metodo_pago_id=self.metodo_inactivo.id)

        resultado = self.previsualizar()
        self.assertEqual(resultado.metodo_pago.id, self.metodo_activo.id)

    def test_tasa_no_disponible_impide_preview(self):
        """Comprueba que sin tasa comercial vigente la operación sea rechazada.

        Se espera que la previsualización no se realice.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(moneda_destino_id=self.otra.id)

    def test_preview_no_crea_transaccion(self):
        """Comprueba que la previsualización no registre transacciones.

        Se espera que no exista ninguna transacción tras la previsualización.
        """
        self.previsualizar()

        self.assertEqual(Transaccion.objects.count(), 0)


class ComisionPorCategoriaTests(BaseOperacionesTests):
    """Pruebas de la comisión según la categoría del cliente."""

    def _previsualizar_con_categoria(self, nombre_categoria, documento, monto="100"):
        """Previsualiza una compra para un cliente de la categoría indicada."""
        categoria = CategoriaCliente.objects.get_or_create(
            nombre=nombre_categoria,
        )[0]
        cliente = Cliente.objects.create(
            nombre_razon_social=f"Cliente {nombre_categoria}",
            tipo_persona="JURIDICA",
            documento=documento,
            estado="ACTIVO",
            categoria=categoria,
        )
        UsuarioCliente.objects.create(
            cliente=cliente,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        return self.previsualizar(cliente_id=cliente.id, monto=monto)

    def test_comision_minorista_diez_porciento(self):
        """Comprueba que la categoría Minorista aplique 10 por ciento.

        Con 100 unidades a tasa 7000 el importe de comisión debe ser 70000.
        """
        resultado = self._previsualizar_con_categoria(
            "Minorista",
            documento="111111",
        )

        self.assertEqual(resultado.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(resultado.importe_comision, Decimal("70000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("630000.000000"))

    def test_comision_corporativo_siete_porciento(self):
        """Comprueba que la categoría Corporativo aplique 7 por ciento.

        Con 100 unidades a tasa 7000 el importe de comisión debe ser 49000.
        """
        resultado = self._previsualizar_con_categoria(
            "Corporativo",
            documento="222222",
        )

        self.assertEqual(resultado.porcentaje_comision, Decimal("7.00"))
        self.assertEqual(resultado.importe_comision, Decimal("49000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("651000.000000"))

    def test_comision_vip_cinco_porciento(self):
        """Comprueba que la categoría VIP aplique 5 por ciento.

        Con 100 unidades a tasa 7000 el importe de comisión debe ser 35000.
        """
        resultado = self._previsualizar_con_categoria(
            "VIP",
            documento="333333",
        )

        self.assertEqual(resultado.porcentaje_comision, Decimal("5.00"))
        self.assertEqual(resultado.importe_comision, Decimal("35000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("665000.000000"))

    def test_comision_se_descunta_del_monto_convertido(self):
        """Comprueba que el monto destino reste la comisión del convertido.

        Se espera que monto_destino sea monto_convertido menos la comisión.
        """
        resultado = self.previsualizar()

        self.assertTrue(
            resultado.monto_destino
            == resultado.monto_convertido - resultado.importe_comision
        )
        self.assertEqual(
            resultado.porcentaje_comision,
            Decimal("10.00"),
        )

    def test_cliente_sin_categoria_es_rechazado(self):
        """Comprueba que un cliente sin categoría no admita operaciones.

        Se espera que la operación sea rechazada sin aplicar comisión 0.
        """
        cliente_sin_categoria = Cliente.objects.create(
            nombre_razon_social="Cliente sin categoría",
            tipo_persona="FISICA",
            documento="444444",
            estado="ACTIVO",
        )
        UsuarioCliente.objects.create(
            cliente=cliente_sin_categoria,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        with self.assertRaises(ValidationError):
            self.previsualizar(cliente_id=cliente_sin_categoria.id)

    def test_comision_configurada_se_aplica_a_nuevas_operaciones(self):
        """La comisión persistida reemplaza cualquier valor fijo por nombre."""

        self.categoria.porcentaje_comision = Decimal("3.50")
        self.categoria.save(update_fields=["porcentaje_comision"])

        resultado = self.previsualizar()

        self.assertEqual(resultado.porcentaje_comision, Decimal("3.50"))
        self.assertEqual(resultado.importe_comision, Decimal("24500.000000"))


class CrearTransaccionTests(BaseOperacionesTests):
    """Pruebas de la confirmación y persistencia de operaciones."""

    def test_confirmacion_crea_transaccion_pendiente(self):
        """Comprueba que confirmar una operación cree una transacción PENDIENTE.

        La confirmación comercial registra la operación sin completarla.
        """
        resultado = self.crear()

        self.assertFalse(resultado.repetida)
        self.assertFalse(resultado.cambio_cotizacion)
        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_confirmacion_guarda_snapshots(self):
        """Comprueba que la transacción guarde los snapshots de la operación.

        Se espera que monto, tasas, comisión y método queden persistidos.
        """
        resultado = self.crear()
        transaccion = resultado.transaccion

        self.assertEqual(transaccion.cliente_id, self.cliente.id)
        self.assertEqual(transaccion.moneda_origen_id, self.usd.id)
        self.assertEqual(transaccion.moneda_destino_id, self.pyg.id)
        self.assertEqual(transaccion.monto_origen, Decimal("100.000000"))
        self.assertEqual(transaccion.monto_destino, Decimal("630000.000000"))
        self.assertEqual(transaccion.tasa_comercial_id, self.tasa.id)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7000.000000"))
        self.assertEqual(transaccion.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(transaccion.importe_comision, Decimal("70000.000000"))
        self.assertEqual(transaccion.metodo_pago_id, self.metodo_activo.id)
        self.assertEqual(transaccion.metodo_pago_nombre, "Efectivo")
        self.assertEqual(transaccion.creado_por_keycloak_id, self.usuario_id)
        self.assertEqual(transaccion.creado_por_username, self.usuario_username)

    def test_confirmacion_venta_utiliza_tasa_de_venta(self):
        """Comprueba que confirmar una venta aplique la tasa de venta.

        Se espera que la transacción quede pendiente con la tasa de venta.
        """
        resultado = self.crear(tipo="VENTA")

        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")
        self.assertEqual(
            resultado.transaccion.tasa_aplicada,
            Decimal("7250.000000"),
        )

    def test_metodo_pago_inactivo_es_rechazado(self):
        """Comprueba que confirmar con método inactivo sea rechazado.

        Se espera que no se cree ninguna transacción.
        """
        with self.assertRaises(ValidationError):
            self.crear(metodo_pago_id=self.metodo_inactivo.id)

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_cambio_cotizacion_rechaza_sin_crear_transaccion(self):
        """Comprueba que un cambio de cotización rechace la operación.

        Si la versión de la tasa cambió desde la previsualización, la
        solicitud debe fallar sin dejar una transacción inválida.
        """
        version_original = self.tasa.version
        self.actualizar_cotizacion()

        with self.assertRaises(ValidationError):
            self.crear(version_preview=version_original)

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_misma_version_no_cancela_aunque_cambie_el_valor(self):
        """Comprueba que con la misma versión la operación continúe.

        Solo la versión de la tasa define el cambio de cotización; un
        cambio de valor con la misma versión no debe cancelar la operación.
        """
        self.tasa.compra = Decimal("7100.000000")
        self.tasa.save(update_fields=["compra"])

        resultado = self.crear(version_preview=self.tasa.version)

        self.assertFalse(resultado.cambio_cotizacion)
        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")
        self.assertEqual(
            resultado.transaccion.tasa_aplicada,
            Decimal("7100.000000"),
        )

    def test_version_distinta_rechaza_aunque_tasa_coincida(self):
        """Comprueba que la decisión dependa de la versión, no del valor.

        Aunque el valor de tasa_preview coincida con la tasa actual, una
        versión distinta debe rechazar la operación.
        """
        version_original = self.tasa.version
        self.actualizar_cotizacion()

        with self.assertRaises(ValidationError):
            self.crear(
                version_preview=version_original,
                tasa_preview=self.tasa.compra,
            )

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_version_invalida_es_rechazada(self):
        """Comprueba que una versión de preview inválida sea rechazada.

        Sin una versión de la tasa no se puede decidir el cambio de
        cotización; la operación debe ser rechazada sin registrar nada.
        """
        for invalida in (None, "", "abc", "0"):
            with self.assertRaises(ValidationError):
                self.crear(version_preview=invalida)

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_cotizacion_no_disponible_no_crea_transaccion(self):
        """Comprueba que sin cotización vigente no se cree la transacción.

        Se espera que la operación sea rechazada sin registrar nada.
        """
        self.tasa.vigente = False
        self.tasa.save(update_fields=["vigente"])

        with self.assertRaises(ValidationError):
            self.crear()

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_cambio_de_porcentaje_desde_preview_rechaza_confirmacion(self):
        """Un cambio de comisión exige generar una nueva previsualización."""

        preview = self.previsualizar()
        self.categoria.porcentaje_comision = Decimal("3.00")
        self.categoria.save(update_fields=["porcentaje_comision"])

        with self.assertRaises(ValidationError):
            self.crear(
                categoria_preview_id=preview.cliente.categoria_id,
                porcentaje_comision_preview=preview.porcentaje_comision,
            )

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_cambio_de_categoria_desde_preview_rechaza_confirmacion(self):
        """Una recategorización exige generar una nueva previsualización."""

        preview = self.previsualizar()
        nueva_categoria = CategoriaCliente.objects.get_or_create(
            nombre="VIP",
            defaults={"porcentaje_comision": Decimal("5.00")},
        )[0]
        self.cliente.categoria = nueva_categoria
        self.cliente.save(update_fields=["categoria"])

        with self.assertRaises(ValidationError):
            self.crear(
                categoria_preview_id=preview.cliente.categoria_id,
                porcentaje_comision_preview=preview.porcentaje_comision,
            )

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_preview_sin_cambios_confirma_con_configuracion_vigente(self):
        """La huella intacta permite registrar la operación pendiente."""

        preview = self.previsualizar()
        resultado = self.crear(
            categoria_preview_id=preview.cliente.categoria_id,
            porcentaje_comision_preview=preview.porcentaje_comision,
        )

        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")
        self.assertEqual(
            resultado.transaccion.porcentaje_comision,
            self.categoria.porcentaje_comision,
        )

    def test_porcentaje_preview_manipulado_no_altera_el_calculo(self):
        """El porcentaje enviado es una huella y nunca una entrada de cálculo."""

        with self.assertRaises(ValidationError):
            self.crear(porcentaje_comision_preview="0.00")

        self.assertEqual(Transaccion.objects.count(), 0)


def _crear_pago_cancelacion(transaccion, estado):
    return Pago.objects.create(
        transaccion=transaccion, metodo_pago=transaccion.metodo_pago, proveedor="stripe",
        monto=transaccion.monto_origen, moneda_codigo=transaccion.moneda_origen.codigo,
        base_importe=Pago.BaseImporte.ORIGEN, iniciado_por_keycloak_id=transaccion.creado_por_keycloak_id,
        estado=estado,
        referencia_externa="pi_" + uuid.uuid4().hex if estado in (Pago.Estado.APROBADO, Pago.Estado.RECHAZADO) else None,
        aprobado_en=timezone.now() if estado == Pago.Estado.APROBADO else None,
    )


class CancelarTransaccionTests(BaseOperacionesTests):
    """Pruebas de la cancelación de transacciones pendientes de HU-25."""

    def crear_pendiente(self):
        """Usa el estado pendiente real de la confirmación comercial."""

        return self.crear().transaccion

    def test_transaccion_pendiente_se_puede_cancelar(self):
        """Comprueba que una transacción PENDIENTE pueda cancelarse.

        Se espera que pase a CANCELADA, registre la auditoría y conserve
        los valores históricos de la operación.
        """
        for tipo in ("COMPRA", "VENTA"):
            with self.subTest(tipo=tipo):
                transaccion = self.crear(tipo=tipo).transaccion
                antes = Transaccion.objects.values().get(pk=transaccion.pk)
                self.assertFalse(Pago.objects.filter(transaccion=transaccion).exists())
                cancelada = cancelar_transaccion(
                    transaccion_id=transaccion.id, usuario_id=self.usuario_id,
                    usuario_username=self.usuario_username,
                )
                self.assertEqual(cancelada.estado, "CANCELADA")
                self.assertEqual(cancelada.cancelado_por_keycloak_id, self.usuario_id)
                self.assertEqual(cancelada.cancelado_por_username, self.usuario_username)
                self.assertIsNotNone(cancelada.cancelado_en)
                self.assertEqual(cancelada.motivo_cancelacion, "Cancelación solicitada por el usuario.")
                despues = Transaccion.objects.values().get(pk=transaccion.pk)
                cambiables = {
                    "estado", "fecha_actualizacion", "cancelado_por_keycloak_id",
                    "cancelado_por_username", "cancelado_en", "motivo_cancelacion",
                }
                self.assertEqual(
                    {k: v for k, v in antes.items() if k not in cambiables},
                    {k: v for k, v in despues.items() if k not in cambiables},
                )
                self.assertFalse(Pago.objects.filter(transaccion=transaccion).exists())
        self.assertEqual(Transaccion.objects.count(), 2)

    def test_pago_error_o_rechazado_permite_cancelar_sin_modificar_pago(self):
        for estado in (Pago.Estado.ERROR, Pago.Estado.RECHAZADO):
            with self.subTest(estado=estado):
                transaccion = self.crear_pendiente()
                pago = _crear_pago_cancelacion(transaccion, estado)
                antes = Pago.objects.values().get(pk=pago.pk)
                cancelada = cancelar_transaccion(
                    transaccion_id=transaccion.pk, usuario_id=self.usuario_id,
                    usuario_username=self.usuario_username,
                )
                self.assertEqual(cancelada.estado, "CANCELADA")
                self.assertEqual(Pago.objects.values().get(pk=pago.pk), antes)

    def test_pago_en_proceso_indeterminado_o_aprobado_impide_cancelar_sin_cambios(self):
        for estado, codigo in (
            (Pago.Estado.EN_PROCESO, "PAGO_EN_PROCESO"),
            (Pago.Estado.INDETERMINADO, "PAGO_INDETERMINADO"),
            (Pago.Estado.APROBADO, "PAGO_APROBADO"),
            ("DESCONOCIDO", "PAGO_ESTADO_NO_CANCELABLE"),
        ):
            with self.subTest(estado=estado):
                transaccion = self.crear_pendiente()
                pago = _crear_pago_cancelacion(
                    transaccion, Pago.Estado.EN_PROCESO if estado == "DESCONOCIDO" else estado,
                )
                antes_pago = Pago.objects.values().get(pk=pago.pk)
                antes_transaccion = Transaccion.objects.values().get(pk=transaccion.pk)
                # SQL impide estados desconocidos; simular la lectura defensiva.
                if estado == "DESCONOCIDO":
                    pago.estado = estado
                    lectura = mock.patch("operaciones.services.Pago.objects.select_for_update")
                else:
                    lectura = mock.patch("operaciones.services.Pago.objects.select_for_update", wraps=Pago.objects.select_for_update)
                with lectura as consulta:
                    if estado == "DESCONOCIDO":
                        consulta.return_value.filter.return_value.first.return_value = pago
                    with self.assertRaises(ValidationError) as error:
                        cancelar_transaccion(
                            transaccion_id=transaccion.pk, usuario_id=self.usuario_id,
                            usuario_username=self.usuario_username,
                        )
                self.assertEqual(error.exception.error_dict["pago"][0].code, codigo)
                self.assertEqual(Pago.objects.values().get(pk=pago.pk), antes_pago)
                self.assertEqual(Transaccion.objects.values().get(pk=transaccion.pk), antes_transaccion)

    def test_transaccion_inexistente_no_se_puede_cancelar(self):
        """Comprueba que una transacción inexistente sea rechazada.

        Se espera un error porque el usuario debe seleccionar
        una transacción existente.
        """
        with self.assertRaises(ValidationError):
            cancelar_transaccion(
                transaccion_id=999999,
                usuario_id=self.usuario_id,
                usuario_username=self.usuario_username,
            )

    def test_usuario_sin_acceso_no_puede_cancelar(self):
        """Comprueba que un usuario no pueda cancelar una operación ajena.

        La cancelación debe respetar la asociación entre usuario y cliente.
        """
        transaccion = self.crear_pendiente()

        with self.assertRaises(ValidationError):
            cancelar_transaccion(
                transaccion_id=transaccion.id,
                usuario_id="usuario-sin-acceso",
                usuario_username="otro.usuario",
            )

        transaccion.refresh_from_db()
        self.assertEqual(
            transaccion.estado,
            "PENDIENTE",
        )

    def test_transaccion_cancelada_no_se_cancela_de_nuevo(self):
        """Comprueba que una transacción CANCELADA no pueda cancelarse otra vez.

        Se espera que el segundo intento sea rechazado y se conserve
        la información de la primera cancelación.
        """
        transaccion = self.crear_pendiente()

        primera = cancelar_transaccion(
            transaccion_id=transaccion.id,
            usuario_id=self.usuario_id,
            usuario_username=self.usuario_username,
        )

        fecha_cancelacion = primera.cancelado_en
        motivo_cancelacion = primera.motivo_cancelacion

        with self.assertRaises(ValidationError):
            cancelar_transaccion(
                transaccion_id=transaccion.id,
                usuario_id=self.usuario_id,
                usuario_username=self.usuario_username,
            )

        primera.refresh_from_db()

        self.assertEqual(
            primera.estado,
            "CANCELADA",
        )
        self.assertEqual(
            primera.cancelado_en,
            fecha_cancelacion,
        )
        self.assertEqual(
            primera.motivo_cancelacion,
            motivo_cancelacion,
        )


class CancelacionPagoConcurrenciaTests(TransactionTestCase):
    """Orden Tx -> Pago probado con conexiones PostgreSQL independientes."""

    # Compartir únicamente fixtures, sin heredar ni duplicar pruebas existentes.
    setUp = BaseOperacionesTests.setUp

    def crear_pendiente(self):
        return Transaccion.objects.create(
            clave_idempotencia=str(uuid.uuid4()), cliente=self.cliente,
            creado_por_keycloak_id=self.usuario_id, tipo="COMPRA",
            moneda_origen=self.usd, moneda_destino=self.pyg,
            monto_origen=Decimal("100"), monto_destino=Decimal("700000"),
            tasa_comercial=self.tasa, tasa_aplicada=Decimal("7000"),
            porcentaje_comision=Decimal("0"), importe_comision=Decimal("0"),
            metodo_pago=self.metodo_activo, metodo_pago_nombre=self.metodo_activo.nombre,
            estado="PENDIENTE",
        )

    def argumentos_pago(self, transaccion, provider):
        return dict(
            transaccion_id=transaccion.pk, usuario_id=self.usuario_id, roles=["USUARIO"],
            cliente_seleccionado_id=self.cliente.pk, provider=provider,
        )

    def _ejecutar(self, funcion, argumentos, *, consulta_enviada=None, datos=None):
        close_old_connections()
        def observar(execute, sql, params, many, context):
            if "FOR UPDATE" in sql and '"operaciones_transaccion"' in sql:
                datos["pid"] = connection.connection.info.backend_pid
                consulta_enviada.set()
            return execute(sql, params, many, context)
        try:
            if consulta_enviada is not None:
                with connection.execute_wrapper(observar):
                    return funcion(**argumentos)
            return funcion(**argumentos)
        finally:
            connections.close_all()

    def _esperar_bloqueo_postgresql(self, bloqueado, dueno):
        limite = time.monotonic() + 5
        while time.monotonic() < limite:
            with connection.cursor() as cursor:
                cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [dueno, bloqueado])
                if cursor.fetchone()[0]:
                    return
            # Poll de una condición observable del servidor, no orden por sleeps.
            time.sleep(0.01)
        self.fail("PostgreSQL no informó el bloqueo esperado entre las dos conexiones.")

    def test_cancelacion_gana_antes_de_reserva_o_reintento_y_proveedor_no_se_invoca(self):
        if connection.vendor != "postgresql":
            self.skipTest("La verificación de pg_blocking_pids requiere PostgreSQL real.")
        from . import services as operaciones_services
        validar_acceso = operaciones_services._validar_acceso_usuario_cliente
        for funcion in (iniciar_pago, reintentar_pago):
            with self.subTest(funcion=funcion.__name__):
                transaccion = self.crear_pendiente()
                pago = _crear_pago_cancelacion(transaccion, Pago.Estado.ERROR) if funcion == reintentar_pago else None
                antes_pago = Pago.objects.values().get(pk=pago.pk) if pago else None
                provider = mock.Mock(spec=PaymentProvider)
                cancelacion_bloqueada, liberar_cancelacion, pago_enviado = Event(), Event(), Event()
                datos_cancelacion, datos_pago = {}, {}
                def detener_despues_lock(cliente, usuario_id):
                    validar_acceso(cliente, usuario_id)
                    datos_cancelacion["pid"] = connection.connection.info.backend_pid
                    cancelacion_bloqueada.set()
                    if not liberar_cancelacion.wait(timeout=10):
                        raise AssertionError("No se liberó la cancelación de prueba.")
                with mock.patch.object(operaciones_services, "_validar_acceso_usuario_cliente", side_effect=detener_despues_lock):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futuro_cancelacion = pool.submit(self._ejecutar, cancelar_transaccion, dict(
                            transaccion_id=transaccion.pk, usuario_id=self.usuario_id,
                            usuario_username=self.usuario_username,
                        ))
                        try:
                            self.assertTrue(cancelacion_bloqueada.wait(timeout=5))
                            futuro_pago = pool.submit(
                                self._ejecutar, funcion, self.argumentos_pago(transaccion, provider),
                                consulta_enviada=pago_enviado, datos=datos_pago,
                            )
                            self.assertTrue(pago_enviado.wait(timeout=5))
                            self._esperar_bloqueo_postgresql(datos_pago["pid"], datos_cancelacion["pid"])
                        finally:
                            liberar_cancelacion.set()
                        self.assertEqual(futuro_cancelacion.result(timeout=5).estado, "CANCELADA")
                        with self.assertRaises(ValidationError) as error:
                            futuro_pago.result(timeout=5)
                        self.assertEqual(error.exception.code, "OPERACION_NO_PENDIENTE")
                provider.iniciar.assert_not_called()
                if pago:
                    self.assertEqual(Pago.objects.values().get(pk=pago.pk), antes_pago)
                else:
                    self.assertFalse(Pago.objects.filter(transaccion=transaccion).exists())

    def test_pago_gana_cancelacion_espera_reserva_y_se_rechaza_durante_io(self):
        if connection.vendor != "postgresql":
            self.skipTest("La verificación de pg_blocking_pids requiere PostgreSQL real.")
        guardar = Pago.save
        for funcion in (iniciar_pago, reintentar_pago):
            with self.subTest(funcion=funcion.__name__):
                transaccion = self.crear_pendiente()
                if funcion == reintentar_pago:
                    _crear_pago_cancelacion(transaccion, Pago.Estado.ERROR)
                antes_transaccion = Transaccion.objects.values().get(pk=transaccion.pk)
                reserva_bloqueada, liberar_reserva = Event(), Event()
                proveedor_en_io, liberar_io, cancelacion_enviada = Event(), Event(), Event()
                datos_pago, datos_cancelacion = {}, {}
                def detener_despues_reserva(pago, *args, **kwargs):
                    resultado = guardar(pago, *args, **kwargs)
                    if pago.transaccion_id == transaccion.pk and pago.estado == Pago.Estado.EN_PROCESO:
                        datos_pago["pid"] = connection.connection.info.backend_pid
                        datos_pago["pago"] = Pago.objects.values().get(pk=pago.pk)
                        reserva_bloqueada.set()
                        if not liberar_reserva.wait(timeout=10):
                            raise AssertionError("No se liberó la reserva de prueba.")
                    return resultado
                def cobrar(solicitud):
                    self.assertFalse(connection.in_atomic_block)
                    proveedor_en_io.set()
                    if not liberar_io.wait(timeout=10):
                        raise AssertionError("La cancelación no respondió durante IO.")
                    return ResultadoPago(
                        EstadoPago.APROBADO, CodigoResultado.APROBADO,
                        "pi_" + str(solicitud.pago_id), solicitud.monto, solicitud.moneda,
                    )
                provider = mock.Mock(spec=PaymentProvider)
                provider.iniciar.side_effect = cobrar
                with mock.patch.object(Pago, "save", autospec=True, side_effect=detener_despues_reserva):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futuro_pago = pool.submit(self._ejecutar, funcion, self.argumentos_pago(transaccion, provider))
                        try:
                            self.assertTrue(reserva_bloqueada.wait(timeout=5))
                            futuro_cancelacion = pool.submit(
                                self._ejecutar, cancelar_transaccion,
                                dict(transaccion_id=transaccion.pk, usuario_id=self.usuario_id,
                                     usuario_username=self.usuario_username),
                                consulta_enviada=cancelacion_enviada, datos=datos_cancelacion,
                            )
                            self.assertTrue(cancelacion_enviada.wait(timeout=5))
                            self._esperar_bloqueo_postgresql(datos_cancelacion["pid"], datos_pago["pid"])
                            liberar_reserva.set()
                            self.assertTrue(proveedor_en_io.wait(timeout=5))
                            with self.assertRaises(ValidationError) as error:
                                futuro_cancelacion.result(timeout=5)
                            self.assertEqual(error.exception.error_dict["pago"][0].code, "PAGO_EN_PROCESO")
                            self.assertFalse(liberar_io.is_set())
                            self.assertEqual(Transaccion.objects.values().get(pk=transaccion.pk), antes_transaccion)
                            self.assertEqual(Pago.objects.values().get(pk=datos_pago["pago"]["id"]), datos_pago["pago"])
                        finally:
                            liberar_reserva.set()
                            liberar_io.set()
                        self.assertEqual(futuro_pago.result(timeout=5).estado, EstadoPago.APROBADO)
                self.assertEqual(provider.iniciar.call_count, 1)
                transaccion.refresh_from_db()
                self.assertEqual(transaccion.estado, "PENDIENTE")


class IdempotenciaTests(BaseOperacionesTests):
    """Pruebas de la idempotencia por clave idempotencia en confirmación."""

    def test_misma_clave_no_duplica_transaccion(self):
        """Comprueba que repetir la confirmación no duplique transacciones.

        Se espera que la segunda confirmación devuelva la misma transacción.
        """
        clave = self.clave_idempotencia()
        primera = self.crear(clave_idempotencia=clave)
        segunda = self.crear(clave_idempotencia=clave, monto="100.000000")

        self.assertFalse(primera.repetida)
        self.assertTrue(segunda.repetida)
        self.assertEqual(primera.transaccion.id, segunda.transaccion.id)
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_reintento_devuelve_transaccion_original(self):
        """Comprueba que el reintento devuelva la transacción original.

        Aunque la cotización cambie después, repetir la misma clave debe
        devolver la transacción ya registrada sin crear otra.
        """
        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave)
        self.assertEqual(original.transaccion.estado, "PENDIENTE")

        version_original = original.transaccion.tasa_comercial.version

        self.actualizar_cotizacion()
        reintento = self.crear(
            clave_idempotencia=clave,
            version_preview=version_original,
        )

        self.assertTrue(reintento.repetida)
        self.assertFalse(reintento.cambio_cotizacion)
        self.assertEqual(reintento.transaccion.id, original.transaccion.id)
        self.assertEqual(original.transaccion.estado, "PENDIENTE")
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_reintento_conserva_estado_final_sin_reabrir_operacion(self):
        """Una repetición comercial conserva completadas históricas y canceladas."""
        campos = (
            "estado", "monto_origen", "monto_destino", "tasa_aplicada",
            "porcentaje_comision", "importe_comision", "metodo_pago_nombre",
            "fecha_actualizacion", "cancelado_en", "motivo_cancelacion",
        )
        for estado in ("COMPLETADA", "CANCELADA"):
            with self.subTest(estado=estado):
                clave = self.clave_idempotencia()
                original = self.crear(clave_idempotencia=clave).transaccion
                if estado == "COMPLETADA":
                    # Representa un registro histórico; no es el flujo de creación.
                    original.estado = estado
                    original.save(update_fields=["estado"])
                else:
                    original = cancelar_transaccion(
                        transaccion_id=original.pk, usuario_id=self.usuario_id,
                        usuario_username=self.usuario_username,
                    )
                original.refresh_from_db()
                snapshots = {campo: getattr(original, campo) for campo in campos}

                reintento = self.crear(clave_idempotencia=clave)
                self.assertTrue(reintento.repetida)
                self.assertEqual(reintento.transaccion.id, original.id)
                self.assertEqual(
                    {campo: getattr(reintento.transaccion, campo) for campo in campos},
                    snapshots,
                )

    def test_misma_clave_otro_usuario_es_rechazada_sin_revelar_operacion(self):
        """La clave no autoriza a otra identidad aunque comparta cliente."""

        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="otro-usuario",
            username="otro.usuario",
            activo=True,
        )

        with self.assertRaises(ValidationError) as error:
            self.crear(
                clave_idempotencia=clave,
                usuario_id="otro-usuario",
                usuario_username="otro.usuario",
            )

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_clave_otro_cliente_es_rechazada(self):
        """La clave no puede reutilizarse en otro cliente autorizado."""

        clave = self.clave_idempotencia()
        self.crear(clave_idempotencia=clave)
        otro_cliente = Cliente.objects.create(
            nombre_razon_social="Otro cliente idempotente",
            tipo_persona="JURIDICA",
            documento="IDEMP-OTRO-CLIENTE",
            categoria=self.categoria,
        )
        UsuarioCliente.objects.create(
            cliente=otro_cliente,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        with self.assertRaises(ValidationError):
            self.crear(
                clave_idempotencia=clave,
                cliente_id=otro_cliente.id,
                categoria_preview_id=otro_cliente.categoria_id,
            )

        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_clave_payload_distinto_es_rechazada(self):
        """La clave no puede identificar una solicitud financiera diferente."""

        clave = self.clave_idempotencia()
        self.crear(clave_idempotencia=clave)

        for cambio in (
            {"monto": "101"},
            {"tipo": "VENTA"},
            {"moneda_destino_id": self.otra.id},
            {"version_preview": self.tasa.version + 1},
            {"porcentaje_comision_preview": "9.00"},
            {"metodo_pago_id": self.metodo_inactivo.id},
        ):
            if cambio.get("metodo_pago_id") == self.metodo_inactivo.id:
                otro_metodo = MetodoPago.objects.create(
                    nombre="Transferencia idempotente",
                    activo=True,
                )
                cambio = {"metodo_pago_id": otro_metodo.id}
            with self.assertRaises(ValidationError):
                self.crear(clave_idempotencia=clave, **cambio)

        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_clave_categoria_distinta_con_igual_porcentaje_es_rechazada(self):
        """La categoría del preview integra el payload aunque la comisión coincida."""

        categoria_alternativa = CategoriaCliente.objects.create(
            nombre="Minorista alternativo",
            porcentaje_comision=self.categoria.porcentaje_comision,
        )
        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        self.cliente.categoria = categoria_alternativa
        self.cliente.save(update_fields=["categoria"])

        with self.assertRaises(ValidationError) as error:
            self.crear(
                clave_idempotencia=clave,
                categoria_preview_id=categoria_alternativa.id,
                porcentaje_comision_preview=(
                    categoria_alternativa.porcentaje_comision
                ),
            )

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_transaccion_historica_sin_huella_rechaza_reintento(self):
        """Una fila histórica sin huella nunca se presume equivalente."""

        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        Transaccion.objects.filter(pk=original.pk).update(
            huella_idempotencia=None
        )

        with self.assertRaises(ValidationError) as error:
            self.crear(clave_idempotencia=clave)

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_carrera_rechaza_categoria_distinta_con_igual_porcentaje(self):
        """La carrera de unicidad aplica la misma huella que el reintento normal."""

        categoria_alternativa = CategoriaCliente.objects.create(
            nombre="VIP alternativo",
            porcentaje_comision=self.categoria.porcentaje_comision,
        )
        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        self.cliente.categoria = categoria_alternativa
        self.cliente.save(update_fields=["categoria"])

        with mock.patch(
            "operaciones.services.Transaccion.objects.filter",
            side_effect=lambda *args, **kwargs: Transaccion.objects.none(),
        ):
            with self.assertRaises(ValidationError) as error:
                self.crear(
                    clave_idempotencia=clave,
                    categoria_preview_id=categoria_alternativa.id,
                    porcentaje_comision_preview=(
                        categoria_alternativa.porcentaje_comision
                    ),
                )

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_carrera_por_unicidad_se_resuelve_como_repetida(self):
        """Comprueba que una carrera de unicidad se resuelva como repetida.

        Si el chequeo previo no detecta el duplicado y el INSERT choca con
        la unicidad de la clave, la operación debe devolverse como repetida.
        """
        primera = self.crear()
        clave = primera.transaccion.clave_idempotencia

        with mock.patch(
            "operaciones.services.Transaccion.objects.filter",
            side_effect=lambda *args, **kwargs: Transaccion.objects.none(),
        ):
            reintento = self.crear(clave_idempotencia=clave)

        self.assertTrue(reintento.repetida)
        self.assertEqual(reintento.transaccion.id, primera.transaccion.id)
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_integrity_error_ajeno_no_es_tratado_como_repetida(self):
        """Comprueba que un IntegrityError ajeno se propague.

        Una violación de una restricción distinta a la clave de
        idempotencia no debe interpretarse como repetición de la operación.
        """
        diag = type(
            "Diag",
            (),
            {"constraint_name": "transaccion_algun_check"},
        )()
        causa = type("Causa", (Exception,), {"diag": diag})()

        def save_que_falla(*args, **kwargs):
            raise IntegrityError("viola transaccion_algun_check") from causa

        with mock.patch(
            "operaciones.services.Transaccion.save",
            side_effect=save_que_falla,
        ):
            with self.assertRaises(IntegrityError):
                self.crear()

        self.assertEqual(Transaccion.objects.count(), 0)


class PersistenciaSnapshotsTests(BaseOperacionesTests):
    """Pruebas de persistencia de snapshots ante cambios posteriores."""

    def test_cambios_de_cotizacion_no_alteran_snapshots(self):
        """Comprueba que cambios posteriores no alteren los snapshots.

        Se espera que los valores guardados permanezcan invariantes.
        """
        resultado = self.crear()
        transaccion = Transaccion.objects.get(pk=resultado.transaccion.pk)

        self.actualizar_cotizacion()

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7000.000000"))
        self.assertEqual(transaccion.monto_destino, Decimal("630000.000000"))
        self.assertEqual(transaccion.importe_comision, Decimal("70000.000000"))
        self.assertEqual(transaccion.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(transaccion.metodo_pago_nombre, "Efectivo")
        self.assertEqual(transaccion.estado, "PENDIENTE")

    def test_cambio_de_comision_solo_afecta_operaciones_nuevas(self):
        """Una nueva configuración no altera el snapshot histórico."""

        anterior = self.crear().transaccion
        self.categoria.porcentaje_comision = Decimal("3.00")
        self.categoria.save(update_fields=["porcentaje_comision"])
        nueva = self.crear().transaccion

        anterior.refresh_from_db()
        self.assertEqual(anterior.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(anterior.importe_comision, Decimal("70000.000000"))
        self.assertEqual(nueva.porcentaje_comision, Decimal("3.00"))
        self.assertEqual(nueva.importe_comision, Decimal("21000.000000"))


class HistorialTransaccionesTests(BaseOperacionesTests):
    """Pruebas del historial autorizado de transacciones."""

    def _transaccion_manual(self, cliente, *, estado="PENDIENTE", cancelacion=False):
        """Crea directamente una transacción para completar el historial."""
        campos = {
            "estado": estado,
            "cancelado_por_keycloak_id": None,
            "cancelado_por_username": None,
            "cancelado_en": None,
            "motivo_cancelacion": None,
        }
        if cancelacion:
            campos.update(
                {
                    "estado": "CANCELADA",
                    "cancelado_por_keycloak_id": self.usuario_id,
                    "cancelado_por_username": self.usuario_username,
                    "cancelado_en": timezone.now(),
                    "motivo_cancelacion": "Motivo de prueba.",
                }
            )

        return Transaccion.objects.create(
            clave_idempotencia=self.clave_idempotencia(),
            cliente=cliente,
            creado_por_keycloak_id=self.usuario_id,
            creado_por_username=self.usuario_username,
            tipo="COMPRA",
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            monto_origen=Decimal("100.000000"),
            monto_destino=Decimal("630000.000000"),
            tasa_comercial=self.tasa,
            tasa_aplicada=Decimal("7000.000000"),
            porcentaje_comision=Decimal("10.00"),
            importe_comision=Decimal("70000.000000"),
            metodo_pago=self.metodo_activo,
            metodo_pago_nombre=self.metodo_activo.nombre,
            estado=campos["estado"],
            cancelado_por_keycloak_id=campos["cancelado_por_keycloak_id"],
            cancelado_por_username=campos["cancelado_por_username"],
            cancelado_en=campos["cancelado_en"],
            motivo_cancelacion=campos["motivo_cancelacion"],
        )

    def test_historial_solo_muestra_clientes_autorizados(self):
        """Comprueba que el historial filtre por clientes autorizados.

        Se espera que un usuario vea solo transacciones de sus clientes.

        Requisito relacionado: RNF-02.
        """
        propia = self._transaccion_manual(self.cliente)

        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente no autorizado",
            tipo_persona="JURIDICA",
            documento="555555",
            estado="ACTIVO",
            categoria=self.categoria,
        )
        ajena = self._transaccion_manual(cliente_ajeno)

        historial = listar_transacciones(usuario_id=self.usuario_id)

        self.assertIn(propia, historial)
        self.assertNotIn(ajena, historial)

    def test_historial_administrador_ve_todas(self):
        """Comprueba que el administrador consulte todas las transacciones.

        Se espera que el usuario administrador no posea filtros.
        """
        propia = self._transaccion_manual(self.cliente)
        otra = self._transaccion_manual(
            Cliente.objects.create(
                nombre_razon_social="Cliente sin asociación",
                tipo_persona="FISICA",
                documento="666666",
                estado="ACTIVO",
                categoria=self.categoria,
            )
        )

        historial = listar_transacciones(
            usuario_id=self.usuario_id,
            es_admin=True,
        )

        self.assertIn(propia, historial)
        self.assertIn(otra, historial)

    def test_api_administrador_expone_detalle_global_sin_asociacion(self):
        """El supervisor recibe los datos esenciales de una operación ajena."""

        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente global",
            tipo_persona="JURIDICA",
            documento="GLOBAL-001",
            estado="ACTIVO",
            categoria=self.categoria,
        )
        transaccion = self._transaccion_manual(cliente_ajeno, estado="COMPLETADA")
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = int(time.time()) + 600
        session[SESSION_ROLES] = ["ADMINISTRADOR"]
        session[SESSION_USUARIO] = {"sub": "admin-global", "username": "admin"}
        session.save()

        response = self.client.get(reverse("operaciones:historial_transacciones"))

        self.assertEqual(response.status_code, 200)
        detalle = next(
            item
            for item in response.json()["transacciones"]
            if item["id"] == transaccion.id
        )
        self.assertEqual(detalle["cliente"]["categoria"], "Minorista")
        self.assertEqual(detalle["estado"], "COMPLETADA")
        for campo in (
            "tipo",
            "monto_origen",
            "monto_destino",
            "tasa_aplicada",
            "porcentaje_comision",
            "importe_comision",
            "metodo_pago",
            "fecha_creacion",
            "fecha_actualizacion",
        ):
            self.assertIn(campo, detalle)

        response_detalle = self.client.get(
            reverse("operaciones:detalle_transaccion", args=[transaccion.id])
        )
        self.assertEqual(response_detalle.status_code, 200)
        self.assertEqual(
            response_detalle.json()["transaccion"]["id"],
            transaccion.id,
        )

    def test_historial_incluye_transacciones_canceladas(self):
        """Comprueba que el historial incluya transacciones canceladas.

        Se espera que la transacción cancelada conserve su motivo.
        """
        cancelada = self._transaccion_manual(
            self.cliente,
            cancelacion=True,
        )

        historial = listar_transacciones(usuario_id=self.usuario_id)

        self.assertIn(cancelada, historial)
        self.assertEqual(cancelada.estado, "CANCELADA")
        self.assertEqual(cancelada.motivo_cancelacion, "Motivo de prueba.")

    def test_historial_no_recalcula_valores(self):
        """Comprueba que el historial no recalcule con la cotización actual.

        Se espera que los snapshots devuelvan los valores persistidos.
        """
        self.crear()
        self.actualizar_cotizacion()

        historial = listar_transacciones(usuario_id=self.usuario_id)
        serializada = _serializar_transaccion(historial[0])

        self.assertEqual(len(historial), 1)
        self.assertEqual(historial[0].tasa_aplicada, Decimal("7000.000000"))
        self.assertEqual(historial[0].monto_destino, Decimal("630000.000000"))
        self.assertEqual(serializada["tasa_aplicada"], "7000")
        self.assertEqual(serializada["monto_convertido"], "700000.000000")

    def test_historial_usa_la_tasa_redondeada_aplicada(self):
        """Comprueba que el historial use la misma tasa aplicada.

        La cotización comercial se normaliza antes de calcular y persistir.
        """
        self.tasa.compra = Decimal("7000.000001")
        self.tasa.save(update_fields=["compra"])

        self.crear(monto="1.000003")
        historial = listar_transacciones(usuario_id=self.usuario_id)
        serializada = _serializar_transaccion(historial[0])

        self.assertEqual(serializada["monto_origen"], "1.000003")
        self.assertEqual(serializada["monto_convertido"], "7000.021000")
        self.assertEqual(serializada["tasa_aplicada"], "7000")


class OperacionesUrlTests(TestCase):
    """Pruebas del registro de las rutas del núcleo de operaciones."""

    def test_rutas_operaciones_registradas(self):
        """Comprueba que las tres rutas del núcleo estén registradas.

        Se espera que los nombres de ruta resuelvan bajo el prefijo API.
        """
        self.assertEqual(
            reverse("operaciones:previsualizar_operacion"),
            "/api/operaciones/previsualizar/",
        )
        self.assertEqual(
            reverse("operaciones:crear_transaccion"),
            "/api/operaciones/crear/",
        )
        self.assertEqual(
            reverse("operaciones:cancelar_transaccion"),
            "/api/operaciones/cancelar/",
        )
        self.assertEqual(
            reverse("operaciones:historial_transacciones"),
            "/api/operaciones/historial/",
        )
        self.assertEqual(reverse("operaciones_web:inicio"), "/operaciones/")


class OperacionesFrontendTests(BaseOperacionesTests):
    """Pruebas esenciales de integración de la pantalla de operaciones."""

    def autenticar(self):
        """Crea una sesión web vigente para el usuario asociado del escenario."""

        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = int(time.time()) + 600
        session[SESSION_ROLES] = ["USUARIO"]
        session[SESSION_USUARIO] = {
            "sub": self.usuario_id,
            "username": self.usuario_username,
        }
        session["selected_client"] = {
            "id": self.cliente.id,
            "name": self.cliente.nombre_razon_social,
        }
        session.save()

    def autenticar_con_roles(self, roles):
        """Crea una sesión válida con los roles indicados y sin cliente."""

        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = int(time.time()) + 600
        session[SESSION_ROLES] = roles
        session[SESSION_USUARIO] = {
            "sub": self.usuario_id,
            "username": self.usuario_username,
        }
        session.pop("selected_client", None)
        session.save()

    def test_pantalla_presenta_cliente_y_catalogos_activos(self):
        """Muestra el contexto autorizado y excluye opciones inactivas."""

        self.cliente.metodo_pago_preferido = self.metodo_activo
        self.cliente.save(update_fields=["metodo_pago_preferido"])
        self.autenticar()

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/operaciones.html")
        self.assertEqual(response.context["cliente_operacion"], self.cliente)
        self.assertIn(self.metodo_activo, response.context["metodos_activos"])
        self.assertNotIn(self.metodo_inactivo, response.context["metodos_activos"])
        self.assertContains(response, "Preferido")
        self.assertContains(
            response,
            f'data-methods-url="{reverse("operaciones:metodos_pago_operacion")}"',
        )
        self.assertContains(
            response,
            f'data-detail-url="{reverse("operaciones:detalle_transaccion", args=[0])}"',
        )

    def test_pantalla_no_expone_cliente_sin_asociacion_activa(self):
        """No habilita el formulario si el cliente dejó de estar asociado."""

        self.asociacion.activo = False
        self.asociacion.save(update_fields=["activo"])
        self.autenticar()

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["cliente_operacion"])
        self.assertContains(response, "Seleccioná un cliente para operar")

    def test_administrador_supervisa_sin_cliente_y_sin_formulario(self):
        """El administrador accede al historial global, no a crear operaciones."""

        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["es_supervisor"])
        self.assertContains(response, "Modo supervisor global")
        self.assertNotContains(response, "data-operation-form")

    def test_administrador_no_puede_confirmar_operaciones(self):
        """La API financiera no amplía permisos por el rol administrador."""

        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.post(
            reverse("operaciones:crear_transaccion"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_administrador_cajero_conserva_modo_supervisor(self):
        """La prioridad multirrol impide operar con un rol inferior."""

        self.autenticar_con_roles(["ADMINISTRADOR", "CAJERO"])

        pantalla = self.client.get(reverse("operaciones_web:inicio"))
        preview = self.client.post(
            reverse("operaciones:previsualizar_operacion"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(pantalla.status_code, 200)
        self.assertTrue(pantalla.context["es_supervisor"])
        self.assertEqual(preview.status_code, 403)

    def test_analista_no_accede_al_modulo_operativo(self):
        """El analista permanece limitado a tasas y referencia."""

        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 403)
