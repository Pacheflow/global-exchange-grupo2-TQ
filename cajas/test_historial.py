from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from monedas.models import Moneda

from .models import Caja, PeriodoCaja, SaldoInicialCaja
from .services import (
    cerrar_caja,
    consultar_historial_caja,
    realizar_arqueo,
    registrar_movimiento_manual,
)


class HistorialCajaTests(TestCase):
    """Pruebas de HU-44 para la consulta del historial de caja."""

    def setUp(self):
        """Prepara una caja con un período y saldo inicial."""
        self.caja = Caja.objects.create(
            codigo="HISTORIAL",
            nombre="Caja historial",
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

    def test_historial_muestra_periodo_movimientos_arqueo_y_cierre(self):
        """El historial conserva los registros completos de un período cerrado."""
        registrar_movimiento_manual(
            periodo_id=self.periodo.id,
            tipo="INGRESO",
            moneda_id=self.usd.id,
            monto="10",
            motivo="Ingreso de prueba",
            **self.identidad,
        )

        realizar_arqueo(
            periodo_id=self.periodo.id,
            saldos_fisicos=[
                {
                    "moneda_id": self.usd.id,
                    "monto": "115",
                }
            ],
            observacion="Sobrante encontrado.",
            **self.identidad,
        )

        cerrar_caja(
            periodo_id=self.periodo.id,
            **self.identidad,
        )

        caja, periodos = consultar_historial_caja(
            caja_id=self.caja.id,
            usuario_id="admin-id",
            roles=["ADMINISTRADOR"],
        )

        periodo = periodos[0]
        arqueo = periodo.arqueos.first()

        self.assertEqual(caja, self.caja)
        self.assertEqual(periodo.estado, "CERRADO")
        self.assertEqual(periodo.movimientos.count(), 1)
        self.assertEqual(periodo.arqueos.count(), 1)
        self.assertEqual(arqueo.detalles.first().diferencia, Decimal("5"))
        self.assertEqual(periodo.cierre.detalles.count(), 1)

    def test_nuevo_periodo_no_modifica_historial_anterior(self):
        """Una nueva apertura debe conservar intacto el período histórico."""
        realizar_arqueo(
            periodo_id=self.periodo.id,
            saldos_fisicos=[
                {
                    "moneda_id": self.usd.id,
                    "monto": "100",
                }
            ],
            **self.identidad,
        )

        cerrar_caja(
            periodo_id=self.periodo.id,
            **self.identidad,
        )

        periodo_anterior_id = self.periodo.id

        nuevo_periodo = PeriodoCaja.objects.create(
            caja=self.caja,
            responsable_keycloak_id="otro-cajero",
            responsable_username="otro",
        )

        SaldoInicialCaja.objects.create(
            periodo=nuevo_periodo,
            moneda=self.usd,
            monto=Decimal("200.000000"),
        )

        _, periodos = consultar_historial_caja(
            caja_id=self.caja.id,
            usuario_id="admin-id",
            roles=["ADMINISTRADOR"],
        )

        ids = {periodo.id for periodo in periodos}

        self.assertIn(periodo_anterior_id, ids)
        self.assertIn(nuevo_periodo.id, ids)

        anterior = PeriodoCaja.objects.get(pk=periodo_anterior_id)
        self.assertEqual(anterior.estado, "CERRADO")
        self.assertEqual(
            anterior.saldos_iniciales.get(moneda=self.usd).monto,
            Decimal("100"),
        )

    def test_caja_sin_periodos_devuelve_historial_vacio(self):
        """Una caja sin registros debe devolver una lista vacía."""
        vacia = Caja.objects.create(
            codigo="VACIA",
            nombre="Caja sin historial",
            creado_por_keycloak_id="admin",
            actualizado_por_keycloak_id="admin",
        )

        _, periodos = consultar_historial_caja(
            caja_id=vacia.id,
            usuario_id="admin-id",
            roles=["ADMINISTRADOR"],
        )

        self.assertEqual(periodos, [])

    def test_historial_permite_cajero_y_administrador(self):
        """CAJERO y ADMINISTRADOR pueden consultar el historial."""
        _, periodos_cajero = consultar_historial_caja(
            caja_id=self.caja.id,
            usuario_id="cajero-id",
            roles=["CAJERO"],
        )

        _, periodos_admin = consultar_historial_caja(
            caja_id=self.caja.id,
            usuario_id="admin-id",
            roles=["ADMINISTRADOR"],
        )

        self.assertEqual(len(periodos_cajero), 1)
        self.assertEqual(len(periodos_admin), 1)

    def test_historial_rechaza_rol_no_autorizado(self):
        """Un rol distinto de CAJERO o ADMINISTRADOR no consulta historial."""
        with self.assertRaises(PermissionDenied):
            consultar_historial_caja(
                caja_id=self.caja.id,
                usuario_id="usuario-id",
                roles=["USUARIO"],
            )