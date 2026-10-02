from decimal import Decimal, ROUND_HALF_UP


PRECISION_TASA_FRACCIONARIA = Decimal("0.0000000001")
PRECISION_TASA_ENTERA = Decimal("1")


def normalizar_tasa(valor):
    """Aplica la regla de presentación y cálculo compartida para tasas.

    Las tasas cuyo valor absoluto es al menos uno se redondean al entero más
    cercano. Las tasas menores que uno conservan hasta diez decimales para no
    perder cotizaciones significativas, como las de PYG a USD.
    """

    tasa = Decimal(str(valor))
    precision = (
        PRECISION_TASA_ENTERA
        if abs(tasa) >= PRECISION_TASA_ENTERA
        else PRECISION_TASA_FRACCIONARIA
    )
    return tasa.quantize(precision, rounding=ROUND_HALF_UP)
