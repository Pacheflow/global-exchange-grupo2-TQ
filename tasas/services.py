from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from monedas.models import Moneda

from .models import (
    ConsultaProveedorTasas,
    TasaComercial,
    TasaReferencia,
)
from .providers import ProveedorTasasError, ProveedorTasasHTTP



# HU-17 - Consultar y visualizar tasas de referencia



@dataclass(frozen=True)
class ResultadoConsultaTasas:
    """Resultado de la consulta de tasas de referencia."""

    estado: str
    tasas: list[TasaReferencia]
    mensaje: str | None = None


def _tasas_guardadas(moneda_base):
    """Obtiene las últimas tasas de referencia guardadas."""
    return list(
        TasaReferencia.objects.filter(
            moneda_base=moneda_base
        )
        .select_related(
            "moneda_base",
            "moneda_cotizada",
        )
        .order_by(
            "moneda_cotizada__codigo"
        )
    )


def consultar_tasas_referencia(*, proveedor=None):
    """
    Actualiza las tasas externas o devuelve
    el último dato válido como fallback.
    """

    try:
        moneda_base = Moneda.objects.get(
            codigo=settings.TASAS_BASE_CURRENCY,
            estado="ACTIVA",
        )
    except Moneda.DoesNotExist:
        return ResultadoConsultaTasas(
            estado="indisponible",
            tasas=[],
            mensaje=(
                "La moneda base configurada "
                "no existe o está inactiva."
            ),
        )

    cotizadas = list(
        Moneda.objects.activas().exclude(
            pk=moneda_base.pk
        )
    )

    if not cotizadas:
        return ResultadoConsultaTasas(
            estado="vacio",
            tasas=[],
            mensaje="No hay monedas activas para consultar.",
        )

    proveedor = proveedor or ProveedorTasasHTTP()

    try:
        respuesta = proveedor.obtener(
            moneda_base.codigo,
            [
                moneda.codigo
                for moneda in cotizadas
            ],
        )
    except ProveedorTasasError as exc:
        guardadas = _tasas_guardadas(
            moneda_base
        )

        return ResultadoConsultaTasas(
            estado=(
                "desactualizado"
                if guardadas
                else "indisponible"
            ),
            tasas=guardadas,
            mensaje=str(exc),
        )

    vigente_hasta = (
        respuesta.fecha_hora
        + timedelta(
            seconds=settings.TASAS_VALIDITY_SECONDS
        )
    )

    with transaction.atomic():
        consulta = ConsultaProveedorTasas.objects.create(
            fuente=respuesta.fuente,
            moneda_base=moneda_base,
            fecha_hora_fuente=respuesta.fecha_hora,
            respuesta=respuesta.respuesta_original,
        )

        for moneda in cotizadas:
            TasaReferencia.objects.update_or_create(
                moneda_base=moneda_base,
                moneda_cotizada=moneda,
                defaults={
                    "valor": respuesta.tasas[
                        moneda.codigo
                    ],
                    "fuente": respuesta.fuente,
                    "fecha_hora_fuente": (
                        respuesta.fecha_hora
                    ),
                    "vigente_hasta": vigente_hasta,
                    "consulta": consulta,
                },
            )

    tasas = _tasas_guardadas(
        moneda_base
    )

    estado = (
        "actualizado"
        if vigente_hasta >= timezone.now()
        else "desactualizado"
    )

    return ResultadoConsultaTasas(
        estado=estado,
        tasas=tasas,
    )



# HU-21 - Administrar tasas comerciales



PRECISION_TASA = Decimal("0.000001")


def _convertir_tasa(valor, campo):
    """Convierte y valida un valor de tasa comercial."""

    if valor is None or valor == "":
        return None

    try:
        valor_decimal = Decimal(
            str(valor)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            {
                campo: (
                    "El valor ingresado no es válido."
                )
            }
        )

    if valor_decimal <= 0:
        raise ValidationError(
            {
                campo: (
                    "El valor debe ser mayor que cero."
                )
            }
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
                    "La moneda de origen y destino "
                    "deben ser diferentes."
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

    if (
        compra_nueva is None
        and venta_nueva is None
    ):
        raise ValidationError(
            {
                "tasa": (
                    "Debe ingresar una tasa "
                    "de compra y/o venta."
                )
            }
        )

    tasas_del_par = (
        TasaComercial.objects
        .select_for_update()
        .filter(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
        )
    )
    tasa_actual = (
        tasas_del_par
        .filter(vigente=True)
        .first()
    )
    ultima_version = (
        tasas_del_par
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    )

    if tasa_actual is None:
        if (
            compra_nueva is None
            or venta_nueva is None
        ):
            raise ValidationError(
                {
                    "tasa": (
                        "Para registrar la primera "
                        "tasa del par se deben indicar "
                        "compra y venta."
                    )
                }
            )

        version = ultima_version + 1

    else:
        if compra_nueva is None:
            compra_nueva = (
                tasa_actual.compra
            )

        if venta_nueva is None:
            venta_nueva = (
                tasa_actual.venta
            )

        version = ultima_version + 1

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


@transaction.atomic
def desactivar_tasa_comercial(tasa_id):
    """Da de baja lógicamente una tasa sin eliminar su historial."""

    tasa = (
        TasaComercial.objects
        .select_for_update()
        .select_related("moneda_origen", "moneda_destino")
        .get(pk=tasa_id)
    )
    if not tasa.vigente:
        raise ValidationError(
            {"tasa": "La tasa comercial ya se encuentra inactiva."}
        )

    tasa.vigente = False
    tasa.save(update_fields=["vigente"])
    return tasa
