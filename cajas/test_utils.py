"""Fixtures de fondos explícitos para escenarios de operaciones y pagos offline."""
from decimal import Decimal
from uuid import uuid4

from .models import Caja, PeriodoCaja, SaldoInicialCaja


def crear_fondos_prueba(monedas, monto=Decimal("999999999999")):
    """Crea una caja abierta únicamente en la BD de tests, sin servicios externos."""
    caja = Caja.objects.create(codigo=f"TEST-{uuid4().hex[:16]}", nombre="Fondos de prueba",
                               creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin")
    periodo = PeriodoCaja.objects.create(caja=caja, responsable_keycloak_id="cajero")
    for moneda in monedas:
        SaldoInicialCaja.objects.create(periodo=periodo, moneda=moneda, monto=monto)
    return periodo
