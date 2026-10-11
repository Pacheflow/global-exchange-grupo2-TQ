"""Construcción del único proveedor autorizado, exclusivamente Stripe TEST."""

from .providers import PaymentProvider
from .stripe_provider import EscenarioStripeTest, StripePaymentProvider


def obtener_payment_provider() -> PaymentProvider:
    # El escenario y la configuración son decisiones del servidor.
    return StripePaymentProvider(escenario_test=EscenarioStripeTest.APROBACION)
