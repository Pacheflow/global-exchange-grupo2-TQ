"""Orquestación interna: reserva local, proveedor fuera de locks y recuperación.

No completa operaciones. La cancelación comparte el orden Transaccion -> Pago
y protege los estados que pueden tener ejecución externa. El proveedor se
inyecta desde una capa de confianza configurada exclusivamente para TEST.
"""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from clientes.models import UsuarioCliente
from operaciones.models import Transaccion
from usuarios.services.keycloak import rol_efectivo

from .models import Pago
from .providers import CodigoResultado, EstadoPago, PaymentProvider, ResultadoPago, SolicitudPago


logger = logging.getLogger(__name__)
PROVEEDOR_TEST = "stripe"
TERMINALES = frozenset({Pago.Estado.APROBADO, Pago.Estado.RECHAZADO})
ERRORES_SEGUROS = frozenset({
    CodigoResultado.SOLICITUD_INVALIDA, CodigoResultado.CONFIGURACION_INVALIDA,
    CodigoResultado.ERROR_SIN_EJECUCION,
})


class PersistenciaPagoError(RuntimeError):
    """La reserva existe; recuperar el mismo pago, nunca iniciar otro cobro."""


@dataclass(frozen=True)
class EstadoPagoPersistido:
    pago_id: UUID
    estado: EstadoPago
    codigo: CodigoResultado
    reutilizado: bool
    anomalia: str | None = None

    @property
    def mensaje(self):
        return ResultadoPago(self.estado, self.codigo).mensaje


@dataclass(frozen=True)
class _Reserva:
    solicitud: SolicitudPago
    version: tuple
    cliente_id: int
    metodo_pago_id: int


def _exigir_autocommit():
    # Un savepoint dentro de una transacción externa no hace durable la reserva.
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ValidationError("El pago requiere una transacción independiente.", code="TRANSACCION_EXTERNA")


def _bloquear(transaccion_id):
    try:
        transaccion = (
            Transaccion.objects.select_related("cliente", "moneda_origen", "metodo_pago")
            .select_for_update(of=("self",)).get(pk=transaccion_id)
        )
    except Transaccion.DoesNotExist:
        raise ValidationError("La operación no existe.", code="OPERACION_INEXISTENTE") from None
    pago = Pago.objects.select_for_update(of=("self",)).filter(transaccion_id=transaccion.pk).first()
    return transaccion, pago


def _autorizar(transaccion, usuario_id, roles, cliente_seleccionado_id):
    if not isinstance(usuario_id, str) or not usuario_id.strip() or len(usuario_id) > 255:
        raise PermissionDenied("Identidad inválida.")
    if not isinstance(roles, (list, tuple, set, frozenset)) or not all(isinstance(r, str) for r in roles):
        raise PermissionDenied("Roles inválidos.")
    usuario_id = usuario_id.strip()
    if (
        rol_efectivo(roles) not in {"CAJERO", "USUARIO"}
        or type(cliente_seleccionado_id) is not int
        or cliente_seleccionado_id != transaccion.cliente_id
        or transaccion.cliente.estado != "ACTIVO"
        or not UsuarioCliente.objects.filter(
            cliente_id=transaccion.cliente_id, keycloak_user_id=usuario_id,
            activo=True, rol_en_cliente__in=("RESPONSABLE", "OPERADOR"),
        ).exists()
    ):
        raise PermissionDenied("No tiene permiso para procesar el pago de esta operación.")
    return usuario_id


def _elegible(transaccion):
    if transaccion.tipo != "COMPRA":
        raise ValidationError("Solo las compras utilizan este servicio de pago.", code="TIPO_NO_ADMITIDO")
    if transaccion.estado != "PENDIENTE":
        raise ValidationError("La operación debe estar pendiente.", code="OPERACION_NO_PENDIENTE")
    if not transaccion.metodo_pago.activo:
        raise ValidationError("El método de pago no está habilitado.", code="METODO_INACTIVO")


def _validar_snapshots(transaccion, pago):
    if (
        pago.proveedor != PROVEEDOR_TEST or pago.metodo_pago_id != transaccion.metodo_pago_id
        or pago.monto != transaccion.monto_origen
        or pago.moneda_codigo != transaccion.moneda_origen.codigo
        or pago.base_importe != Pago.BaseImporte.ORIGEN
        or pago.huella_solicitud != pago.calcular_huella()
    ):
        raise ValidationError("La obligación difiere de la reserva del pago.", code="OBLIGACION_CAMBIADA")


