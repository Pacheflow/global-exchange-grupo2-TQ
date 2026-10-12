import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from threading import Barrier

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
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


class ConcurrenciaMovimientosCajaTests(TransactionTestCase):
    """Verifica exclusión e idempotencia con conexiones PostgreSQL independientes."""

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.caja = Caja.objects.create(
            codigo="CONCURRENTES", nombre="Caja concurrente",
            creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin",
        )
        self.periodo = PeriodoCaja.objects.create(
            caja=self.caja, responsable_keycloak_id="cajero",
        )
        self.moneda, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"},
        )
        SaldoInicialCaja.objects.create(
            periodo=self.periodo, moneda=self.moneda, monto=Decimal("100"),
        )

    def _movimiento(self, *, automatico=False, tipo="INGRESO", monto="40"):
        datos = dict(
            periodo_id=self.periodo.pk, moneda_id=self.moneda.pk,
            tipo=tipo, monto=monto, motivo="Prueba concurrente", usuario_id="cajero",
        )
        if automatico:
            return registrar_movimiento_automatico(
                **datos, clave_idempotencia="evento-concurrente", referencia_externa="QA",
            )
        return registrar_movimiento_manual(**datos, roles=["CAJERO"])

    def _conexion_independiente(self, accion, pids, barrera):
        close_old_connections()
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.put(cursor.fetchone()[0])
            barrera.wait(timeout=5)
            return accion()
        finally:
            connections["default"].close()

    def _esperar_bloqueo(self, pid, *, directo=True):
        """Comprueba espera real, incluida la cola detrás de otra conexión bloqueada."""
        limite = time.monotonic() + 5
        while time.monotonic() < limite:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))"
                    if directo else "SELECT cardinality(pg_blocking_pids(%s)) > 0",
                    [pid],
                )
                if cursor.fetchone()[0]:
                    return
            time.sleep(0.01)
        self.fail("La conexión independiente no llegó a esperar el lock.")

    def _competir(self, accion):
        """Retiene Caja hasta comprobar que ambas solicitudes están bloqueadas."""
        pids, barrera = Queue(), Barrier(3)
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            with transaction.atomic():
                Caja.objects.select_for_update(of=("self",)).get(pk=self.caja.pk)
                futuros = [
                    ejecutor.submit(self._conexion_independiente, accion, pids, barrera)
                    for _ in range(2)
                ]
                barrera.wait(timeout=5)
                for _ in futuros:
                    self._esperar_bloqueo(pids.get(timeout=5), directo=False)
            return [futuro.result(timeout=15) for futuro in futuros]

    def test_dos_egresos_concurrentes_no_dejan_saldo_negativo(self):
        """Dos egresos de 70 sobre 100 compiten: uno confirma y otro se rechaza."""
        def egresar():
            try:
                self._movimiento(tipo="EGRESO", monto="70")
                return "confirmado"
            except ValidationError as error:
                if "insuficiente" not in " ".join(error.messages):
                    raise
                return "saldo_insuficiente"

        self.assertCountEqual(self._competir(egresar), ["confirmado", "saldo_insuficiente"])
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        _, saldos = consultar_saldos_caja(
            periodo_id=self.periodo.pk, usuario_id="cajero", roles=["CAJERO"],
        )
        self.assertEqual(saldos[0].saldo_actual, Decimal("30"))

    def test_automaticos_concurrentes_reutilizan_el_mismo_movimiento(self):
        """La misma clave simultánea produce un alta y una reutilización sin duplicar saldo."""
        resultados = self._competir(lambda: self._movimiento(automatico=True))
        self.assertEqual(resultados[0].movimiento.pk, resultados[1].movimiento.pk)
        self.assertCountEqual([resultado.repetido for resultado in resultados], [False, True])
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        _, saldos = consultar_saldos_caja(
            periodo_id=self.periodo.pk, usuario_id="cajero", roles=["CAJERO"],
        )
        self.assertEqual(saldos[0].saldo_actual, Decimal("140"))

    def test_manual_y_automatico_bloquean_caja_antes_de_periodo(self):
        """Mientras esperan Período, ambos servicios ya retienen el lock de Caja."""
        for automatico in (False, True):
            with self.subTest(automatico=automatico):
                pids, barrera = Queue(), Barrier(2)
                with ThreadPoolExecutor(max_workers=1) as ejecutor:
                    with transaction.atomic():
                        PeriodoCaja.objects.select_for_update(of=("self",)).get(pk=self.periodo.pk)
                        futuro = ejecutor.submit(
                            self._conexion_independiente,
                            lambda: self._movimiento(automatico=automatico), pids, barrera,
                        )
                        barrera.wait(timeout=5)
                        self._esperar_bloqueo(pids.get(timeout=5))
                        # Si Caja se adquiriera después de Período, NOWAIT tendría éxito.
                        with self.assertRaises(OperationalError) as error:
                            with transaction.atomic():
                                Caja.objects.select_for_update(
                                    of=("self",), nowait=True,
                                ).get(pk=self.caja.pk)
                        self.assertEqual(error.exception.__cause__.sqlstate, "55P03")
                    futuro.result(timeout=15)
        self.assertEqual(MovimientoCaja.objects.count(), 2)

