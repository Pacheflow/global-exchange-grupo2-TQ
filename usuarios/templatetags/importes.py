"""Formato común de importes para vistas administrativas, sin redondeo."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from django import template
from django.utils.numberformat import format as formato_numero

register = template.Library()


@register.filter
def importe_pyg(valor):
    """Presenta guaraníes enteros; redondeo visual, sin alterar datos financieros."""
    if valor is None:
        return ""
    try:
        monto = Decimal(str(valor))
        if not monto.is_finite():
            return ""
        with localcontext() as ctx:
            ctx.prec = max(28, len(monto.as_tuple().digits) + abs(monto.as_tuple().exponent) + 2)
            entero = monto.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return importe_legible(entero)
    except (InvalidOperation, ValueError):
        return ""


@register.filter
def importe_legible(valor):
    """Agrupa miles con puntos y conserva solo decimales significativos.

    Acepta Decimal y strings del contrato financiero, sin float ni límite por
    operación: los totales agregados pueden superar el máximo transaccional.
    """
    if valor is None:
        return ""
    try:
        monto = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return str(valor)
    if not monto.is_finite():
        return str(valor)
    texto = format(monto, "f") if monto else "0"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return formato_numero(texto, decimal_sep=",", thousand_sep=".",
                          grouping=3, force_grouping=True)
