"""Contrato de orquestación; proveedor offline y concurrencia PostgreSQL real."""

import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal
from threading import Barrier, Event
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from clientes.models import CategoriaCliente, Cliente, UsuarioCliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from operaciones.models import Transaccion
from tasas.models import TasaComercial

from .models import Pago
from .providers import CodigoResultado, EstadoPago, PaymentProvider, ResultadoPago
from .services import PersistenciaPagoError, iniciar_pago, recuperar_pago, reintentar_pago


class PagoServiceTests(TransactionTestCase):
    def setUp(self):
        categoria, _ = CategoriaCliente.objects.get_or_create(nombre="Minorista")
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente servicio pagos", tipo_persona="FISICA",
            documento="servicio-pagos", categoria=categoria,
        )
        self.asociacion = UsuarioCliente.objects.create(
            cliente=self.cliente, keycloak_user_id="usuario-pagos", username="operador",
            rol_en_cliente="OPERADOR", activo=True,
        )
        self.origen, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"},
        )
        self.destino, _ = Moneda.objects.get_or_create(
            codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"},
        )
        self.metodo = MetodoPago.objects.create(nombre="Método servicio pagos")
        self.tasa = TasaComercial.objects.create(
            moneda_origen=self.origen, moneda_destino=self.destino,
            compra=Decimal("7000"), venta=Decimal("7200"), vigente=True,
            usuario_id="usuario-pagos", usuario_username="operador",
        )
        self.transaccion = self.crear_transaccion()
        self.provider = Mock(spec=PaymentProvider)
        self.provider.iniciar.side_effect = lambda solicitud: self.resultado(solicitud)
        self.provider.consultar.side_effect = lambda solicitud, referencia: self.resultado(solicitud, referencia=referencia)
        self.provider.conciliar_sin_referencia.side_effect = lambda solicitud: self.resultado(solicitud)

    def crear_transaccion(self, **cambios):
        datos = {
            "clave_idempotencia": str(uuid.uuid4()), "cliente": self.cliente,
            "creado_por_keycloak_id": "usuario-pagos", "tipo": "COMPRA",
            "moneda_origen": self.origen, "moneda_destino": self.destino,
            "monto_origen": Decimal("12.340000"), "monto_destino": Decimal("86380"),
            "tasa_comercial": self.tasa, "tasa_aplicada": Decimal("7000"),
            "porcentaje_comision": Decimal("0"), "importe_comision": Decimal("0"),
            "metodo_pago": self.metodo, "metodo_pago_nombre": self.metodo.nombre,
            "estado": "PENDIENTE",
        }
        datos.update(cambios)
        return Transaccion.objects.create(**datos)

    def argumentos(self, **cambios):
        datos = dict(
            transaccion_id=self.transaccion.pk, usuario_id="usuario-pagos",
            roles=["USUARIO"], cliente_seleccionado_id=self.cliente.pk,
            provider=self.provider,
        )
        datos.update(cambios)
        return datos

    @staticmethod
    def resultado(solicitud, estado=EstadoPago.APROBADO, referencia="pi_servicio"):
        codigo = {
            EstadoPago.APROBADO: CodigoResultado.APROBADO,
            EstadoPago.RECHAZADO: CodigoResultado.RECHAZADO,
            EstadoPago.EN_PROCESO: CodigoResultado.EN_PROCESO,
            EstadoPago.INDETERMINADO: CodigoResultado.RESULTADO_DESCONOCIDO,
        }[estado]
        return ResultadoPago(estado, codigo, referencia, solicitud.monto, solicitud.moneda)

    def reservar_incierto(self, *, referencia=None):
        if referencia:
            self.provider.iniciar.side_effect = lambda s: self.resultado(s, EstadoPago.INDETERMINADO, referencia)
        else:
            self.provider.iniciar.side_effect = TimeoutError("contenido externo ficticio")
        iniciar_pago(**self.argumentos())
        return Pago.objects.get(transaccion=self.transaccion)

    def test_reserva_confirmada_y_aprobacion_no_completa_operacion(self):
        self.asociacion.rol_en_cliente = "RESPONSABLE"
        self.asociacion.save()
        def iniciar(solicitud):
            self.assertFalse(connection.in_atomic_block)
            # Una segunda conexión ve la reserva confirmada antes de IO.
            with ThreadPoolExecutor(max_workers=1) as pool:
                def leer():
                    close_old_connections()
                    try:
                        return Pago.objects.get(pk=solicitud.pago_id).estado
                    finally:
                        connections.close_all()
                self.assertEqual(pool.submit(leer).result(timeout=5), Pago.Estado.EN_PROCESO)
            return self.resultado(solicitud)
        self.provider.iniciar.side_effect = iniciar
        respuesta = iniciar_pago(**self.argumentos(roles=["CAJERO"]))
        pago = Pago.objects.get(pk=respuesta.pago_id)
        solicitud = self.provider.iniciar.call_args.args[0]
        self.assertEqual((solicitud.monto, solicitud.moneda, solicitud.huella_solicitud),
                         (self.transaccion.monto_origen, self.origen.codigo, pago.huella_solicitud))
        self.assertEqual(pago.base_importe, "ORIGEN")
        self.assertEqual(pago.iniciado_por_keycloak_id, "usuario-pagos")
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(pago.referencia_externa, "pi_servicio")
        self.assertIsNotNone(pago.aprobado_en)
        self.assertEqual([e["codigo"] for e in pago.trazabilidad], ["RESERVADO", "APROBADO"])
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, "PENDIENTE")

    def test_venta_rechazada_por_inicio_y_reintento_sin_pago_ni_proveedor(self):
        self.transaccion.tipo = "VENTA"
        self.transaccion.save()
        for funcion in (iniciar_pago, reintentar_pago):
            with self.subTest(funcion=funcion.__name__), self.assertRaises(ValidationError):
                funcion(**self.argumentos())
        self.assertFalse(Pago.objects.exists())
        self.provider.iniciar.assert_not_called()
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, "PENDIENTE")

    def test_no_pendiente_o_metodo_inactivo_impide_inicio(self):
        self.transaccion.estado = "COMPLETADA"
        self.transaccion.save()
        with self.assertRaises(ValidationError):
            iniciar_pago(**self.argumentos())
        self.transaccion.estado = "PENDIENTE"
        self.transaccion.save()
        self.metodo.desactivar()
        with self.assertRaises(ValidationError):
            iniciar_pago(**self.argumentos())
        self.assertFalse(Pago.objects.exists())
        self.provider.iniciar.assert_not_called()

    def test_permisos_identidad_rol_efectivo_y_contexto(self):
        for cambios in (
            {"usuario_id": " "}, {"usuario_id": "ajeno"}, {"roles": []},
            {"roles": ["ADMINISTRADOR", "CAJERO"]},
            {"roles": ["ANALISTA_CAMBIARIO", "USUARIO"]}, {"roles": "USUARIO"},
            {"cliente_seleccionado_id": self.cliente.pk + 1},
        ):
            with self.subTest(cambios=cambios), self.assertRaises(PermissionDenied):
                iniciar_pago(**self.argumentos(**cambios))
        self.assertFalse(Pago.objects.exists())
        self.provider.iniciar.assert_not_called()

    def test_asociacion_consulta_inactiva_y_cliente_inactivo(self):
        for campo, valor in (("rol_en_cliente", "CONSULTA"), ("activo", False)):
            original = getattr(self.asociacion, campo)
            setattr(self.asociacion, campo, valor)
            self.asociacion.save()
            with self.subTest(campo=campo), self.assertRaises(PermissionDenied):
                iniciar_pago(**self.argumentos())
            setattr(self.asociacion, campo, original)
            self.asociacion.save()
        self.cliente.dar_de_baja()
        with self.assertRaises(PermissionDenied):
            iniciar_pago(**self.argumentos())
        self.provider.iniciar.assert_not_called()

    def test_idempotencia_devuelve_estado_existente_sin_otro_inicio(self):
        primero = iniciar_pago(**self.argumentos())
        repetido = iniciar_pago(**self.argumentos())
        self.assertEqual(primero.pago_id, repetido.pago_id)
        self.assertTrue(repetido.reutilizado)
        self.assertEqual(self.provider.iniciar.call_count, 1)
        self.assertEqual(Pago.objects.count(), 1)

    def test_snapshots_incompatibles_impiden_reenvio(self):
        self.reservar_incierto()
        for campo, valor in (("monto_origen", Decimal("20")), ("metodo_pago", MetodoPago.objects.create(nombre="Otro"))):
            original = getattr(self.transaccion, campo)
            setattr(self.transaccion, campo, valor)
            self.transaccion.save()
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                iniciar_pago(**self.argumentos())
            setattr(self.transaccion, campo, original)
            self.transaccion.save()
        self.assertEqual(self.provider.iniciar.call_count, 1)

    def test_rechazo_persistido_sin_finalizacion_ni_reintento(self):
        self.provider.iniciar.side_effect = lambda s: self.resultado(s, EstadoPago.RECHAZADO)
        respuesta = iniciar_pago(**self.argumentos())
        self.assertEqual(respuesta.estado, EstadoPago.RECHAZADO)
        pago = Pago.objects.get(pk=respuesta.pago_id)
        self.assertIsNone(pago.aprobado_en)
        reintentar_pago(**self.argumentos())
        recuperar_pago(**self.argumentos())
        self.assertEqual(self.provider.iniciar.call_count, 1)
        self.provider.consultar.assert_not_called()

    def test_error_seguro_y_reintento_explicito_reutilizan_solicitud(self):
        self.provider.iniciar.side_effect = None
        self.provider.iniciar.return_value = ResultadoPago(EstadoPago.ERROR, CodigoResultado.ERROR_SIN_EJECUCION)
        primero = iniciar_pago(**self.argumentos())
        self.assertEqual(primero.estado, EstadoPago.ERROR)
        solicitud = self.provider.iniciar.call_args.args[0]
        iniciar_pago(**self.argumentos())
        self.assertEqual(self.provider.iniciar.call_count, 1)
        self.provider.iniciar.side_effect = lambda s: self.resultado(s)
        segundo = reintentar_pago(**self.argumentos())
        self.assertEqual(primero.pago_id, segundo.pago_id)
        self.assertEqual(self.provider.iniciar.call_args.args[0], solicitud)
        self.assertEqual([e["codigo"] for e in Pago.objects.get(pk=primero.pago_id).trazabilidad],
                         ["RESERVADO", "ERROR_SIN_EJECUCION", "REINTENTO", "APROBADO"])

    def test_timeout_indeterminado_no_reintenta_y_no_filtra_error(self):
        pago = self.reservar_incierto()
        respuesta = reintentar_pago(**self.argumentos())
        self.assertEqual(respuesta.estado, EstadoPago.INDETERMINADO)
        self.assertEqual(self.provider.iniciar.call_count, 1)
        self.assertNotIn("contenido externo", str(pago.trazabilidad) + respuesta.mensaje)

    def test_recuperacion_sin_referencia_concilia_sin_iniciar(self):
        pago = self.reservar_incierto()
        respuesta = recuperar_pago(**self.argumentos())
        self.assertEqual(respuesta.estado, EstadoPago.APROBADO)
        self.assertEqual(respuesta.pago_id, pago.pk)
        self.provider.conciliar_sin_referencia.assert_called_once()
        self.provider.consultar.assert_not_called()
        self.assertEqual(self.provider.iniciar.call_count, 1)

    def test_recuperacion_con_referencia_consulta_y_metodo_inactivo_no_oculta_evidencia(self):
        self.reservar_incierto(referencia="pi_existente")
        self.metodo.desactivar()
        respuesta = recuperar_pago(**self.argumentos())
        self.assertEqual(respuesta.estado, EstadoPago.APROBADO)
        self.assertEqual(self.provider.consultar.call_args.args[1], "pi_existente")
        self.provider.conciliar_sin_referencia.assert_not_called()
        self.assertEqual(self.provider.iniciar.call_count, 1)

    def test_consultas_negativas_vacias_o_fallidas_nunca_habilitan_error(self):
        self.reservar_incierto()
        for resultado in (
            ResultadoPago(EstadoPago.ERROR, CodigoResultado.ERROR_SIN_EJECUCION),
            ResultadoPago(EstadoPago.INDETERMINADO, CodigoResultado.RESULTADO_DESCONOCIDO),
            TimeoutError("404 o timeout ficticio"),
        ):
            self.provider.conciliar_sin_referencia.side_effect = None
            if isinstance(resultado, Exception):
                self.provider.conciliar_sin_referencia.side_effect = resultado
            else:
                self.provider.conciliar_sin_referencia.return_value = resultado
            with self.subTest(resultado=type(resultado).__name__):
                self.assertEqual(recuperar_pago(**self.argumentos()).estado, EstadoPago.INDETERMINADO)
        self.assertEqual(len(Pago.objects.get(transaccion=self.transaccion).trazabilidad), 2)

    def test_respuestas_invalidas_no_se_guardan_como_aprobacion(self):
        for cambios in (
            {"referencia_externa": None}, {"monto": Decimal("99")}, {"moneda": "EUR"},
            {"codigo": CodigoResultado.RECHAZADO}, {"referencia_externa": "referencia\n"},
        ):
            tx = self.crear_transaccion()
            def respuesta(solicitud):
                datos = dict(estado=EstadoPago.APROBADO, codigo=CodigoResultado.APROBADO,
                             referencia_externa="pi_valido", monto=solicitud.monto, moneda=solicitud.moneda)
                datos.update(cambios)
                return ResultadoPago(**datos)
            self.provider.iniciar.side_effect = respuesta
            with self.subTest(cambios=cambios):
                self.assertEqual(iniciar_pago(**self.argumentos(transaccion_id=tx.pk)).estado,
                                 EstadoPago.INDETERMINADO)

    def test_referencia_no_se_reemplaza(self):
        pago = self.reservar_incierto(referencia="pi_original")
        self.provider.consultar.side_effect = lambda s, ref: self.resultado(s, referencia="pi_otro")
        with self.assertLogs("pagos.services", level="WARNING"):
            respuesta = recuperar_pago(**self.argumentos())
        self.assertEqual(respuesta.anomalia, "REFERENCIA_CONTRADICTORIA")
        pago.refresh_from_db()
        self.assertEqual(pago.referencia_externa, "pi_original")
        self.assertEqual(pago.estado, Pago.Estado.INDETERMINADO)

    def test_fallo_local_despues_de_aprobacion_se_recupera_sin_otro_cobro(self):
        guardar = Pago.save
        def fallar(pago, *args, **kwargs):
            if pago.estado == Pago.Estado.APROBADO:
                raise DatabaseError("detalle local ficticio")
            return guardar(pago, *args, **kwargs)
        with patch.object(Pago, "save", autospec=True, side_effect=fallar):
            with self.assertLogs("pagos.services", level="ERROR"), self.assertRaises(PersistenciaPagoError):
                iniciar_pago(**self.argumentos())
        pago = Pago.objects.get(transaccion=self.transaccion)
        self.assertEqual(pago.estado, Pago.Estado.EN_PROCESO)
        self.assertEqual(recuperar_pago(**self.argumentos()).estado, EstadoPago.APROBADO)
        self.assertEqual(self.provider.iniciar.call_count, 1)

    def test_fallo_reserva_no_invoca_proveedor_y_atomic_externo_rechazado(self):
        with patch.object(Pago, "save", side_effect=DatabaseError("reserva")):
            with self.assertRaises(DatabaseError):
                iniciar_pago(**self.argumentos())
        self.assertFalse(Pago.objects.exists())
        with transaction.atomic(), self.assertRaises(ValidationError):
            iniciar_pago(**self.argumentos())
        self.provider.iniciar.assert_not_called()

    def test_revocacion_durante_io_no_impide_persistir_aprobacion(self):
        def aprobar(solicitud):
            self.asociacion.activo = False
            self.asociacion.save()
            self.cliente.dar_de_baja()
            return self.resultado(solicitud)
        self.provider.iniciar.side_effect = aprobar
        self.assertEqual(iniciar_pago(**self.argumentos()).estado, EstadoPago.APROBADO)

    def test_operacion_cambiada_durante_io_conserva_evidencia_y_reporta_anomalia(self):
        def aprobar(solicitud):
            Transaccion.objects.filter(pk=self.transaccion.pk).update(
                estado="CANCELADA", cancelado_por_keycloak_id="usuario-pagos",
                cancelado_por_username="operador", cancelado_en=timezone.now(), motivo_cancelacion="prueba",
            )
            return self.resultado(solicitud)
        self.provider.iniciar.side_effect = aprobar
        with self.assertLogs("pagos.services", level="WARNING"):
            respuesta = iniciar_pago(**self.argumentos())
        self.assertEqual(respuesta.estado, EstadoPago.APROBADO)
        self.assertEqual(respuesta.anomalia, "OPERACION_CAMBIADA")
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, "CANCELADA")

    def test_presupuesto_trazabilidad_impide_reintento_antes_de_io(self):
        self.provider.iniciar.side_effect = None
        self.provider.iniciar.return_value = ResultadoPago(EstadoPago.ERROR, CodigoResultado.ERROR_SIN_EJECUCION)
        respuesta = iniciar_pago(**self.argumentos())
        pago = Pago.objects.get(pk=respuesta.pago_id)
        pago.trazabilidad = [dict(pago.trazabilidad[0])] * 47
        pago.save()
        with self.assertRaises(ValidationError):
            reintentar_pago(**self.argumentos())
        self.assertEqual(self.provider.iniciar.call_count, 1)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.ERROR)

    def test_resultado_error_tardio_no_degrada_recuperacion_indeterminada(self):
        self.provider.conciliar_sin_referencia.side_effect = None
        self.provider.conciliar_sin_referencia.return_value = ResultadoPago(
            EstadoPago.INDETERMINADO, CodigoResultado.RESULTADO_DESCONOCIDO,
        )
        def iniciar(solicitud):
            recuperar_pago(**self.argumentos())
            return ResultadoPago(EstadoPago.ERROR, CodigoResultado.ERROR_SIN_EJECUCION)
        self.provider.iniciar.side_effect = iniciar
        self.assertEqual(iniciar_pago(**self.argumentos()).estado, EstadoPago.INDETERMINADO)

    def test_terminal_recuperado_no_se_degrada_por_respuesta_tardia(self):
        for terminal, tardio in (
            (EstadoPago.APROBADO, EstadoPago.RECHAZADO),
            (EstadoPago.RECHAZADO, EstadoPago.APROBADO),
        ):
            with self.subTest(terminal=terminal):
                tx = self.crear_transaccion()
                referencia = "pi_" + str(tx.pk)
                self.provider.conciliar_sin_referencia.side_effect = (
                    lambda s: self.resultado(s, terminal, referencia)
                )
                def iniciar(solicitud):
                    recuperar_pago(**self.argumentos(transaccion_id=tx.pk))
                    return self.resultado(solicitud, tardio, referencia)
                self.provider.iniciar.side_effect = iniciar
                with self.assertLogs("pagos.services", level="WARNING"):
                    respuesta = iniciar_pago(**self.argumentos(transaccion_id=tx.pk))
                self.assertEqual(respuesta.estado, terminal)
                self.assertEqual(respuesta.anomalia, "RESULTADO_TERMINAL_CONTRADICTORIO")
                pago = Pago.objects.get(pk=respuesta.pago_id)
                fecha = pago.aprobado_en
                if terminal == EstadoPago.APROBADO:
                    self.assertIsNotNone(fecha)
                else:
                    self.assertIsNone(fecha)
                recuperar_pago(**self.argumentos(transaccion_id=tx.pk))
                pago.refresh_from_db()
                self.assertEqual(pago.aprobado_en, fecha)
                self.assertEqual(pago.referencia_externa, referencia)

    def test_dos_inicios_o_reintentos_concurrentes_un_pago_y_una_autorizacion(self):
        if connection.vendor != "postgresql":
            self.skipTest("La prueba de locks requiere PostgreSQL real.")
        for funcion in (iniciar_pago, reintentar_pago):
            with self.subTest(funcion=funcion.__name__):
                tx = self.crear_transaccion()
                if funcion == reintentar_pago:
                    error = Mock(spec=PaymentProvider)
                    error.iniciar.return_value = ResultadoPago(EstadoPago.ERROR, CodigoResultado.ERROR_SIN_EJECUCION)
                    iniciar_pago(**self.argumentos(transaccion_id=tx.pk, provider=error))
                arrancar = Barrier(3)
                llamado, liberar = Event(), Event()
                provider = Mock(spec=PaymentProvider)
                def cobrar(solicitud):
                    self.assertFalse(connection.in_atomic_block)
                    llamado.set()
                    if not liberar.wait(timeout=10):
                        raise AssertionError("La segunda solicitud quedó bloqueada durante IO.")
                    return self.resultado(solicitud, referencia="pi_" + str(solicitud.pago_id))
                provider.iniciar.side_effect = cobrar
                def ejecutar():
                    close_old_connections()
                    try:
                        arrancar.wait(timeout=5)
                        return funcion(**self.argumentos(transaccion_id=tx.pk, provider=provider))
                    finally:
                        connections.close_all()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futuros = [pool.submit(ejecutar) for _ in range(2)]
                    try:
                        arrancar.wait(timeout=5)
                        self.assertTrue(llamado.wait(timeout=5))
                        terminados, _ = wait(futuros, timeout=5, return_when=FIRST_COMPLETED)
                        self.assertEqual(len(terminados), 1)
                        self.assertEqual(next(iter(terminados)).result().estado, EstadoPago.EN_PROCESO)
                    finally:
                        liberar.set()
                    resultados = [f.result(timeout=5) for f in futuros]
                self.assertEqual(len({r.pago_id for r in resultados}), 1)
                self.assertEqual(Pago.objects.filter(transaccion=tx).count(), 1)
                self.assertEqual(provider.iniciar.call_count, 1)
                self.assertEqual(Pago.objects.get(transaccion=tx).estado, Pago.Estado.APROBADO)