def _evento(estado, codigo):
    return {"fecha": timezone.now().isoformat(), "estado": str(estado), "codigo": codigo}


def _asegurar_espacio(pago):
    # Reserva/reintento, primera referencia, incertidumbre y resultado terminal.
    # No se registran polls repetidos y nunca se recorta evidencia histórica.
    peor_evento = {
        "fecha": "9999-12-31T23:59:59.999999+00:00", "estado": "INDETERMINADO",
        "codigo": "RESULTADO_DESCONOCIDO",
    }
    futuros = pago.trazabilidad + [peor_evento] * 4
    if (
        len(futuros) > Pago.MAX_EVENTOS_TRAZABILIDAD
        or len(json.dumps(futuros, ensure_ascii=False).encode("utf-8")) > Pago.MAX_BYTES_TRAZABILIDAD
    ):
        raise ValidationError("No hay capacidad para registrar otro intento seguro.", code="TRAZABILIDAD_AGOTADA")


def _version(pago):
    return (
        pago.fecha_actualizacion, pago.estado, pago.referencia_externa,
        json.dumps(pago.trazabilidad, sort_keys=True, separators=(",", ":")),
    )


def _reserva(transaccion, pago):
    return _Reserva(
        SolicitudPago(pago.id, transaccion.id, pago.monto, pago.moneda_codigo, pago.huella_solicitud),
        _version(pago), transaccion.cliente_id, pago.metodo_pago_id,
    )


def _respuesta(pago, *, reutilizado, anomalia=None):
    codigo = {
        Pago.Estado.EN_PROCESO: CodigoResultado.EN_PROCESO,
        Pago.Estado.APROBADO: CodigoResultado.APROBADO,
        Pago.Estado.RECHAZADO: CodigoResultado.RECHAZADO,
        Pago.Estado.ERROR: CodigoResultado.ERROR_SIN_EJECUCION,
        Pago.Estado.INDETERMINADO: CodigoResultado.RESULTADO_DESCONOCIDO,
    }[pago.estado]
    return EstadoPagoPersistido(pago.id, EstadoPago(pago.estado), codigo, reutilizado, anomalia)


def _incierto():
    return ResultadoPago(EstadoPago.INDETERMINADO, CodigoResultado.RESULTADO_DESCONOCIDO)


def _normalizar(resultado, solicitud, *, consulta):
    """Defensa del contrato neutral, sin interpretar objetos o errores del SDK."""
    if not isinstance(resultado, ResultadoPago):
        return _incierto()
    if not isinstance(resultado.estado, EstadoPago) or not isinstance(resultado.codigo, CodigoResultado):
        return _incierto()
    coherente = {
        EstadoPago.APROBADO: {CodigoResultado.APROBADO},
        EstadoPago.RECHAZADO: {CodigoResultado.RECHAZADO},
        EstadoPago.EN_PROCESO: {CodigoResultado.EN_PROCESO},
        EstadoPago.ERROR: ERRORES_SEGUROS,
        EstadoPago.INDETERMINADO: {
            CodigoResultado.RESULTADO_DESCONOCIDO, CodigoResultado.RESPUESTA_INVALIDA,
            *ERRORES_SEGUROS,
        },
    }
    if resultado.codigo not in coherente[resultado.estado]:
        return _incierto()
    referencia = resultado.referencia_externa
    if referencia is not None and (
        not isinstance(referencia, str) or not referencia or referencia != referencia.strip()
        or len(referencia) > 255 or any(ord(c) < 32 for c in referencia)
    ):
        return _incierto()
    datos_presentes = resultado.monto is not None or resultado.moneda is not None or referencia is not None
    if datos_presentes and (
        not isinstance(resultado.monto, Decimal) or not resultado.monto.is_finite()
        or resultado.monto != solicitud.monto or resultado.moneda != solicitud.moneda
    ):
        return _incierto()
    if resultado.estado == EstadoPago.APROBADO and referencia is None:
        return _incierto()
    if resultado.estado == EstadoPago.RECHAZADO and not datos_presentes:
        return _incierto()
    if resultado.estado == EstadoPago.ERROR and (consulta or referencia is not None):
        return _incierto()
    return resultado


