"""HU-S6-02: contrato financiero común, sin alterar el flujo transaccional.

Ganancia = comisión de transacciones completadas. La fecha de imputación es
fecha_creacion (cohortes de operaciones), no una fecha de liquidación inferida.
Solo la tasa aplicada e inmutable de la operación permite convertir a PYG.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Transaccion

MONEDA = "PYG"
PRECISION = Decimal("0.000001")
MAX_DIAS = 366


def importes_pyg(operacion):
    """Devuelve volumen bruto y comisión en PYG; None si falta conversión fiable.

    El volumen contabiliza una sola pata del intercambio, antes de comisiones.
    No utiliza tasas actuales ni el catálogo mutable de tasas comerciales.
    """
    with localcontext() as ctx:
        ctx.prec = 64
        if operacion.moneda_destino.codigo == MONEDA:
            return (operacion.monto_origen * operacion.tasa_aplicada,
                    operacion.importe_comision)
        if operacion.moneda_origen.codigo == MONEDA:
            return (operacion.monto_origen,
                    operacion.importe_comision / operacion.tasa_aplicada)
    return None


def _inicio_periodo(fecha, agrupacion):
    if agrupacion == "semana":
        return fecha - timedelta(days=fecha.weekday())
    if agrupacion == "mes":
        return fecha.replace(day=1)
    return fecha


def _siguiente(fecha, agrupacion):
    if agrupacion == "mes":
        return (fecha.replace(day=28) + timedelta(days=4)).replace(day=1)
    return fecha + timedelta(days=7 if agrupacion == "semana" else 1)


def _acumulador():
    return dict(operaciones=0, compras=0, ventas=0, operaciones_convertidas=0,
                operaciones_sin_conversion=0, volumen=Decimal(0), comisiones=Decimal(0))


def _sumar(destino, operacion, importes):
    destino["operaciones"] += 1
    destino["compras" if operacion.tipo == "COMPRA" else "ventas"] += 1
    if importes is None:
        destino["operaciones_sin_conversion"] += 1
    else:
        destino["operaciones_convertidas"] += 1
        destino["volumen"] += importes[0]
        destino["comisiones"] += importes[1]


def _serializar(valores):
    resultado = dict(valores)
    for campo in ("volumen", "comisiones"):
        resultado[campo] = format(valores[campo].quantize(PRECISION, rounding=ROUND_HALF_UP), "f")
    resultado["ganancia"] = resultado["comisiones"]
    resultado["completo"] = valores["operaciones_sin_conversion"] == 0
    return resultado


def reporte_financiero(*, desde, hasta, agrupacion="dia"):
    """Agrega un rango inclusivo local de hasta 366 días; incluye períodos vacíos.

    Los buckets extremos pueden ser parciales: solo incluyen el rango solicitado.
    El límite temporal acota el reporte; iterator evita materializar las filas.
    """
    if agrupacion not in {"dia", "semana", "mes"}:
        raise ValidationError("Agrupación inválida: usá dia, semana o mes.")
    if desde > hasta or (hasta - desde).days >= MAX_DIAS:
        raise ValidationError("El período debe estar ordenado y abarcar como máximo 366 días.")
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(desde, time.min), tz)
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min), tz)
    operaciones = Transaccion.objects.filter(
        estado="COMPLETADA", fecha_creacion__gte=inicio, fecha_creacion__lt=fin,
    ).select_related("moneda_origen", "moneda_destino").order_by("pk")
    buckets = {}
    fecha = _inicio_periodo(desde, agrupacion)
    while fecha <= hasta:
        buckets[fecha] = _acumulador()
        fecha = _siguiente(fecha, agrupacion)
    total = _acumulador()
    sin_conversion = {}
    with localcontext() as ctx:
        ctx.prec = 64
        for operacion in operaciones.iterator(chunk_size=1000):
            fecha = timezone.localtime(operacion.fecha_creacion, tz).date()
            importes = importes_pyg(operacion)
            _sumar(total, operacion, importes)
            _sumar(buckets[_inicio_periodo(fecha, agrupacion)], operacion, importes)
            if importes is None:
                par = f"{operacion.moneda_origen.codigo}/{operacion.moneda_destino.codigo}"
                sin_conversion[par] = sin_conversion.get(par, 0) + 1
        resultado = {
            "version": 1, "moneda": MONEDA, "definicion_ganancia": "COMISIONES",
            "fecha_imputacion": "fecha_creacion", "estado": "COMPLETADA",
            "zona_horaria": str(tz), "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "agrupacion": agrupacion, "totales": _serializar(total),
            "periodos": [dict(inicio=fecha.isoformat(),
                              desde=max(fecha, desde).isoformat(),
                              hasta=min(_siguiente(fecha, agrupacion) - timedelta(days=1), hasta).isoformat(),
                              **_serializar(valores)) for fecha, valores in buckets.items()],
            "sin_conversion": [dict(par=par, operaciones=cantidad)
                               for par, cantidad in sorted(sin_conversion.items())],
            "advertencias": [],
        }
    if sin_conversion:
        resultado["advertencias"].append(
            "Importes parciales: hay operaciones sin PYG en el par. Sus cantidades sí están incluidas."
        )
    return resultado
