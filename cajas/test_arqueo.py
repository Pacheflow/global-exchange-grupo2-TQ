from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from monedas.models import Moneda

from .models import (
    ArqueoCaja,
    Caja,
    DetalleArqueoCaja,
    PeriodoCaja,
    SaldoInicialCaja,
)
from .services import realizar_arqueo, registrar_movimiento_manual


class ArqueoCajaTests(TestCase):
    """Pruebas de HU-42 para el arqueo de una caja abierta."""

    def setUp(self):
        """Prepara una caja abierta con saldos iniciales en USD y PYG."""
        self.caja = Caja.objects.create(
            codigo="ARQUEO",
            nombre="Caja para arqueo",
            creado_por_keycloak_id="admin",
            actualizado_por_keycloak_id="admin",
        )

        self.periodo = PeriodoCaja.objects.create(
            caja=self.caja,
            responsable_keycloak_id="cajero-id",
            responsable_username="elias",
        )

        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar", "simbolo": "$"},
        )

        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní", "simbolo": "Gs"},
        )

        SaldoInicialCaja.objects.create(
            periodo=self.periodo,
            moneda=self.usd,
            monto=Decimal("100.000000"),
        )

        SaldoInicialCaja.objects.create(
            periodo=self.periodo,
            moneda=self.pyg,
            monto=Decimal("500000.000000"),
        )

        self.identidad = {
            "usuario_id": "cajero-id",
            "username": "elias",
            "roles": ["CAJERO"],
        }

    def arquear(self, saldos_fisicos, **cambios):
        """Ejecuta un arqueo válido usando la identidad del cajero."""
        datos = {
            "periodo_id": self.periodo.id,
            "saldos_fisicos": saldos_fisicos,
            "observacion": "",
            **self.identidad,
            **cambios,
        }
        return realizar_arqueo(**datos)

    def test_arqueo_calcula_diferencias_y_guarda_resultado(self):
        """Comprueba sobrante, faltante, usuario y persistencia del arqueo."""
        arqueo = self.arquear(
            [
                {"moneda_id": self.usd.id, "monto": "105"},
                {"moneda_id": self.pyg.id, "monto": "499000"},
            ],
            observacion="Diferencia encontrada en caja.",
        )

        detalles = {
            detalle.moneda.codigo: detalle
            for detalle in arqueo.detalles.select_related("moneda")
        }

        self.assertEqual(detalles["USD"].saldo_teorico, Decimal("100"))
        self.assertEqual(detalles["USD"].diferencia, Decimal("5"))
        self.assertEqual(detalles["USD"].resultado, "SOBRANTE")

        self.assertEqual(detalles["PYG"].saldo_teorico, Decimal("500000"))
        self.assertEqual(detalles["PYG"].diferencia, Decimal("-1000"))
        self.assertEqual(detalles["PYG"].resultado, "FALTANTE")

        self.assertEqual(arqueo.realizado_por_keycloak_id, "cajero-id")
        self.assertEqual(arqueo.realizado_por_username, "elias")
        self.assertEqual(
            arqueo.observacion,
            "Diferencia encontrada en caja.",
        )
        self.assertIsNotNone(arqueo.fecha_arqueo)
        self.assertEqual(ArqueoCaja.objects.count(), 1)
        self.assertEqual(DetalleArqueoCaja.objects.count(), 2)

    def test_arqueo_sin_diferencia(self):
        """Comprueba que valores físicos iguales al teórico no tengan diferencia."""
        arqueo = self.arquear(
            [
                {"moneda_id": self.usd.id, "monto": "100"},
                {"moneda_id": self.pyg.id, "monto": "500000"},
            ]
        )

        for detalle in arqueo.detalles.all():
            self.assertEqual(detalle.diferencia, Decimal("0"))
            self.assertEqual(detalle.resultado, "SIN_DIFERENCIA")

    def test_arqueo_utiliza_saldo_teorico_con_movimientos(self):
        """Comprueba que el arqueo use el saldo actualizado por movimientos."""
        registrar_movimiento_manual(
            periodo_id=self.periodo.id,
            tipo="INGRESO",
            moneda_id=self.usd.id,
            monto="25",
            motivo="Ingreso previo al arqueo",
            **self.identidad,
        )

        arqueo = self.arquear(
            [
                {"moneda_id": self.usd.id, "monto": "125"},
                {"moneda_id": self.pyg.id, "monto": "500000"},
            ]
        )

        detalle_usd = arqueo.detalles.get(moneda=self.usd)

        self.assertEqual(detalle_usd.saldo_teorico, Decimal("125"))
        self.assertEqual(detalle_usd.diferencia, Decimal("0"))

    def test_saldo_fisico_negativo_no_crea_arqueo(self):
        """Un saldo físico negativo debe rechazarse sin guardar datos parciales."""
        with self.assertRaises(ValidationError):
            self.arquear(
                [
                    {"moneda_id": self.usd.id, "monto": "-1"},
                    {"moneda_id": self.pyg.id, "monto": "500000"},
                ]
            )

        self.assertFalse(ArqueoCaja.objects.exists())
        self.assertFalse(DetalleArqueoCaja.objects.exists())

    def test_periodo_cerrado_no_permite_arqueo(self):
        """Una caja cerrada no puede recibir un nuevo arqueo."""
        self.periodo.estado = "CERRADO"
        self.periodo.save(update_fields=["estado"])

        with self.assertRaisesMessage(ValidationError, "abierto"):
            self.arquear(
                [
                    {"moneda_id": self.usd.id, "monto": "100"},
                    {"moneda_id": self.pyg.id, "monto": "500000"},
                ]
            )

        self.assertFalse(ArqueoCaja.objects.exists())

    def test_arqueo_exige_rol_cajero(self):
        """Un usuario con otro rol no puede realizar el arqueo."""
        with self.assertRaises(PermissionDenied):
            self.arquear(
                [
                    {"moneda_id": self.usd.id, "monto": "100"},
                    {"moneda_id": self.pyg.id, "monto": "500000"},
                ],
                roles=["ADMINISTRADOR"],
            )

        self.assertFalse(ArqueoCaja.objects.exists())