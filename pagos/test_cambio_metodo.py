"""Cambio de método sin cobros, evidencia histórica e idempotencia concurrente."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from clientes.models import UsuarioCliente
from fondos.models import ReservaFondo
from fondos.services import reservar
from metodos_pago.models import MetodoPago
from operaciones.models import CambioMetodoPago, Transaccion

from .models import Pago
from .providers import CodigoResultado, EstadoPago, ResultadoPago
from .services import (
    _invocar, _reserva, cambiar_metodo_pago, consultar_estado_pago, iniciar_pago,
)
from .test_views import _EscenarioHTTP


class CambioMetodoPagoTests(_EscenarioHTTP, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.nuevo = MetodoPago.objects.create(nombre="Otra tarjeta", naturaleza="ELECTRONICO")

    def argumentos(self, pago=None, **cambios):
        datos = dict(
            transaccion_id=self.transaccion.pk, usuario_id="http-usuario", roles=["USUARIO"],
            cliente_seleccionado_id=self.cliente_pago.pk, metodo_pago_id=self.nuevo.pk,
            metodo_anterior_id=self.metodo.pk, pago_esperado_id=pago.pk if pago else None,
            clave_idempotencia=uuid.uuid4(),
        )
        datos.update(cambios)
        return datos

    def cuerpo(self, pago=None, **cambios):
        datos = self.argumentos(pago)
        datos = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in datos.items()
                 if k in {"metodo_pago_id", "metodo_anterior_id", "pago_esperado_id", "clave_idempotencia"}}
        datos.update(cambios)
        return datos

    def cambiar_http(self, datos):
        return self.client.post(self.url("cambiar_metodo"), data=json.dumps(datos), content_type="application/json")

    def test_sin_pago_cambia_eleccion_sin_cobro_y_preserva_creacion(self):
        self.transaccion.huella_idempotencia = "a" * 64
        self.transaccion.save(update_fields=["huella_idempotencia"])
        antes = Transaccion.objects.values().get(pk=self.transaccion.pk)
        resultado = cambiar_metodo_pago(**self.argumentos())
        despues = Transaccion.objects.values().get(pk=self.transaccion.pk)
        for campo in antes:
            if campo not in {"metodo_pago_id", "metodo_pago_nombre", "fecha_actualizacion"}:
                self.assertEqual(despues[campo], antes[campo], campo)
        self.assertIsNone(resultado["pago_id"])
        self.assertEqual(despues["metodo_pago_id"], self.nuevo.pk)
        self.assertFalse(Pago.objects.exists())
        self.factory_mock.assert_not_called()
        self.provider.iniciar.assert_not_called()

    def test_rechazado_archiva_sin_alterar_snapshots_y_nuevo_uuid(self):
        viejo = self.crear_pago(self.transaccion, Pago.Estado.RECHAZADO, referencia="pi_rechazado")
        antes = Pago.objects.values().get(pk=viejo.pk)
        with transaction.atomic():
            reservar(self.transaccion)
        cambiar_metodo_pago(**self.argumentos(viejo))
        despues = Pago.objects.values().get(pk=viejo.pk)
        self.assertEqual(despues, {**antes, "vigente": False})
        self.assertEqual(ReservaFondo.objects.get(operacion=self.transaccion).estado, "LIBERADA")
        self.assertIsNone(Transaccion.objects.get(pk=self.transaccion.pk).pago)
        cambio = CambioMetodoPago.objects.get()
        self.assertEqual((cambio.anterior_id, cambio.nuevo_id), (self.metodo.pk, self.nuevo.pk))
        self.assertEqual(cambio.nombre_anterior, self.metodo.nombre)
        nuevo = iniciar_pago(transaccion_id=self.transaccion.pk, usuario_id="http-usuario", roles=["USUARIO"],
                             cliente_seleccionado_id=self.cliente_pago.pk, provider=self.provider)
        repetido = iniciar_pago(transaccion_id=self.transaccion.pk, usuario_id="http-usuario", roles=["USUARIO"],
                                cliente_seleccionado_id=self.cliente_pago.pk, provider=self.provider)
        self.assertNotEqual(nuevo.pago_id, viejo.pk)
        self.assertEqual(nuevo.pago_id, repetido.pago_id)
        self.assertEqual(Pago.objects.filter(transaccion=self.transaccion).count(), 2)
        self.assertEqual(Pago.objects.filter(transaccion=self.transaccion, vigente=True).count(), 1)
        self.provider.iniciar.assert_called_once()
        self.assertEqual(Transaccion.objects.get(pk=self.transaccion.pk).estado, "COMPLETADA")

    def test_error_certificado_permite_cambiar(self):
        pago = self.crear_pago(self.transaccion, Pago.Estado.ERROR)
        self.assertEqual(pago.trazabilidad[-1]["codigo"], "ERROR_SIN_EJECUCION")
        cambiar_metodo_pago(**self.argumentos(pago))
        pago.refresh_from_db()
        self.assertFalse(pago.vigente)
        self.provider.iniciar.assert_not_called()

    def test_error_sin_certificacion_o_con_referencia_no_permite_cambiar(self):
        for traza, referencia in (([], None), ([dict(fecha=timezone.now().isoformat(), estado="ERROR", codigo="CONSULTADO")], None),
                                  ([dict(fecha=timezone.now().isoformat(), estado="ERROR", codigo="ERROR_SIN_EJECUCION")], "pi_dudoso")):
            tx = self.crear_transaccion()
            pago = self.crear_pago(tx, Pago.Estado.ERROR, referencia=referencia)
            pago.trazabilidad = traza
            pago.save()
            with self.subTest(traza=traza, referencia=referencia), self.assertRaises(ValidationError) as error:
                cambiar_metodo_pago(**self.argumentos(pago, transaccion_id=tx.pk))
            self.assertEqual(error.exception.code, "CAMBIO_METODO_NO_PERMITIDO")
            pago.refresh_from_db()
            self.assertTrue(pago.vigente)
        self.assertFalse(CambioMetodoPago.objects.exists())
        self.provider.iniciar.assert_not_called()

    def test_estados_con_posible_ejecucion_no_permiten_cambiar(self):
        for estado in (Pago.Estado.EN_PROCESO, Pago.Estado.INDETERMINADO, Pago.Estado.APROBADO):
            tx = self.crear_transaccion()
            pago = self.crear_pago(tx, estado, referencia="pi_" + uuid.uuid4().hex if estado == Pago.Estado.APROBADO else None)
            antes = Pago.objects.values().get(pk=pago.pk)
            with self.subTest(estado=estado), self.assertRaises(ValidationError) as error:
                cambiar_metodo_pago(**self.argumentos(pago, transaccion_id=tx.pk))
            self.assertEqual(error.exception.code, "CAMBIO_METODO_NO_PERMITIDO")
            self.assertEqual(Pago.objects.values().get(pk=pago.pk), antes)
        self.assertFalse(CambioMetodoPago.objects.exists())
        self.provider.iniciar.assert_not_called()

    def test_venta_presencial_historica_y_no_pendiente_bloqueadas(self):
        for cambios in ({"tipo": "VENTA"}, {"version_flujo": 0, "canal": "", "naturaleza_metodo": ""},
                        {"canal": "PRESENCIAL", "naturaleza_metodo": "EFECTIVO"}, {"estado": "COMPLETADA"}):
            tx = self.crear_transaccion(**cambios)
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                cambiar_metodo_pago(**self.argumentos(transaccion_id=tx.pk))
        self.assertFalse(CambioMetodoPago.objects.exists())

    def test_opciones_inactivas_efectivo_y_sin_clasificar_bloqueadas(self):
        for naturaleza, activo in (("ELECTRONICO", False), ("EFECTIVO", True), ("SIN_CLASIFICAR", False)):
            metodo = MetodoPago.objects.create(nombre="Alternativa " + naturaleza, naturaleza=naturaleza, activo=activo)
            if naturaleza == "SIN_CLASIFICAR":
                MetodoPago.objects.filter(pk=metodo.pk).update(activo=True)
            with self.subTest(naturaleza=naturaleza), self.assertRaises(ValidationError):
                cambiar_metodo_pago(**self.argumentos(metodo_pago_id=metodo.pk))
        self.assertFalse(CambioMetodoPago.objects.exists())
        self.assertFalse(Pago.objects.exists())

    def test_idempotencia_reproduce_auditoria_incluso_tras_completar(self):
        datos = self.argumentos()
        primero = cambiar_metodo_pago(**datos)
        iniciar_pago(transaccion_id=self.transaccion.pk, usuario_id="http-usuario", roles=["USUARIO"],
                     cliente_seleccionado_id=self.cliente_pago.pk, provider=self.provider)
        segundo = cambiar_metodo_pago(**datos)
        self.assertEqual(segundo, {**primero, "reutilizado": True})
        self.assertEqual(CambioMetodoPago.objects.count(), 1)
        self.assertEqual(Pago.objects.count(), 1)
        self.provider.iniciar.assert_called_once()
        with self.assertRaises(ValidationError) as error:
            cambiar_metodo_pago(**{**datos, "metodo_pago_id": self.metodo.pk})
        self.assertEqual(error.exception.code, "CONFLICTO_IDEMPOTENCIA")

    def test_replay_revalida_asociacion_seleccion_y_rol(self):
        datos = self.argumentos()
        cambiar_metodo_pago(**datos)
        for cambios in ({"cliente_seleccionado_id": self.cliente_pago.pk + 100}, {"roles": ["CAJERO", "USUARIO"]},
                        {"usuario_id": "otro"}):
            with self.subTest(cambios=cambios), self.assertRaises(PermissionDenied):
                cambiar_metodo_pago(**{**datos, **cambios})
        UsuarioCliente.objects.update(activo=False)
        with self.assertRaises(PermissionDenied):
            cambiar_metodo_pago(**datos)

    def test_estado_esperado_obsoleto_devuelve_409_sin_mutaciones(self):
        pago = self.crear_pago(self.transaccion, Pago.Estado.RECHAZADO, referencia="pi_stale")
        antes = Pago.objects.values().get(pk=pago.pk)
        for cambios in ({"pago_esperado_id": None}, {"pago_esperado_id": str(uuid.uuid4())},
                        {"metodo_anterior_id": self.nuevo.pk}):
            respuesta = self.cambiar_http(self.cuerpo(pago, **cambios))
            self.assertEqual(respuesta.status_code, 409)
            self.assertEqual(respuesta.json()["codigo"], "ESTADO_DESACTUALIZADO")
        self.assertEqual(Pago.objects.values().get(pk=pago.pk), antes)
        self.assertFalse(CambioMetodoPago.objects.exists())

    def test_entrada_cerrada_tipos_y_uuid_estrictos(self):
        base = self.cuerpo()
        casos = [[], {}, {**base, "extra": 1}, {**base, "metodo_pago_id": True}, {**base, "metodo_anterior_id": "1"},
                 {**base, "pago_esperado_id": ""}, {**base, "clave_idempotencia": None},
                 {**base, "clave_idempotencia": "invalida"}]
        for cuerpo in casos:
            with self.subTest(cuerpo=cuerpo):
                respuesta = self.cambiar_http(cuerpo)
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.json()["codigo"], "ENTRADA_INVALIDA")
        self.assertEqual(self.client.get(self.url("cambiar_metodo")).status_code, 405)
        self.factory_mock.assert_not_called()

    def test_post_rechazado_y_lectura_historial_autorizados_sin_proveedor(self):
        pago = self.crear_pago(self.transaccion, Pago.Estado.RECHAZADO, referencia="pi_historico")
        respuesta = self.cambiar_http(self.cuerpo(pago))
        self.assertEqual(respuesta.status_code, 200)
        consulta = self.client.get(self.url("consultar")).json()
        self.assertEqual(consulta["codigo"], "PAGO_NO_INICIADO")
        self.assertIsNone(consulta["pago_id"])
        self.assertFalse(consulta["vigente"])
        self.assertTrue(consulta["puede_cambiar_metodo"])
        self.assertEqual(consulta["metodo_pago_id"], self.nuevo.pk)
        self.metodo.nombre = "Nombre editado posteriormente"
        self.metodo.save()
        historial = self.client.get(self.url("intentos")).json()["intentos"]
        self.assertEqual(len(historial), 1)
        self.assertEqual(historial[0]["pago_id"], str(pago.pk))
        self.assertEqual(historial[0]["metodo_pago_nombre"], "Método HTTP pagos")
        self.assertFalse(historial[0]["vigente"])
        self.assertNotIn("referencia_externa", historial[0])
        self.factory_mock.assert_not_called()
        UsuarioCliente.objects.update(activo=False)
        self.assertEqual(self.client.get(self.url("intentos")).status_code, 404)

    def test_cajero_consulta_historia_pero_no_puede_cambiar(self):
        self.autenticar(roles=["CAJERO", "USUARIO"])
        self.assertEqual(self.cambiar_http(self.cuerpo()).status_code, 403)
        self.assertFalse(self.client.get(self.url("consultar")).json()["puede_cambiar_metodo"])
        self.assertEqual(self.client.get(self.url("intentos")).status_code, 200)
        self.factory_mock.assert_not_called()

    def test_bd_un_solo_vigente_e_historicos_inmutables(self):
        viejo = self.crear_pago(self.transaccion, Pago.Estado.RECHAZADO, referencia="pi_bd")
        cambiar_metodo_pago(**self.argumentos(viejo))
        self.transaccion.refresh_from_db()
        actual = Pago.objects.create(transaccion=self.transaccion, metodo_pago=self.nuevo, proveedor="stripe",
                                     monto=self.transaccion.monto_origen, moneda_codigo=self.origen.codigo,
                                     base_importe=Pago.BaseImporte.ORIGEN, iniciado_por_keycloak_id="http-usuario")
        otro = Pago(transaccion=self.transaccion, metodo_pago=self.nuevo, proveedor="stripe", monto=actual.monto,
                    moneda_codigo=actual.moneda_codigo, base_importe=actual.base_importe, iniciado_por_keycloak_id="http-usuario")
        otro.huella_solicitud = otro.calcular_huella()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pago.objects.bulk_create([otro])
        viejo.refresh_from_db()
        viejo.vigente = True
        with self.assertRaises(ValidationError):
            viejo.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pago.objects.filter(pk=actual.pk).update(vigente=False)
        self.assertEqual(Transaccion.objects.get(pk=self.transaccion.pk).pago.pk, actual.pk)

    def test_respuesta_tardia_de_archivado_no_escribe_ni_sincroniza_actual(self):
        viejo = self.crear_pago(self.transaccion, Pago.Estado.RECHAZADO, referencia="pi_tardio")
        reserva = _reserva(self.transaccion, viejo)
        cambiar_metodo_pago(**self.argumentos(viejo))
        self.transaccion.refresh_from_db()
        actual = Pago.objects.create(transaccion=self.transaccion, metodo_pago=self.nuevo, proveedor="stripe",
                                     monto=self.transaccion.monto_origen, moneda_codigo=self.origen.codigo,
                                     base_importe=Pago.BaseImporte.ORIGEN, iniciado_por_keycloak_id="http-usuario")
        antes = list(Pago.objects.order_by("id").values())
        with patch("pagos.services.sincronizar_resultado_local") as sincronizar:
            respuesta = _invocar(self.provider, reserva, consulta=False)
        self.assertEqual(respuesta.pago_id, viejo.pk)
        self.assertEqual(respuesta.anomalia, "INTENTO_ARCHIVADO")
        sincronizar.assert_not_called()
        self.assertEqual(list(Pago.objects.order_by("id").values()), antes)
        self.assertEqual(Transaccion.objects.get(pk=self.transaccion.pk).estado, "PENDIENTE")
        self.assertEqual(Transaccion.objects.get(pk=self.transaccion.pk).pago.pk, actual.pk)

    def test_doble_click_concurrente_cambia_una_vez(self):
        if connection.vendor != "postgresql":
            self.skipTest("La serialización de filas requiere PostgreSQL.")
        datos = self.argumentos()
        barrera = Barrier(2)
        def ejecutar():
            close_old_connections()
            try:
                barrera.wait(timeout=10)
                return cambiar_metodo_pago(**datos)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            tareas = [pool.submit(ejecutar) for _ in range(2)]
            resultados = [t.result(timeout=20) for t in tareas]
        self.assertEqual(sorted(r["reutilizado"] for r in resultados), [False, True])
        self.assertEqual(CambioMetodoPago.objects.count(), 1)
        self.assertFalse(Pago.objects.exists())
        self.provider.iniciar.assert_not_called()

    def test_cambio_concurrente_durante_cobro_no_habilita_otro_intento(self):
        if connection.vendor != "postgresql":
            self.skipTest("La serialización de filas requiere PostgreSQL.")
        iniciado, continuar = Event(), Event()
        def proveedor(solicitud):
            iniciado.set()
            if not continuar.wait(timeout=15):
                raise TimeoutError
            return self.resultado(solicitud)
        self.provider.iniciar.side_effect = proveedor
        tx_id, cliente_id = self.transaccion.pk, self.cliente_pago.pk
        def cobrar():
            close_old_connections()
            try:
                return iniciar_pago(transaccion_id=tx_id, usuario_id="http-usuario", roles=["USUARIO"],
                                    cliente_seleccionado_id=cliente_id, provider=self.provider)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=1) as pool:
            tarea = pool.submit(cobrar)
            try:
                self.assertTrue(iniciado.wait(timeout=10))
                actual = Pago.objects.get(transaccion=self.transaccion)
                with self.assertRaises(ValidationError) as error:
                    cambiar_metodo_pago(**self.argumentos(actual))
                self.assertEqual(error.exception.code, "CAMBIO_METODO_NO_PERMITIDO")
            finally:
                continuar.set()
            self.assertEqual(tarea.result(timeout=20).estado, EstadoPago.APROBADO)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertFalse(CambioMetodoPago.objects.exists())
        self.provider.iniciar.assert_called_once()
