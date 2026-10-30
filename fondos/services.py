"""Protocolo financiero: Operación → Pago → Reserva → Fondos ordenados por moneda.

Cada escritura bloquea Fondo; ningún bloqueo se mantiene durante IO externo.
Las cargas solo bloquean Fondo y nunca adquieren luego locks de operaciones.
"""
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum

from monedas.models import Moneda
from usuarios.services.keycloak import rol_efectivo
from .models import Fondo, MovimientoFondo, ReservaFondo, FinalizacionOnline, OperacionCompletada


def autorizar_admin(usuario_id, roles):
    """Exige identidad Keycloak y rol efectivo administrativo también en servicios."""
    if (not isinstance(usuario_id, str) or not usuario_id.strip()
        or not isinstance(roles, (list, tuple, set, frozenset))
        or not all(isinstance(rol, str) for rol in roles)
        or rol_efectivo(roles) != "ADMINISTRADOR"):
        raise PermissionDenied("Solo ADMINISTRADOR puede administrar Fondos.")


def importe_positivo(valor):
    """Rechaza importes no finitos, negativos, cero o precisión excesiva sin redondear."""
    try:
        monto = Decimal(str(valor))
        if not monto.is_finite() or monto <= 0 or monto >= Decimal("1000000000000") or monto.as_tuple().exponent < -6:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Ingresá un importe positivo de hasta 6 decimales y 12 enteros.") from None
    return monto


def saldos(fondo):
    """Obtiene registrado, reservado y disponible sin mezclar monedas."""
    valores = {fila["tipo"]: fila["total"] for fila in fondo.movimientos.values("tipo").annotate(total=Sum("monto"))}
    registrado = valores.get("INGRESO", Decimal(0)) - valores.get("EGRESO", Decimal(0))
    reservado = fondo.reservas.filter(estado="ACTIVA").aggregate(total=Sum("monto"))["total"] or Decimal(0)
    return registrado, reservado, registrado - reservado


def consultar(*, usuario_id, roles):
    """Consulta administrativa protegida sin crear fondos por lectura."""
    autorizar_admin(usuario_id, roles)
    return [(f, *saldos(f)) for f in Fondo.objects.select_related("moneda").order_by("moneda__codigo")]


def cargar(*, moneda_id, monto, motivo, clave, usuario_id, roles):
    """Carga idempotente con actor del servidor y bloqueo del fondo único."""
    autorizar_admin(usuario_id, roles)
    monto = importe_positivo(monto)
    motivo = str(motivo).strip()
    if not motivo or len(motivo) > 255:
        raise ValidationError("El motivo es obligatorio y admite hasta 255 caracteres.")
    try:
        clave = f"carga:{UUID(str(clave))}"
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("La clave de la carga no es válida.") from None
    with transaction.atomic():
        # La unicidad serializa altas concurrentes. No bloquear Moneda: una
        # inserción de Fondo puede necesitar su FK antes de bloquear los fondos.
        moneda = Moneda.objects.get(pk=moneda_id)
        if moneda.estado != "ACTIVA":
            raise ValidationError("La moneda debe estar activa.")
        fondo, _ = Fondo.objects.get_or_create(moneda=moneda)
        fondo = Fondo.objects.select_for_update().get(pk=fondo.pk)
        existente = MovimientoFondo.objects.filter(clave=clave).first()
        if existente:
            if (existente.fondo_id, existente.monto, existente.motivo, existente.responsable) != (fondo.pk, monto, motivo, usuario_id):
                raise ValidationError("La solicitud ya fue utilizada con otros datos.")
            return existente
        return MovimientoFondo.objects.create(fondo=fondo, tipo="INGRESO", monto=monto, motivo=motivo,
                                             clave=clave, responsable=usuario_id)


def exigir_flujo(op, canal="ONLINE"):
    """No adivina el canal de registros heredados ni los procesa automáticamente."""
    if op.version_flujo != 1 or op.canal != canal:
        raise ValidationError("La operación requiere revisión del flujo histórico.", code="REVISION_PENDIENTE")


def hay_disponibilidad(*, moneda_id, monto):
    """Lectura informativa; el cobro reserva y la VENTA revalida bajo bloqueo."""
    fondo = Fondo.objects.filter(moneda_id=moneda_id).first()
    return fondo is not None and saldos(fondo)[2] >= monto


