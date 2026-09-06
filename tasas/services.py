from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from monedas.models import Moneda
from .models import TasaComercial


PRECISION_TASA = Decimal("0.000001")


def _convertir_tasa(valor, campo):
    """Convierte y valida un valor de tasa comercial."""
    if valor is None or valor == "":
        return None

    try:
        valor_decimal = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            {campo: "El valor ingresado no es válido."}
        )

    if valor_decimal <= 0:
        raise ValidationError(
            {campo: "El valor debe ser mayor que cero."}
        )

    return valor_decimal.quantize(
        PRECISION_TASA,
        rounding=ROUND_HALF_UP,
    )


@transaction.atomic
def actualizar_tasa_comercial(
    moneda_origen_id,
    moneda_destino_id,
    usuario_id,
    usuario_username="",
    compra=None,
    venta=None,
):
    """
    Crea una nueva versión de una tasa comercial.

    La versión anterior se conserva como histórica.
    Se permite modificar compra, venta o ambas.
    """

    if moneda_origen_id == moneda_destino_id:
        raise ValidationError(
            {
                "monedas": (
                    "La moneda de origen y destino deben ser diferentes."
                )
            }
        )

    try:
        moneda_origen = Moneda.objects.get(
            pk=moneda_origen_id
        )
    except Moneda.DoesNotExist:
        raise ValidationError(
            {
                "moneda_origen": (
                    "La moneda de origen no existe."
                )
            }
        )

    try:
        moneda_destino = Moneda.objects.get(
            pk=moneda_destino_id
        )
    except Moneda.DoesNotExist:
        raise ValidationError(
            {
                "moneda_destino": (
                    "La moneda de destino no existe."
                )
            }
        )

    if moneda_origen.estado != "ACTIVA":
        raise ValidationError(
            {
                "moneda_origen": (
                    "La moneda de origen debe estar activa."
                )
            }
        )

    if moneda_destino.estado != "ACTIVA":
        raise ValidationError(
            {
                "moneda_destino": (
                    "La moneda de destino debe estar activa."
                )
            }
        )

    compra_nueva = _convertir_tasa(
        compra,
        "compra",
    )

    venta_nueva = _convertir_tasa(
        venta,
        "venta",
    )

    if compra_nueva is None and venta_nueva is None:
        raise ValidationError(
            {
                "tasa": (
                    "Debe ingresar una tasa de compra y/o venta."
                )
            }
        )

    tasa_actual = (
        TasaComercial.objects
        .select_for_update()
        .filter(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            vigente=True,
        )
        .first()
    )

    if tasa_actual is None:
        if compra_nueva is None or venta_nueva is None:
            raise ValidationError(
                {
                    "tasa": (
                        "Para registrar la primera tasa del par "
                        "se deben indicar compra y venta."
                    )
                }
            )

        version = 1

    else:
        if compra_nueva is None:
            compra_nueva = tasa_actual.compra

        if venta_nueva is None:
            venta_nueva = tasa_actual.venta

        version = tasa_actual.version + 1

        tasa_actual.vigente = False
        tasa_actual.save(
            update_fields=["vigente"]
        )

    nueva_tasa = TasaComercial(
        moneda_origen=moneda_origen,
        moneda_destino=moneda_destino,
        compra=compra_nueva,
        venta=venta_nueva,
        vigente=True,
        version=version,
        usuario_id=usuario_id,
        usuario_username=usuario_username,
    )

    nueva_tasa.full_clean()
    nueva_tasa.save()

    return nueva_tasa