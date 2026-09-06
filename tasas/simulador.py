from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.utils import timezone

from monedas.models import Moneda

from .models import TasaReferencia


PRECISION_RESULTADO = Decimal("0.0000000001")


@dataclass(frozen=True)
class ResultadoSimulacion:
    moneda_origen: Moneda
    moneda_destino: Moneda
    monto: Decimal
    tasa: Decimal
    tipo_tasa: str
    fecha_hora: object
    resultado: Decimal


def _convertir_monto(monto):
    """Convierte y valida el monto ingresado."""

    try:
        monto_decimal = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({"monto": "El monto debe ser numérico."})

    if not monto_decimal.is_finite() or monto_decimal <= 0:
        raise ValidationError({"monto": "El monto debe ser mayor que cero."})

    return monto_decimal


def _obtener_moneda_activa(moneda_id, campo):
    """Obtiene una moneda y verifica que se encuentre activa."""

    try:
        moneda = Moneda.objects.get(pk=moneda_id)
    except (Moneda.DoesNotExist, ValueError, TypeError):
        raise ValidationError({campo: "La moneda seleccionada no existe."})

    if moneda.estado != "ACTIVA":
        raise ValidationError(
            {campo: "La moneda seleccionada se encuentra inactiva."}
        )

    return moneda


def _buscar_tasa(moneda_origen, moneda_destino):
    """Busca una tasa de referencia vigente para el par directo o inverso."""

    ahora = timezone.now()
    tasa_directa = (
        TasaReferencia.objects.filter(
            moneda_base=moneda_origen,
            moneda_cotizada=moneda_destino,
            vigente_hasta__gte=ahora,
        ).first()
    )

    if tasa_directa:
        return tasa_directa.valor, tasa_directa.fecha_hora_fuente

    tasa_inversa = (
        TasaReferencia.objects.filter(
            moneda_base=moneda_destino,
            moneda_cotizada=moneda_origen,
            vigente_hasta__gte=ahora,
        ).first()
    )

    if tasa_inversa:
        return Decimal("1") / tasa_inversa.valor, tasa_inversa.fecha_hora_fuente

    raise ValidationError(
        {"tasa": "No existe una tasa disponible para la conversión seleccionada."}
    )


def simular_conversion(moneda_origen_id, moneda_destino_id, monto):
    """Simula una conversión sin generar una operación real."""

    moneda_origen = _obtener_moneda_activa(moneda_origen_id, "moneda_origen")
    moneda_destino = _obtener_moneda_activa(moneda_destino_id, "moneda_destino")

    if moneda_origen.id == moneda_destino.id:
        raise ValidationError(
            {"monedas": "La moneda de origen y destino deben ser diferentes."}
        )

    monto_decimal = _convertir_monto(monto)
    tasa, fecha_hora = _buscar_tasa(moneda_origen, moneda_destino)
    resultado = (monto_decimal * tasa).quantize(
        PRECISION_RESULTADO,
        rounding=ROUND_HALF_UP,
    )

    return ResultadoSimulacion(
        moneda_origen=moneda_origen,
        moneda_destino=moneda_destino,
        monto=monto_decimal,
        tasa=tasa,
        tipo_tasa="REFERENCIA",
        fecha_hora=fecha_hora,
        resultado=resultado,
    )
