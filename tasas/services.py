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


PRECISION_TASA = Decimal("0.0000000001")


def _convertir_tasa(valor, campo):
    """Convierte y valida un valor de tasa comercial."""

    # Si no se recibió un valor, se devuelve None.
    # Esto permite modificar solamente compra o solamente venta.
    if valor is None or valor == "":
        return None

    # Convertimos el valor recibido a Decimal para trabajar
    # correctamente con valores monetarios.
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

    # Las tasas comerciales siempre deben ser mayores que cero.
    if valor_decimal <= 0:
        raise ValidationError(
            {
                campo: (
                    "El valor debe ser mayor que cero."
                )
            }
        )

    # Se aplica la precisión definida para guardar la tasa.
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

    # La moneda de origen y la moneda de destino
    # deben ser diferentes.
    if moneda_origen_id == moneda_destino_id:
        raise ValidationError(
            {
                "monedas": (
                    "La moneda de origen y destino "
                    "deben ser diferentes."
                )
            }
        )

    # Buscamos la moneda de origen y comprobamos
    # que realmente exista.
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

    # Buscamos la moneda de destino.
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

    # No se pueden crear tasas nuevas utilizando
    # una moneda que se encuentre inactiva.
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

    # Convertimos y validamos los valores de compra y venta.
    compra_nueva = _convertir_tasa(
        compra,
        "compra",
    )

    venta_nueva = _convertir_tasa(
        venta,
        "venta",
    )

    # Se debe modificar por lo menos uno de los dos valores.
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

    # Buscamos todas las tasas que pertenecen al mismo par.
    # select_for_update evita que dos cambios simultáneos
    # modifiquen el versionado al mismo tiempo.
    tasas_del_par = (
        TasaComercial.objects
        .select_for_update()
        .filter(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
        )
    )

    # Obtenemos la tasa que está vigente actualmente.
    tasa_actual = (
        tasas_del_par
        .filter(vigente=True)
        .first()
    )

    # Buscamos la última versión registrada para continuar
    # correctamente con el número de versión.
    ultima_version = (
        tasas_del_par
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    )

    # Si todavía no existe una tasa vigente para este par,
    # se trata del primer registro.
    if tasa_actual is None:

        # Para la primera tasa es obligatorio ingresar
        # tanto compra como venta.
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

        # Si no se modificó la compra, conservamos
        # el valor que tenía la tasa actual.
        if compra_nueva is None:
            compra_nueva = (
                tasa_actual.compra
            )

        # Si no se modificó la venta, conservamos
        # el valor anterior.
        if venta_nueva is None:
            venta_nueva = (
                tasa_actual.venta
            )

        # Cada modificación crea una nueva versión.
        version = ultima_version + 1

        # La versión anterior deja de estar vigente,
        # pero no se elimina porque forma parte del historial.
        tasa_actual.vigente = False
        tasa_actual.save(
            update_fields=["vigente"]
        )

    # Creamos la nueva versión de la tasa comercial.
    # También guardamos quién realizó la modificación.
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

    # Ejecutamos las validaciones del modelo antes de guardar.
    nueva_tasa.full_clean()
    nueva_tasa.save()

    from .notificaciones import registrar_evento
    registrar_evento(nueva_tasa, tasa_actual)

    return nueva_tasa


@transaction.atomic
def desactivar_tasa_comercial(tasa_id):
    """Da de baja lógicamente una tasa sin eliminar su historial."""

    # Buscamos y bloqueamos la tasa mientras se realiza
    # la modificación.
    tasa = (
        TasaComercial.objects
        .select_for_update()
        .select_related(
            "moneda_origen",
            "moneda_destino",
        )
        .get(pk=tasa_id)
    )

    # Si ya estaba inactiva, no se puede volver
    # a realizar la misma acción.
    if not tasa.vigente:
        raise ValidationError(
            {
                "tasa": (
                    "La tasa comercial ya se encuentra inactiva."
                )
            }
        )

    # Se realiza una baja lógica: cambiamos el estado,
    # pero no eliminamos el registro de la base de datos.
    tasa.vigente = False
    tasa.save(
        update_fields=["vigente"]
    )

    return tasa