def _persistir(reserva, resultado, *, consulta, reutilizado):
    try:
        with transaction.atomic(durable=True):
            transaccion, pago = _bloquear(reserva.solicitud.transaccion_id)
            if pago is None or _reserva(transaccion, pago).solicitud != reserva.solicitud:
                raise ValidationError("La reserva del pago cambió.", code="RESERVA_CAMBIADA")
            resultado = _normalizar(resultado, reserva.solicitud, consulta=consulta)
            referencia = resultado.referencia_externa
            if pago.referencia_externa and referencia and pago.referencia_externa != referencia:
                logger.warning("PAGO_REFERENCIA_CONTRADICTORIA pago=%s", pago.pk)
                return _respuesta(pago, reutilizado=reutilizado, anomalia="REFERENCIA_CONTRADICTORIA")
            if pago.estado in TERMINALES:
                anomalia = None
                if resultado.estado in TERMINALES and resultado.estado != pago.estado:
                    anomalia = "RESULTADO_TERMINAL_CONTRADICTORIO"
                    logger.warning("PAGO_TERMINAL_CONTRADICTORIO pago=%s", pago.pk)
                return _respuesta(pago, reutilizado=reutilizado, anomalia=anomalia)
            # Una respuesta de error/procesamiento antigua no revierte recuperación.
            if _version(pago) != reserva.version and resultado.estado not in TERMINALES:
                return _respuesta(pago, reutilizado=reutilizado)
            estado = str(resultado.estado)
            if estado == Pago.Estado.ERROR and (
                consulta or pago.estado != Pago.Estado.EN_PROCESO or pago.referencia_externa
            ):
                estado = Pago.Estado.INDETERMINADO
            if pago.estado == Pago.Estado.INDETERMINADO and estado == Pago.Estado.EN_PROCESO:
                estado = Pago.Estado.INDETERMINADO
            referencia_nueva = referencia is not None and pago.referencia_externa is None
            cambio_estado = pago.estado != estado
            if not cambio_estado and not referencia_nueva:
                return _respuesta(pago, reutilizado=reutilizado)
            pago.estado = estado
            if referencia_nueva:
                pago.referencia_externa = referencia
            if estado == Pago.Estado.APROBADO:
                pago.aprobado_en = pago.aprobado_en or timezone.now()
            codigo = {
                Pago.Estado.APROBADO: "APROBADO", Pago.Estado.RECHAZADO: "RECHAZADO",
                Pago.Estado.ERROR: "ERROR_SIN_EJECUCION",
                Pago.Estado.INDETERMINADO: "RESULTADO_DESCONOCIDO",
                Pago.Estado.EN_PROCESO: "CONSULTADO",
            }[estado]
            pago.trazabilidad = pago.trazabilidad + [_evento(estado, codigo)]
            pago.save()
            # No reevaluar permisos después de IO: conservar evidencia del cobro.
            anomalia = None
            if (
                transaccion.estado != "PENDIENTE" or transaccion.tipo != "COMPRA"
                or transaccion.cliente_id != reserva.cliente_id
                or transaccion.metodo_pago_id != reserva.metodo_pago_id
                or transaccion.monto_origen != pago.monto
                or transaccion.moneda_origen.codigo != pago.moneda_codigo
            ):
                anomalia = "OPERACION_CAMBIADA"
                logger.warning("PAGO_OPERACION_CAMBIADA pago=%s", pago.pk)
            return _respuesta(pago, reutilizado=reutilizado, anomalia=anomalia)
    except (DatabaseError, ValidationError):
        logger.error("PAGO_PERSISTENCIA_PENDIENTE pago=%s", reserva.solicitud.pago_id)
        raise PersistenciaPagoError("No se pudo persistir el resultado; recuperar el mismo pago.") from None


def _invocar(provider, reserva, *, consulta, referencia=None, reutilizado=False):
    # Reserva ya confirmada; ningún lock ni transacción durante IO externo.
    try:
        if consulta:
            resultado = (
                provider.consultar(reserva.solicitud, referencia) if referencia
                else provider.conciliar_sin_referencia(reserva.solicitud)
            )
        else:
            resultado = provider.iniciar(reserva.solicitud)
    except Exception:
        # Nunca serializar el mensaje, payload o traceback externo.
        resultado = _incierto()
    return _persistir(reserva, resultado, consulta=consulta, reutilizado=reutilizado)


