"""Límites monetarios compartidos por servicios, API y formulario de operaciones."""
from decimal import Decimal, DecimalException

from django.core.exceptions import ValidationError

from pagos.stripe_provider import StripePaymentProvider

from .models import Transaccion


CODIGOS_MONTO = frozenset({"MONTO_INVALIDO", "MONTO_EXCESIVO", "MONTO_PRECISION"})
MENSAJE_MONTO_INVALIDO = "Ingresá un monto válido mayor a cero."
MENSAJE_MONTO_EXCESIVO = "El monto ingresado supera el límite permitido para una operación."


def maximo_campo(nombre):
    campo = Transaccion._meta.get_field(nombre)
    # Construcción exacta; no depende de la precisión decimal global.
    return Decimal((0, (9,) * campo.max_digits, -campo.decimal_places))


def limites_monto_operacion(*, tipo=None, moneda_codigo=None, presencial=False):
    decimales = Transaccion._meta.get_field("monto_origen").decimal_places
    maximo = maximo_campo("monto_origen")
    if tipo == "COMPRA" and not presencial and moneda_codigo in StripePaymentProvider.DECIMALES:
        decimales = StripePaymentProvider.DECIMALES[moneda_codigo]
        maximo = min(maximo, Decimal((0, tuple(map(int, str(StripePaymentProvider.MAX_UNIDADES))), -decimales)))
    return {"maximo": str(maximo), "decimales": decimales,
            "minimo": str(Decimal((0, (1,), -decimales)))}


def especificacion_montos():
    return {
        "general": limites_monto_operacion(),
        "compra_online": {
            codigo: limites_monto_operacion(tipo="COMPRA", moneda_codigo=codigo)
            for codigo in StripePaymentProvider.DECIMALES
        },
    }


def validar_monto_operacion(monto, *, tipo=None, moneda_codigo=None, presencial=False):
    """Valida sin redondear ni expandir exponentes recibidos del usuario.

    Los ceros decimales sobrantes son representables y se eliminan para que
    DecimalField reciba la misma precisión que se aceptó en esta frontera.
    """
    try:
        valor = Decimal(str(monto))
    except (DecimalException, TypeError, ValueError):
        raise ValidationError(MENSAJE_MONTO_INVALIDO, code="MONTO_INVALIDO") from None
    if not valor.is_finite() or valor <= 0:
        raise ValidationError(MENSAJE_MONTO_INVALIDO, code="MONTO_INVALIDO")
    limites = limites_monto_operacion(tipo=tipo, moneda_codigo=moneda_codigo, presencial=presencial)
    if valor > Decimal(limites["maximo"]):
        raise ValidationError(MENSAJE_MONTO_EXCESIVO, code="MONTO_EXCESIVO")
    signo, digitos, exponente = valor.as_tuple()
    fin = len(digitos)
    while fin > 1 and digitos[fin - 1] == 0:
        fin -= 1
        exponente += 1
    if exponente < -limites["decimales"]:
        mensaje = ("Ingresá un monto sin decimales para esta moneda."
                   if limites["decimales"] == 0 else
                   f"Ingresá un monto con hasta {limites['decimales']} decimales.")
        raise ValidationError(mensaje, code="MONTO_PRECISION")
    return Decimal((signo, digitos[:fin], exponente))


def validar_resultados_operacion(importe_comision, monto_destino):
    """Controla únicamente los valores que se guardan, sin limitar el bruto."""
    if (not importe_comision.is_finite() or not monto_destino.is_finite()
        or importe_comision > maximo_campo("importe_comision")
        or monto_destino > maximo_campo("monto_destino")):
        raise ValidationError(MENSAJE_MONTO_EXCESIVO, code="MONTO_EXCESIVO")
    if monto_destino <= 0 or importe_comision < 0:
        raise ValidationError("El monto ingresado no permite obtener un importe de destino mayor a cero.",
                              code="MONTO_INVALIDO")
