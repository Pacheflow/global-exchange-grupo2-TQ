"""Fondos administrativos, intercambio online y recuperación, siempre sin cobros reales."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from cajas.models import MovimientoCaja, Caja
from metodos_pago.models import MetodoPago
from operaciones.models import Transaccion
from operaciones import tests as escenarios
from operaciones import test_guillermo as interfaz
from pagos.models import Pago
from pagos.providers import EstadoPago, CodigoResultado, ResultadoPago, PaymentProvider
from pagos.services import iniciar_pago, recuperar_pago, PersistenciaPagoError, sincronizar_resultado_local
from .models import Fondo, MovimientoFondo, ReservaFondo, FinalizacionOnline, OperacionCompletada
from .services import cargar, consultar, reservar, saldos


class FondosTests(TransactionTestCase):
    """Comparte fixtures, sin heredar ni duplicar pruebas de Operaciones."""
    con_fondos_operacion = False
    setUp = escenarios.BaseOperacionesTests.setUp
    parametros_preview = escenarios.BaseOperacionesTests.parametros_preview
    parametros_crear = escenarios.BaseOperacionesTests.parametros_crear
    previsualizar = escenarios.BaseOperacionesTests.previsualizar
    crear = escenarios.BaseOperacionesTests.crear
    clave_idempotencia = escenarios.BaseOperacionesTests.clave_idempotencia

    def financiar(self, monto="1000000", moneda=None, clave=None):
        """Carga financiación explícita con servicio administrativo en la BD aislada."""
        return cargar(moneda_id=(moneda or self.pyg).pk, monto=monto, motivo="Financiación QA aislada",
                      clave=clave or uuid4(), usuario_id="admin-fondos", roles=["ADMINISTRADOR"])

    def argumentos_pago(self, op, provider):
        """Usa identidad y cliente de la fixture, nunca campos manipulables del formulario."""
        return dict(transaccion_id=op.pk, usuario_id=self.usuario_id, roles=["USUARIO"],
                    cliente_seleccionado_id=self.cliente.pk, provider=provider)

    def provider(self, estado=EstadoPago.APROBADO):
        """Proveedor neutral simulado que devuelve evidencia coherente sin red."""
        provider = Mock(spec=PaymentProvider)
        codigo = {EstadoPago.APROBADO: CodigoResultado.APROBADO, EstadoPago.RECHAZADO: CodigoResultado.RECHAZADO,
                  EstadoPago.INDETERMINADO: CodigoResultado.RESULTADO_DESCONOCIDO,
                  EstadoPago.EN_PROCESO: CodigoResultado.EN_PROCESO}[estado]
        provider.iniciar.side_effect = lambda s: ResultadoPago(estado, codigo, f"pi_{s.pago_id.hex}", s.monto, s.moneda)
        return provider

    def test_carga_idempotente_permisos_precision_y_trazabilidad(self):
        """Solo administrador carga importes exactos; repetir no duplica y cambiar payload se rechaza."""
        clave = uuid4()
        movimiento = self.financiar("12.123456", clave=clave)
        self.assertEqual(self.financiar("12.123456", clave=clave).pk, movimiento.pk)
        with self.assertRaises(ValidationError): self.financiar("13", clave=clave)
        for valor in ("0", "-1", "NaN", "Infinity", "0.1234567", "1000000000000"):
            with self.subTest(valor=valor), self.assertRaises(ValidationError): self.financiar(valor)
        for roles in (["USUARIO"], ["CAJERO"], ["ANALISTA_CAMBIARIO", "CAJERO"]):
            with self.subTest(roles=roles), self.assertRaises(PermissionDenied):
                cargar(moneda_id=self.pyg.pk, monto="1", motivo="QA", clave=uuid4(), usuario_id="otro", roles=roles)
            with self.assertRaises(PermissionDenied): consultar(usuario_id="otro", roles=roles)
        self.assertEqual(MovimientoFondo.objects.count(), 1)
        self.assertEqual(movimiento.responsable, "admin-fondos")
        self.assertIsNotNone(movimiento.fecha)
        with self.assertRaises(ValueError): movimiento.save()
        with self.assertRaises(ValueError): movimiento.delete()
        self.assertFalse(Caja.objects.exists())

    def test_carga_http_csrf_prg_y_responsable_no_suplantable(self):
        """POST administrativo usa CSRF y actor de sesión, redirige y repetir conserva una sola carga."""
        interfaz.FlujosGuillermoTests.autenticar(self, roles=("ADMINISTRADOR", "CAJERO"))
        url = reverse("fondos:cargar")
        datos = dict(moneda=self.pyg.pk, importe="50", motivo="QA", clave=str(uuid4()), responsable="intruso")
        respuesta = self.client.post(url, datos, follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.redirect_chain, [(reverse("fondos:inicio"), 302)])
        self.assertContains(respuesta, "Carga de fondos registrada")
        self.client.post(url, datos)
        self.assertEqual(MovimientoFondo.objects.count(), 1)
        self.assertEqual(MovimientoFondo.objects.get().responsable, self.usuario_id)
        estricto = Client(enforce_csrf_checks=True)
        estricto.cookies = self.client.cookies
        self.assertEqual(estricto.post(url, datos).status_code, 403)
        for rol in ("USUARIO", "CAJERO", "ANALISTA_CAMBIARIO"):
            interfaz.FlujosGuillermoTests.autenticar(self, roles=(rol,))
            for nombre in ("inicio", "cargar", "movimientos"):
                self.assertEqual(self.client.get(reverse(f"fondos:{nombre}")).status_code, 403)

    def test_venta_sin_caja_completa_neto_sin_duplicar_comision(self):
        """VENTA con saldo exacto completa dos movimientos electrónicos, conserva comisión y repite sin efectos."""
        preview = self.previsualizar(tipo="VENTA")
        self.financiar(preview.monto_destino)
        clave = str(uuid4())
        with patch("pagos.stripe_provider.StripePaymentProvider._cliente") as externo:
            op = self.crear(tipo="VENTA", clave_idempotencia=clave).transaccion
            repetida = self.crear(tipo="VENTA", clave_idempotencia=clave)
            externo.assert_not_called()
        self.assertEqual(op.estado, "COMPLETADA")
        self.assertEqual((op.canal, op.naturaleza_metodo, op.version_flujo), ("ONLINE", "ELECTRONICO", 1))
        self.assertTrue(repetida.repetida)
        self.assertEqual(repetida.transaccion.pk, op.pk)
        self.assertEqual(MovimientoFondo.objects.filter(operacion=op).count(), 2)
        self.assertEqual(MovimientoFondo.objects.get(operacion=op, tipo="EGRESO").monto, preview.monto_destino)
        self.assertEqual(FinalizacionOnline.objects.get(operacion=op).fuente, "VENTA_SIMULADA")
        self.assertEqual(OperacionCompletada.objects.filter(operacion=op).count(), 1)
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())
        self.assertEqual(saldos(Fondo.objects.get(moneda=self.pyg)), (Decimal(0), Decimal(0), Decimal(0)))

    def test_venta_rollback_sin_financiacion_o_fallo_local(self):
        """Sin saldo o si falla evidencia, confirmar VENTA no deja operación ni movimientos parciales."""
        with self.assertRaises(ValidationError): self.crear(tipo="VENTA")
        self.financiar()
        with patch("fondos.services.FinalizacionOnline.objects.create", side_effect=RuntimeError("aislado")):
            with self.assertRaises(RuntimeError): self.crear(tipo="VENTA")
        self.assertFalse(Transaccion.objects.exists())
        self.assertFalse(MovimientoFondo.objects.filter(operacion__isnull=False).exists())
        self.assertFalse(FinalizacionOnline.objects.exists())

    def test_compra_reserva_durable_y_finaliza_sin_caja(self):
        """COMPRA reserva antes del proveedor, cobra origen y aprueba una vez con dos movimientos y sin Caja."""
        preview = self.previsualizar()
        self.financiar(preview.monto_destino)
        op = self.crear().transaccion
        provider = self.provider()
        responder = provider.iniciar.side_effect
        def cobrar(solicitud):
            from django.db import connection
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "ACTIVA")
            self.assertEqual(saldos(Fondo.objects.get(moneda=self.pyg))[2], 0)
            self.assertEqual((solicitud.monto, solicitud.moneda), (op.monto_origen, self.usd.codigo))
            return responder(solicitud)
        provider.iniciar.side_effect = cobrar
        iniciar_pago(**self.argumentos_pago(op, provider))
        iniciar_pago(**self.argumentos_pago(op, provider))
        op.refresh_from_db()
        self.assertEqual(op.estado, "COMPLETADA")
        self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "CONSUMIDA")
        self.assertEqual(MovimientoFondo.objects.filter(operacion=op).count(), 2)
        self.assertFalse(MovimientoCaja.objects.exists())
        provider.iniciar.assert_called_once()

    def test_rechazo_error_e_incertidumbre_gestionan_reserva(self):
        """Rechazo y error seguro liberan; proceso e incertidumbre retienen sin movimientos ni completar."""
        self.financiar("999999999999")
        for estado in (EstadoPago.RECHAZADO, EstadoPago.EN_PROCESO, EstadoPago.INDETERMINADO, EstadoPago.ERROR):
            op = self.crear(clave_idempotencia=str(uuid4())).transaccion
            if estado == EstadoPago.ERROR:
                provider = Mock(spec=PaymentProvider)
                provider.iniciar.return_value = ResultadoPago(estado, CodigoResultado.ERROR_SIN_EJECUCION)
            else:
                provider = self.provider(estado)
            iniciar_pago(**self.argumentos_pago(op, provider))
            op.refresh_from_db()
            self.assertEqual(op.estado, "PENDIENTE")
            self.assertEqual(ReservaFondo.objects.get(operacion=op).estado,
                             "LIBERADA" if estado in (EstadoPago.RECHAZADO, EstadoPago.ERROR) else "ACTIVA")
            self.assertFalse(MovimientoFondo.objects.filter(operacion=op).exists())

    def test_aprobacion_durable_y_recuperacion_local_sin_cobro(self):
        """Tras fallar la finalización, recuperar explícitamente el mismo Pago completa una vez sin consultar ni cobrar otra vez."""
        self.financiar()
        op = self.crear().transaccion
        provider = self.provider()
        with patch("fondos.services.FinalizacionOnline.objects.create", side_effect=RuntimeError("aislado")):
            with self.assertRaises(PersistenciaPagoError): iniciar_pago(**self.argumentos_pago(op, provider))
        self.assertEqual(Pago.objects.get(transaccion=op).estado, "APROBADO")
        self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "ACTIVA")
        self.assertFalse(MovimientoFondo.objects.filter(operacion=op).exists())
        pago_id = Pago.objects.get(transaccion=op).pk
        resultado = recuperar_pago(**self.argumentos_pago(op, provider))
        self.assertEqual(resultado.pago_id, pago_id)
        self.assertEqual(resultado.estado, EstadoPago.APROBADO)
        recuperar_pago(**self.argumentos_pago(op, provider))
        op.refresh_from_db()
        self.assertEqual(op.estado, "COMPLETADA")
        self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "CONSUMIDA")
        self.assertEqual(MovimientoFondo.objects.filter(operacion=op).count(), 2)
        provider.iniciar.assert_called_once()
        provider.consultar.assert_not_called()
        provider.conciliar_sin_referencia.assert_not_called()

    def test_aprobado_sin_saldo_destino_recupera_tras_financiar_sin_recobro(self):
        """Una anomalía después del IO conserva el aprobado; financiar permite finalizar solo una vez."""
        monto = self.previsualizar().monto_destino
        carga = self.financiar(monto)
        op = self.crear().transaccion
        provider = self.provider()
        responder = provider.iniciar.side_effect
        faltante = Decimal("1")

        def aprobar_con_anomalia(solicitud):
            from django.db import connection
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "ACTIVA")
            # Fixture excepcional: update evita deliberadamente la inmutabilidad
            # para simular corrupción externa después de reservar. No es ruta pública.
            MovimientoFondo.objects.filter(pk=carga.pk).update(monto=monto - faltante)
            return responder(solicitud)

        provider.iniciar.side_effect = aprobar_con_anomalia
        with self.assertLogs("pagos.services", level="ERROR") as registro:
            with self.assertRaises(PersistenciaPagoError):
                iniciar_pago(**self.argumentos_pago(op, provider))
        self.assertTrue(any("FINALIZACION_ONLINE_PENDIENTE" in linea for linea in registro.output))
        pago = Pago.objects.get(transaccion=op)
        self.assertEqual(pago.estado, "APROBADO")
        self.assertTrue(pago.referencia_externa)
        self.assertIsNotNone(pago.aprobado_en)
        op.refresh_from_db()
        self.assertEqual(op.estado, "PENDIENTE")
        self.assertEqual(saldos(Fondo.objects.get(moneda=self.pyg))[2], -faltante)
        self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "ACTIVA")
        self.assertFalse(MovimientoFondo.objects.filter(operacion=op).exists())
        self.assertFalse(FinalizacionOnline.objects.filter(operacion=op).exists())
        self.assertFalse(OperacionCompletada.objects.filter(operacion=op).exists())
        with self.assertRaises(PersistenciaPagoError):
            recuperar_pago(**self.argumentos_pago(op, provider))
        self.assertEqual(Pago.objects.get(transaccion=op).estado, "APROBADO")
        provider.iniciar.assert_called_once()
        provider.consultar.assert_not_called()
        provider.conciliar_sin_referencia.assert_not_called()
        self.financiar(faltante)
        for _ in range(2):
            resultado = recuperar_pago(**self.argumentos_pago(op, provider))
            self.assertEqual((resultado.pago_id, resultado.estado), (pago.pk, EstadoPago.APROBADO))
        op.refresh_from_db()
        pago.refresh_from_db()
        self.assertEqual(op.estado, "COMPLETADA")
        self.assertEqual(Pago.objects.filter(transaccion=op).count(), 1)
        self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "CONSUMIDA")
        self.assertEqual(MovimientoFondo.objects.filter(operacion=op).count(), 2)
        self.assertEqual(MovimientoFondo.objects.get(operacion=op, tipo="EGRESO").monto, monto)
        self.assertEqual(MovimientoFondo.objects.get(operacion=op, tipo="INGRESO").monto, op.monto_origen)
        self.assertEqual(FinalizacionOnline.objects.filter(operacion=op).count(), 1)
        self.assertEqual(FinalizacionOnline.objects.get(operacion=op).referencia, pago.referencia_externa)
        self.assertEqual(OperacionCompletada.objects.filter(operacion=op).count(), 1)
        self.assertEqual(saldos(Fondo.objects.get(moneda=self.pyg)), (Decimal(0), Decimal(0), Decimal(0)))
        self.assertFalse(MovimientoCaja.objects.exists())
        self.assertFalse(Caja.objects.exists())
        provider.iniciar.assert_called_once()
        provider.consultar.assert_not_called()
        provider.conciliar_sin_referencia.assert_not_called()

    def test_reserva_invalida_impide_finalizar_aprobado_sin_recobrar(self):
        """Recuperar no consume reservas liberadas o inconsistentes ni llama al proveedor."""
        self.financiar()
        op = self.crear().transaccion
        provider = self.provider()
        with patch("fondos.services.FinalizacionOnline.objects.create", side_effect=RuntimeError("aislado")):
            with self.assertRaises(PersistenciaPagoError):
                iniciar_pago(**self.argumentos_pago(op, provider))
        reserva = ReservaFondo.objects.get(operacion=op)
        pago = Pago.objects.get(transaccion=op)
        for cambios in ({"estado": "LIBERADA"}, {"monto": op.monto_destino + Decimal("1")}):
            with self.subTest(cambios=cambios):
                # Anomalía de fixture: no hay una API pública que reescriba la reserva.
                ReservaFondo.objects.filter(pk=reserva.pk).update(**cambios)
                for _ in range(2):
                    with self.assertRaises(PersistenciaPagoError):
                        recuperar_pago(**self.argumentos_pago(op, provider))
                op.refresh_from_db()
                self.assertEqual(op.estado, "PENDIENTE")
                self.assertEqual(Pago.objects.get(transaccion=op).pk, pago.pk)
                self.assertEqual(Pago.objects.get(transaccion=op).estado, "APROBADO")
                self.assertFalse(MovimientoFondo.objects.filter(operacion=op).exists())
                self.assertFalse(FinalizacionOnline.objects.filter(operacion=op).exists())
                self.assertFalse(OperacionCompletada.objects.filter(operacion=op).exists())
                ReservaFondo.objects.filter(pk=reserva.pk).update(estado="ACTIVA", monto=op.monto_destino)
        provider.iniciar.assert_called_once()
        provider.consultar.assert_not_called()
        provider.conciliar_sin_referencia.assert_not_called()

    def test_historico_no_se_cobra_ni_se_reclasifica(self):
        """El marcador heredado impide nuevos cobros sin adivinar canal ni mover fondos."""
        self.financiar()
        op = self.crear().transaccion
        Transaccion.objects.filter(pk=op.pk).update(version_flujo=0, canal="", naturaleza_metodo="")
        provider = self.provider()
        with self.assertRaises(ValidationError) as error: iniciar_pago(**self.argumentos_pago(op, provider))
        self.assertEqual(error.exception.code, "REVISION_PENDIENTE")
        provider.iniciar.assert_not_called()
        self.assertFalse(ReservaFondo.objects.exists())

    def test_metodos_por_canal_y_preferido_efectivo_no_elegible(self):
        """Online excluye efectivo y preferido físico; backend rechaza selección manipulada sin cambiar preferencia."""
        from operaciones.services import listar_metodos_pago_operacion
        efectivo = MetodoPago.objects.create(nombre="Solo físico", naturaleza="EFECTIVO")
        self.cliente.metodo_pago_preferido = efectivo
        self.cliente.save()
        _, metodos, preferido = listar_metodos_pago_operacion(usuario_id=self.usuario_id, cliente_id=self.cliente.pk)
        self.assertNotIn(efectivo, metodos)
        self.assertIsNone(preferido)
        with self.assertRaises(ValidationError): self.previsualizar(metodo_pago_id=efectivo.pk)
        with self.assertRaises(ValidationError): self.crear(metodo_pago_id=efectivo.pk)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.metodo_pago_preferido_id, efectivo.pk)


    def test_reservas_concurrentes_no_sobregiran(self):
        """Dos compras compiten por un neto disponible; solo una reserva y la otra no cobra ni sobregira."""
        monto = self.previsualizar().monto_destino
        self.financiar(monto)
        operaciones = [self.crear(clave_idempotencia=str(uuid4())).transaccion for _ in range(2)]
        barrera = Barrier(2)
        def ejecutar(pk):
            close_old_connections()
            try:
                barrera.wait(timeout=5)
                with transaction.atomic():
                    op = Transaccion.objects.select_for_update().get(pk=pk)
                    reservar(op)
                return "reservada"
            except ValidationError:
                return "sin fondos"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(ejecutar, [op.pk for op in operaciones]))
        self.assertCountEqual(resultados, ["reservada", "sin fondos"])
        self.assertEqual(ReservaFondo.objects.filter(estado="ACTIVA").count(), 1)
        self.assertEqual(saldos(Fondo.objects.get(moneda=self.pyg))[2], 0)

    def test_finalizaciones_concurrentes_reutilizan_evidencia(self):
        """Dos recuperadores tras una aprobación durable completan una vez sin duplicar cobros ni movimientos."""
        self.financiar()
        op = self.crear().transaccion
        provider = self.provider()
        with patch("fondos.services.FinalizacionOnline.objects.create", side_effect=RuntimeError("interrupción")):
            with self.assertRaises(PersistenciaPagoError): iniciar_pago(**self.argumentos_pago(op, provider))
        barrera = Barrier(2)
        def finalizar_en_conexion():
            close_old_connections()
            try:
                barrera.wait(timeout=5)
                sincronizar_resultado_local(op.pk)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros = [pool.submit(finalizar_en_conexion) for _ in range(2)]
            for futuro in futuros: futuro.result(timeout=10)
        self.assertEqual(FinalizacionOnline.objects.filter(operacion=op).count(), 1)
        self.assertEqual(OperacionCompletada.objects.filter(operacion=op).count(), 1)
        self.assertEqual(MovimientoFondo.objects.filter(operacion=op).count(), 2)
        self.assertEqual(ReservaFondo.objects.get(operacion=op).estado, "CONSUMIDA")
        provider.iniciar.assert_called_once()

    def test_cargas_concurrentes_con_misma_clave_no_duplican_financiacion(self):
        """Dos POST concurrentes con igual solicitud crean un fondo y una carga, sin acreditar dos veces."""
        clave = uuid4()
        barrera = Barrier(2)
        def cargar_en_conexion():
            close_old_connections()
            try:
                barrera.wait(timeout=5)
                return self.financiar("50", clave=clave).pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros = [pool.submit(cargar_en_conexion) for _ in range(2)]
            ids = [futuro.result(timeout=10) for futuro in futuros]
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(Fondo.objects.count(), 1)
        self.assertEqual(MovimientoFondo.objects.count(), 1)
        self.assertEqual(saldos(Fondo.objects.get(moneda=self.pyg))[2], 50)

    def test_restricciones_bd_no_permiten_duplicados_ni_importes_negativos(self):
        """La BD rechaza fondos duplicados, movimientos negativos y reservas repetidas aun omitiendo full_clean."""
        self.financiar()
        fondo = Fondo.objects.get(moneda=self.pyg)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Fondo.objects.create(moneda=self.pyg)
        invalido = MovimientoFondo(fondo=fondo, tipo="EGRESO", monto=-1, clave="invalido",
                                  motivo="Fixture", responsable="admin-test")
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovimientoFondo.objects.bulk_create([invalido])
        op = self.crear().transaccion
        with transaction.atomic(): reservar(op)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReservaFondo.objects.create(operacion=op, fondo=fondo, monto=op.monto_destino)
