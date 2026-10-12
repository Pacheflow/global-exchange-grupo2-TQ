from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from monedas.models import Moneda

from .models import (
    ArqueoCaja,
    Caja,
    CierreCaja,
    DetalleCierreCaja,
    PeriodoCaja,
    SaldoInicialCaja,
)
from .services import (
    cerrar_caja,
    realizar_arqueo,
    registrar_movimiento_manual,
)


class CierreCajaTests(TestCase):
    """Pruebas de HU-43 para el cierre de un período de caja."""

    def setUp(self):
        """Prepara una caja abierta con USD y un cajero válido."""
        self.caja = Caja.objects.create(
            codigo="CIERRE",
            nombre="Caja para cierre",
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

        SaldoInicialCaja.objects.create(
            periodo=self.periodo,
            moneda=self.usd,
            monto=Decimal("100.000000"),
        )

        self.identidad = {
            "usuario_id": "cajero-id",
            "username": "elias",
            "roles": ["CAJERO"],
        }

    def crear_arqueo(self, monto="100", observacion=""):
        """Registra un arqueo válido antes del cierre."""
        return realizar_arqueo(
            periodo_id=self.periodo.id,
            saldos_fisicos=[
                {
                    "moneda_id": self.usd.id,
                    "monto": monto,
                }
            ],
            observacion=observacion,
            **self.identidad,
        )

    def test_cierre_con_arqueo_guarda_resultados_y_cierra_periodo(self):
        """Un período arqueado debe cerrarse conservando sus valores finales."""
        arqueo = self.crear_arqueo(
            monto="105",
            observacion="Sobrante encontrado.",
        )

        cierre = cerrar_caja(
            periodo_id=self.periodo.id,
            **self.identidad,
        )

        self.periodo.refresh_from_db()
        detalle = cierre.detalles.get(moneda=self.usd)

        self.assertEqual(self.periodo.estado, "CERRADO")
        self.assertEqual(cierre.arqueo, arqueo)
        self.assertEqual(cierre.cerrado_por_keycloak_id, "cajero-id")
        self.assertEqual(cierre.cerrado_por_username, "elias")
        self.assertIsNotNone(cierre.fecha_cierre)

        self.assertEqual(detalle.saldo_teorico, Decimal("100"))
        self.assertEqual(detalle.saldo_fisico, Decimal("105"))
        self.assertEqual(detalle.diferencia, Decimal("5"))

        self.assertEqual(CierreCaja.objects.count(), 1)
        self.assertEqual(DetalleCierreCaja.objects.count(), 1)

    def test_no_se_puede_cerrar_sin_arqueo(self):
        """Un período abierto sin arqueo previo no puede cerrarse."""
        with self.assertRaisesMessage(ValidationError, "arqueo"):
            cerrar_caja(
                periodo_id=self.periodo.id,
                **self.identidad,
            )

        self.periodo.refresh_from_db()

        self.assertEqual(self.periodo.estado, "ABIERTO")
        self.assertFalse(CierreCaja.objects.exists())

    def test_cierre_bloquea_nuevos_movimientos(self):
        """Después del cierre no se permiten movimientos en ese período."""
        self.crear_arqueo()

        cerrar_caja(
            periodo_id=self.periodo.id,
            **self.identidad,
        )

        with self.assertRaisesMessage(ValidationError, "abierto"):
            registrar_movimiento_manual(
                periodo_id=self.periodo.id,
                tipo="INGRESO",
                moneda_id=self.usd.id,
                monto="10",
                motivo="Movimiento posterior al cierre",
                **self.identidad,
            )

    def test_periodo_cerrado_no_se_puede_cerrar_de_nuevo(self):
        """Un período ya cerrado no admite un segundo cierre."""
        self.crear_arqueo()

        cerrar_caja(
            periodo_id=self.periodo.id,
            **self.identidad,
        )

        with self.assertRaises(ValidationError):
            cerrar_caja(
                periodo_id=self.periodo.id,
                **self.identidad,
            )

        self.assertEqual(CierreCaja.objects.count(), 1)

    def test_cierre_exige_rol_cajero(self):
        """Un usuario con otro rol no puede cerrar la caja."""
        self.crear_arqueo()

        with self.assertRaises(PermissionDenied):
            cerrar_caja(
                periodo_id=self.periodo.id,
                usuario_id="admin-id",
                username="admin",
                roles=["ADMINISTRADOR"],
            )

        self.periodo.refresh_from_db()

        self.assertEqual(self.periodo.estado, "ABIERTO")
        self.assertFalse(CierreCaja.objects.exists())
    def test_movimiento_despues_del_arqueo_exige_nuevo_arqueo(self):
        """Un movimiento posterior invalida el arqueo usado para cerrar."""
        self.crear_arqueo()

        registrar_movimiento_manual(
            periodo_id=self.periodo.id,
            tipo="INGRESO",
            moneda_id=self.usd.id,
            monto="10",
            motivo="Ingreso posterior al arqueo",
            **self.identidad,
        )

        with self.assertRaisesMessage(ValidationError, "nuevo arqueo"):
            cerrar_caja(
                periodo_id=self.periodo.id,
                **self.identidad,
            )

        self.periodo.refresh_from_db()

        self.assertEqual(self.periodo.estado, "ABIERTO")
        self.assertFalse(CierreCaja.objects.exists())