def iniciar_pago(*, transaccion_id, usuario_id, roles, cliente_seleccionado_id, provider: PaymentProvider):
    """Reservar una COMPRA; una repetición nunca autoriza otro cobro."""
    _exigir_autocommit()
    with transaction.atomic(durable=True):
        transaccion, pago = _bloquear(transaccion_id)
        identidad = _autorizar(transaccion, usuario_id, roles, cliente_seleccionado_id)
        _elegible(transaccion)
        if pago is not None:
            _validar_snapshots(transaccion, pago)
            return _respuesta(pago, reutilizado=True)
        pago = Pago(
            transaccion=transaccion, metodo_pago=transaccion.metodo_pago, proveedor=PROVEEDOR_TEST,
            monto=transaccion.monto_origen, moneda_codigo=transaccion.moneda_origen.codigo,
            base_importe=Pago.BaseImporte.ORIGEN, iniciado_por_keycloak_id=identidad,
        )
        _asegurar_espacio(pago)
        pago.trazabilidad = [_evento(Pago.Estado.EN_PROCESO, "RESERVADO")]
        pago.save()
        reserva = _reserva(transaccion, pago)
    return _invocar(provider, reserva, consulta=False)


def reintentar_pago(*, transaccion_id, usuario_id, roles, cliente_seleccionado_id, provider: PaymentProvider):
    """Reintento explícito solo cuando está certificada la no ejecución."""
    _exigir_autocommit()
    with transaction.atomic(durable=True):
        transaccion, pago = _bloquear(transaccion_id)
        _autorizar(transaccion, usuario_id, roles, cliente_seleccionado_id)
        _elegible(transaccion)
        if pago is None:
            raise ValidationError("No existe un pago para reintentar.", code="PAGO_INEXISTENTE")
        _validar_snapshots(transaccion, pago)
        if pago.estado != Pago.Estado.ERROR:
            return _respuesta(pago, reutilizado=True)
        if pago.referencia_externa is not None:
            raise ValidationError("El pago requiere recuperación.", code="REQUIERE_RECUPERACION")
        _asegurar_espacio(pago)
        pago.estado = Pago.Estado.EN_PROCESO
        pago.trazabilidad = pago.trazabilidad + [_evento(pago.estado, "REINTENTO")]
        pago.save()
        reserva = _reserva(transaccion, pago)
    return _invocar(provider, reserva, consulta=False, reutilizado=True)


def recuperar_pago(*, transaccion_id, usuario_id, roles, cliente_seleccionado_id, provider: PaymentProvider):
    """Consultar evidencia externa; jamás crear, confirmar ni reintentar cobros."""
    _exigir_autocommit()
    with transaction.atomic(durable=True):
        transaccion, pago = _bloquear(transaccion_id)
        _autorizar(transaccion, usuario_id, roles, cliente_seleccionado_id)
        if pago is None:
            raise ValidationError("No existe un pago para recuperar.", code="PAGO_INEXISTENTE")
        if pago.proveedor != PROVEEDOR_TEST or pago.huella_solicitud != pago.calcular_huella():
            raise ValidationError("La reserva del pago es inválida.", code="RESERVA_INVALIDA")
        if pago.estado not in {Pago.Estado.EN_PROCESO, Pago.Estado.INDETERMINADO}:
            return _respuesta(pago, reutilizado=True)
        reserva, referencia = _reserva(transaccion, pago), pago.referencia_externa
    return _invocar(provider, reserva, consulta=True, referencia=referencia, reutilizado=True)


def consultar_estado_pago(*, transaccion_id, usuario_id, roles, cliente_seleccionado_id):
    """Leer evidencia local autorizada, incluso histórica; sin locks ni proveedor."""
    try:
        transaccion = Transaccion.objects.select_related("cliente", "pago").get(pk=transaccion_id)
    except Transaccion.DoesNotExist:
        raise ValidationError("La operación no existe.", code="OPERACION_INEXISTENTE") from None
    _autorizar(transaccion, usuario_id, roles, cliente_seleccionado_id)
    if transaccion.tipo != "COMPRA":
        raise ValidationError("Solo las compras utilizan este servicio de pago.", code="TIPO_NO_ADMITIDO")
    try:
        pago = transaccion.pago
    except Pago.DoesNotExist:
        return None
    return _respuesta(pago, reutilizado=True)
