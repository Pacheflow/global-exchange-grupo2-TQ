from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def importe_inicial(valor):
    """Presenta el decimal completo con separadores es-PY, sin conversión a float.

    Mantiene la política monetaria de Operaciones (hasta seis decimales) y
    evita perder precisión al representar importes cercanos al máximo.
    """
    try:
        monto = Decimal(str(valor))
        if not monto.is_finite() or monto.as_tuple().exponent < -6 or abs(monto) >= Decimal("1000000000000"):
            return str(valor)
    except (InvalidOperation, ValueError):
        return str(valor)
    entero, _, decimales = format(monto, "f").partition(".")
    entero = format(int(entero), ",").replace(",", ".")
    decimales = decimales.rstrip("0")
    return entero + ("," + decimales if decimales else "")