def _bloquear_fondos(op):
    """Adquiere todas las monedas en orden determinista, sin crear saldos iniciales."""
    # El ingreso puede necesitar una fila sin financiación previa. get_or_create
    # recorre también un orden común; la unicidad serializa altas concurrentes.
    for moneda_id in sorted({op.moneda_origen_id, op.moneda_destino_id}):
        Fondo.objects.get_or_create(moneda_id=moneda_id)
    return {f.moneda_id: f for f in Fondo.objects.select_for_update().filter(
        moneda_id__in=[op.moneda_origen_id, op.moneda_destino_id]).order_by("moneda_id")}


def _insuficiente():
    raise ValidationError("No hay disponibilidad suficiente para procesar esta operación. No se realizó ningún cobro en este intento. Intenta más tarde.", code="DISPONIBILIDAD_INSUFICIENTE")


def reservar(op):
    """Reserva destino antes del proveedor; requiere la operación ya bloqueada."""
    exigir_flujo(op)
    reserva = ReservaFondo.objects.select_for_update().filter(operacion=op).first()
    fondos = _bloquear_fondos(op)
    destino = fondos[op.moneda_destino_id]
    if reserva and reserva.estado == "ACTIVA":
        if reserva.fondo_id != destino.pk or reserva.monto != op.monto_destino:
            raise ValidationError("La reserva no coincide con la operación.")
        return reserva
    if reserva and reserva.estado == "CONSUMIDA":
        raise ValidationError("La reserva ya fue consumida.")
    if saldos(destino)[2] < op.monto_destino:
        _insuficiente()
    if reserva:
        reserva.estado = "ACTIVA"
        reserva.save(update_fields=["estado", "actualizada_en"])
    else:
        reserva = ReservaFondo.objects.create(operacion=op, fondo=destino, monto=op.monto_destino)
    return reserva


def liberar(op):
    """Libera solo desde resultados certificados, nunca por tiempo transcurrido."""
    reserva = ReservaFondo.objects.select_for_update().filter(operacion=op).first()
    if reserva and reserva.estado == "ACTIVA":
        Fondo.objects.select_for_update().get(pk=reserva.fondo_id)
        reserva.estado = "LIBERADA"
        reserva.save(update_fields=["estado", "actualizada_en"])


def finalizar(op, pago=None):
    """Finaliza atómicamente desde evidencia; el llamador bloquea Operación y Pago."""
    exigir_flujo(op)
    if op.estado == "COMPLETADA":
        if not FinalizacionOnline.objects.filter(operacion=op).exists():
            raise ValidationError("Falta evidencia de finalización.")
        return
    if op.estado != "PENDIENTE" or op.naturaleza_metodo != "ELECTRONICO":
        raise ValidationError("La operación no admite finalización online.")
    reserva = ReservaFondo.objects.select_for_update().filter(operacion=op).first()
    if op.tipo == "COMPRA":
        from pagos.services import _validar_snapshots
        if pago is None or pago.estado != "APROBADO":
            raise ValidationError("Se requiere Pago aprobado.")
        _validar_snapshots(op, pago)
        pago.full_clean()
        if not reserva or reserva.estado != "ACTIVA" or reserva.monto != op.monto_destino:
            raise ValidationError("Falta la reserva válida de destino.")
        fuente, referencia = "STRIPE_TEST", pago.referencia_externa
    else:
        fuente, referencia = "VENTA_SIMULADA", f"venta-simulada:{op.pk}"
    fondos = _bloquear_fondos(op)
    destino = fondos[op.moneda_destino_id]
    if reserva and reserva.fondo_id != destino.pk:
        raise ValidationError("La moneda reservada no coincide.")
    # La reserva propia se consume; no se gasta el disponible de otras operaciones.
    necesario = op.monto_destino if op.tipo == "VENTA" else Decimal(0)
    if saldos(destino)[2] < necesario:
        _insuficiente()
    for tipo, moneda_id, monto in [("INGRESO", op.moneda_origen_id, op.monto_origen),
                                   ("EGRESO", op.moneda_destino_id, op.monto_destino)]:
        MovimientoFondo.objects.create(fondo=fondos[moneda_id], tipo=tipo, monto=monto, operacion=op,
            clave=f"operacion:{op.pk}:{tipo}", motivo=f"Intercambio {op.tipo}", referencia=referencia,
            responsable=op.creado_por_keycloak_id)
    FinalizacionOnline.objects.create(operacion=op, fuente=fuente, referencia=referencia,
        monto_recibido=op.monto_origen, moneda_codigo=op.moneda_origen.codigo)
    if reserva:
        reserva.estado = "CONSUMIDA"
        reserva.save(update_fields=["estado", "actualizada_en"])
    op.estado = "COMPLETADA"
    op.save(update_fields=["estado", "fecha_actualizacion"])
    OperacionCompletada.objects.get_or_create(operacion=op)
