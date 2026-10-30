"""Contrato de solo lectura para el bloque inferior de nueva operación en efectivo."""
import time

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)
from .models import Caja, MovimientoCaja, PeriodoCaja, SaldoInicialCaja
from .services import consultar_movimientos_recientes_caja


class MovimientosRecientesCajaTests(TestCase):
    con_fondos_operacion = False

    def setUp(self):
        self.moneda = Moneda.objects.get_or_create(codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"})[0]
        self.periodo = self.crear_periodo("A")
        self.autenticar()
        self.url = reverse("cajas:movimientos_recientes")

    def autenticar(self, roles=("CAJERO",), usuario="cajero-consulta"):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session[SESSION_ROLES] = list(roles)
        session[SESSION_USUARIO] = {"sub": usuario}
        session.save()

    def crear_periodo(self, codigo, **cambios):
        caja = Caja.objects.create(codigo=codigo, nombre=f"Caja {codigo}", creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin")
        return PeriodoCaja.objects.create(caja=caja, responsable_keycloak_id="otro-responsable", **cambios)

    def movimiento(self, periodo=None, **cambios):
        datos = dict(periodo=periodo or self.periodo, moneda=self.moneda, tipo="INGRESO", monto="123.456789", motivo="Movimiento de prueba", registrado_por_keycloak_id="otro-actor")
        datos.update(cambios)
        return MovimientoCaja.objects.create(**datos)

    def test_cinco_ultimos_por_fecha_y_desempate_id_con_datos_reales(self):
        manuales = [self.movimiento() for _ in range(6)]
        automatico = self.movimiento(tipo="EGRESO", origen="AUTOMATICO", clave_idempotencia="prueba-automatica")
        # El empate de fechas debe conservar el orden determinista por ID descendente.
        MovimientoCaja.objects.all().update(fecha_registro=timezone.now())
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        filas = datos["movimientos"]
        self.assertEqual([f["id"] for f in filas], [automatico.pk] + [m.pk for m in reversed(manuales[-4:])])
        self.assertEqual(filas[0]["importe"], "123.456789")
        self.assertEqual((filas[0]["moneda"], filas[0]["tipo"], filas[0]["origen"]), ("USD", "Egreso", "Automático"))
        self.assertEqual((filas[0]["estado"], filas[0]["metodo"]), ("Registrado", "Efectivo"))
        self.assertIn("T", filas[0]["fecha_registro"])
        self.assertEqual(datos["history_url"], reverse("cajas:historial", args=[self.periodo.caja_id]))
        self.assertEqual(respuesta["Cache-Control"], "no-store")

    def test_aisla_caja_y_periodo_y_no_convierte_saldo_inicial_en_movimiento(self):
        otra = self.crear_periodo("B")
        anterior = PeriodoCaja.objects.create(caja=self.periodo.caja, estado="CERRADO", responsable_keycloak_id="otro")
        propio = self.movimiento()
        self.movimiento(periodo=otra)
        self.movimiento(periodo=anterior)
        SaldoInicialCaja.objects.create(periodo=self.periodo, moneda=self.moneda, monto=1000)
        datos = self.client.get(self.url, {"periodo_id": self.periodo.pk}).json()
        self.assertEqual([m["id"] for m in datos["movimientos"]], [propio.pk])

    def test_fuente_exclusiva_excluye_fondos_pago_y_operacion_online(self):
        from fondos.models import Fondo, MovimientoFondo
        from operaciones import tests as escenarios
        from operaciones.models import Transaccion
        from pagos.models import Pago
        escenarios.BaseOperacionesTests.setUp(self)
        operacion = escenarios.EscenarioLiquidacion.operacion_liquidacion(self)
        operacion.canal = "ONLINE"
        operacion.naturaleza_metodo = "ELECTRONICO"
        operacion.metodo_pago = self.metodo_activo
        operacion.save()
        escenarios.EscenarioLiquidacion.pago_liquidacion(self, operacion)
        fondo = Fondo.objects.create(moneda=self.moneda)
        MovimientoFondo.objects.create(fondo=fondo, tipo="INGRESO", monto=20, operacion=operacion, clave="fondo-no-caja", motivo="Recepción online", responsable="usuario")
        with CaptureQueriesContext(connection) as consultas:
            datos = self.client.get(self.url).json()
        self.assertEqual(datos["movimientos"], [])
        sql = " ".join(c["sql"].lower() for c in consultas)
        for tabla in ("fondos_movimientofondo", "operaciones_transaccion", "pagos_pago"):
            self.assertNotIn(tabla, sql)
        self.assertEqual((Transaccion.objects.count(), Pago.objects.count(), MovimientoFondo.objects.count()), (1, 1, 1))

    def test_unica_auto_varias_exigen_elegir_y_historial_sigue_caja(self):
        self.assertEqual(self.client.get(self.url).json()["periodo_id"], self.periodo.pk)
        otra = self.crear_periodo("B")
        datos = self.client.get(self.url).json()
        self.assertIsNone(datos["periodo_id"])
        self.assertEqual(datos["movimientos"], [])
        self.assertEqual(len(datos["periodos"]), 2)
        self.assertEqual(datos["history_url"], reverse("cajas:historial_selector"))
        self.assertEqual(self.client.get(datos["history_url"]).status_code, 200)
        datos = self.client.get(self.url, {"periodo_id": otra.pk}).json()
        self.assertEqual(datos["history_url"], reverse("cajas:historial", args=[otra.caja_id]))
        self.assertEqual(self.client.get(datos["history_url"]).status_code, 200)
        self.assertNotIn("caja_activa", self.client.session)

    def test_sin_caja_abierta_o_sin_movimientos_muestra_vacio(self):
        self.assertEqual(self.client.get(self.url).json()["movimientos"], [])
        self.periodo.estado = "CERRADO"
        self.periodo.save(update_fields=["estado"])
        datos = self.client.get(self.url).json()
        self.assertEqual(datos["periodos"], [])
        self.assertIsNone(datos["periodo_id"])
        self.assertEqual(datos["history_url"], reverse("cajas:historial_selector"))

    def test_seleccion_invalida_cerrada_deshabilitada_no_hace_fallback(self):
        cerrada = self.crear_periodo("C", estado="CERRADO")
        deshabilitada = self.crear_periodo("D")
        Caja.objects.filter(pk=deshabilitada.caja_id).update(estado="DESHABILITADA")
        for seleccion in ("", "abc", "0", "-1", "1.0", "9" * 30, "9999999999", str(cerrada.pk), str(deshabilitada.pk)):
            with self.subTest(seleccion=seleccion):
                respuesta = self.client.get(self.url, {"periodo_id": seleccion})
                self.assertEqual(respuesta.status_code, 400)
                self.assertIsNone(respuesta.json()["periodo_id"])
                self.assertEqual(respuesta.json()["movimientos"], [])
                self.assertEqual([p["id"] for p in respuesta.json()["periodos"]], [self.periodo.pk])

    def test_roles_identidad_sesion_y_metodo_http_no_filtran_datos(self):
        for roles in (("USUARIO",), ("ADMINISTRADOR",), ("ANALISTA_CAMBIARIO",), ("ADMINISTRADOR", "CAJERO")):
            self.autenticar(roles=roles)
            respuesta = self.client.get(self.url)
            self.assertEqual(respuesta.status_code, 403)
            self.assertNotIn("periodos", respuesta.json())
        self.autenticar(usuario="")
        respuesta = self.client.get(self.url)
        self.assertIn(respuesta.status_code, (400, 401))
        self.assertNotIn("periodos", respuesta.json())
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            consultar_movimientos_recientes_caja(usuario_id="", roles=["CAJERO"])
        with self.assertNumQueries(0), self.assertRaises(PermissionDenied):
            consultar_movimientos_recientes_caja(usuario_id="usuario", roles=["USUARIO"])
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.autenticar()
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_actualizar_cerrada_limpia_datos_sin_escrituras_y_permite_otra_seleccion(self):
        self.movimiento()
        otra = self.crear_periodo("B")
        self.assertEqual(len(self.client.get(self.url, {"periodo_id": self.periodo.pk}).json()["movimientos"]), 1)
        self.periodo.estado = "CERRADO"
        self.periodo.save(update_fields=["estado"])
        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get(self.url, {"periodo_id": self.periodo.pk})
        self.assertEqual(respuesta.status_code, 400)
        datos = respuesta.json()
        self.assertIsNone(datos["periodo_id"])
        self.assertEqual(datos["movimientos"], [])
        self.assertEqual([p["id"] for p in datos["periodos"]], [otra.pk])
        for consulta in consultas:
            self.assertFalse(consulta["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")), consulta["sql"])
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        self.assertEqual(self.client.get(self.url, {"periodo_id": otra.pk}).status_code, 200)

    def test_bloque_solo_presencial_con_formulario_y_sin_acciones_por_fila(self):
        pagina = self.client.get(reverse("operaciones_web:presencial"))
        self.assertContains(pagina, "Últimas operaciones de caja")
        self.assertContains(pagina, "Movimientos recientes registrados en la caja.")
        self.assertContains(pagina, "data-operation-form")
        self.assertContains(pagina, "data-cash-recent-url")
        self.assertNotContains(pagina, "Operaciones pendientes")
        self.assertNotContains(pagina, "<th>Acción</th>")
        bandeja = self.client.get(reverse("operaciones_web:inicio"))
        self.assertContains(bandeja, "Operaciones pendientes")
        self.assertNotContains(bandeja, "data-cash-recent-url")
