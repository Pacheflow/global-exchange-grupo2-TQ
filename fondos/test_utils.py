"""Financiación electrónica exclusivamente para bases aisladas de pruebas."""
from decimal import Decimal
from uuid import uuid4
from .services import cargar


def crear_fondos_prueba(monedas, monto=Decimal("999999999999")):
    """Carga cada moneda con actor explícito sin utilizar Caja ni proveedores."""
    for moneda in monedas:
        cargar(moneda_id=moneda.pk, monto=monto, motivo="Financiación de prueba",
               clave=uuid4(), usuario_id="admin-test", roles=["ADMINISTRADOR"])
