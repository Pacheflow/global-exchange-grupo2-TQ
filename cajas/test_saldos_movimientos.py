import time
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from monedas.models import Moneda
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import Caja, MovimientoCaja, PeriodoCaja, SaldoInicialCaja
from .services import (
    consultar_saldos_caja,
    registrar_movimiento_automatico,
    registrar_movimiento_manual,
)


class SaldosMovimientosCajaTests(TestCase):
    """Prueba HU-40 y HU-41 con importes exactos y trazabilidad Keycloak."""

    def setUp(self):
        self.caja = Caja.objects.create(
            codigo="OPERATIVA",
            nombre="Caja operativa",
            creado_por_keycloak_id="admin",
            actualizado_por_keycloak_id="admin",
        )
        self.periodo = PeriodoCaja.objects.create(
            caja=self.caja,
            responsable_keycloak_id="cajero-id",
            responsable_username="guillermo",
        )
        self.usd, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"}
        )
        self.pyg, _ = Moneda.objects.get_or_create(
            codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"}
        )
        SaldoInicialCaja.objects.create(
            periodo=self.periodo, moneda=self.usd, monto=Decimal("100.000000")
        )
        SaldoInicialCaja.objects.create(
            periodo=self.periodo, moneda=self.pyg, monto=Decimal("500000.000000")
        )
        self.identidad = {
            "usuario_id": "cajero-id",
            "username": "guillermo",
            "roles": ["CAJERO"],
        }

    def autenticar(self, rol="CAJERO"):
        """Crea una sesión web verificada con el rol efectivo indicado."""
        sesion = self.client.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = time.time() + 3600
        sesion[SESSION_ROLES] = [rol]
        sesion[SESSION_USUARIO] = {
            "sub": "cajero-id" if rol == "CAJERO" else "admin-id",
            "preferred_username": "guillermo",
        }
        sesion.save()

    def manual(self, **cambios):
        """Registra un movimiento manual con valores válidos por defecto."""
        datos = {
            "periodo_id": self.periodo.id,
            "tipo": "INGRESO",
            "moneda_id": self.usd.id,
            "monto": "25.123456",
            "motivo": "Refuerzo de efectivo",
            **self.identidad,
            **cambios,
        }
        return registrar_movimiento_manual(**datos)

    def test_sin_movimientos_devuelve_saldo_inicial_por_moneda(self):
        """El saldo inicial se devuelve intacto y las monedas nunca se mezclan."""
        _, saldos = consultar_saldos_caja(
            periodo_id=self.periodo.id,
            usuario_id="admin-id",
            roles=["ADMINISTRADOR"],
        )
        actuales = {saldo.moneda.codigo: saldo.saldo_actual for saldo in saldos}
        self.assertEqual(actuales, {"PYG": Decimal("500000"), "USD": Decimal("100")})

    def test_ingreso_y_egreso_modifican_solo_su_moneda(self):
        """Ingreso suma, egreso resta y PYG queda independiente de USD."""
        self.manual()
        self.manual(tipo="EGRESO", monto="20", motivo="Retiro autorizado")
        _, saldos = consultar_saldos_caja(
            periodo_id=self.periodo.id, usuario_id="cajero-id", roles=["CAJERO"]
        )
        actuales = {saldo.moneda.codigo: saldo.saldo_actual for saldo in saldos}
        self.assertEqual(actuales["USD"], Decimal("105.123456"))
        self.assertEqual(actuales["PYG"], Decimal("500000"))

    def test_egreso_sin_fondos_no_escribe(self):
        """Un egreso mayor al saldo se rechaza dentro de la transacción."""
        with self.assertRaisesMessage(ValidationError, "insuficiente"):
            self.manual(tipo="EGRESO", monto="100.000001", motivo="Exceso")
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_periodo_cerrado_no_permite_consulta_ni_movimiento(self):
        """Los cálculos y movimientos nunca reutilizan un período cerrado."""
        self.periodo.estado = "CERRADO"
        self.periodo.save(update_fields=["estado"])
        with self.assertRaisesMessage(ValidationError, "abierto"):
            consultar_saldos_caja(
                periodo_id=self.periodo.id, usuario_id="cajero-id", roles=["CAJERO"]
            )
        with self.assertRaisesMessage(ValidationError, "abierto"):
            self.manual()

    def test_movimiento_manual_exige_rol_cajero_y_motivo(self):
        """Administrador no opera y un cajero no puede omitir el motivo."""
        with self.assertRaises(PermissionDenied):
            self.manual(roles=["ADMINISTRADOR"])
        with self.assertRaisesMessage(ValidationError, "motivo"):
            self.manual(motivo="   ")
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_movimiento_conserva_actor_y_es_inmutable(self):
        """El alta registra al actor de sesión y no admite edición ni borrado."""
        movimiento = self.manual()
        self.assertEqual(movimiento.registrado_por_keycloak_id, "cajero-id")
        self.assertEqual(movimiento.registrado_por_username, "guillermo")
        movimiento.motivo = "Alterado"
        with self.assertRaisesMessage(ValueError, "inmutables"):
            movimiento.save()
        with self.assertRaisesMessage(ValueError, "no se pueden eliminar"):
            movimiento.delete()

    def test_movimiento_automatico_es_idempotente(self):
        """Reintentar la misma operación devuelve el alta original sin duplicarla."""
        datos = {
            "periodo_id": self.periodo.id,
            "tipo": "INGRESO",
            "moneda_id": self.usd.id,
            "monto": "40",
            "motivo": "Operación completada",
            "clave_idempotencia": "operacion-77-ingreso-usd",
            "referencia_externa": "OP-77",
            "usuario_id": "servicio-operaciones",
            "username": "sistema",
        }
        primero = registrar_movimiento_automatico(**datos)
        segundo = registrar_movimiento_automatico(**datos)
        self.assertFalse(primero.repetido)
        self.assertTrue(segundo.repetido)
        self.assertEqual(primero.movimiento.id, segundo.movimiento.id)
        self.assertEqual(MovimientoCaja.objects.count(), 1)

    def test_idempotencia_rechaza_reutilizacion_con_otro_payload(self):
        """Una clave ya usada no puede encubrir un monto automático diferente."""
        datos = {
            "periodo_id": self.periodo.id,
            "tipo": "INGRESO",
            "moneda_id": self.usd.id,
            "monto": "40",
            "motivo": "Operación completada",
            "clave_idempotencia": "operacion-88",
            "referencia_externa": "OP-88",
            "usuario_id": "servicio-operaciones",
        }
        registrar_movimiento_automatico(**datos)
        with self.assertRaisesMessage(ValidationError, "otros datos"):
            registrar_movimiento_automatico(**{**datos, "monto": "41"})
        self.assertEqual(MovimientoCaja.objects.count(), 1)

    def test_flujo_web_cajero_registra_y_muestra_saldo(self):
        """El formulario crea el movimiento y redirige a la consulta actualizada."""
        self.autenticar()
        respuesta = self.client.post(
            reverse("cajas:registrar_movimiento", args=[self.periodo.id]),
            {"tipo": "EGRESO", "moneda": self.usd.id, "monto": "10", "motivo": "Cambio"},
        )
        self.assertRedirects(respuesta, reverse("cajas:saldo", args=[self.periodo.id]))
        detalle = self.client.get(reverse("cajas:saldo", args=[self.periodo.id]))
        self.assertContains(detalle, "90")
        self.assertContains(detalle, "Cambio")

    def test_administrador_consulta_pero_no_registra(self):
        """El administrador ve saldos y recibe 403 al intentar operar manualmente."""
        self.autenticar("ADMINISTRADOR")
        consulta = self.client.get(reverse("cajas:saldo", args=[self.periodo.id]))
        self.assertEqual(consulta.status_code, 200)
        registro = self.client.get(
            reverse("cajas:registrar_movimiento", args=[self.periodo.id])
        )
        self.assertEqual(registro.status_code, 403)

