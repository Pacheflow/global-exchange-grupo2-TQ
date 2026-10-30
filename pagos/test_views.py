"""Contrato HTTP de pagos, sin Internet ni repetición de pruebas de concurrencia."""

import time
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import transaction, connection
from django.urls import resolve, reverse
from django.utils import timezone

from clientes.models import CategoriaCliente, Cliente, UsuarioCliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from operaciones.models import Transaccion
from tasas.models import TasaComercial
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)

from .factory import obtener_payment_provider
from .models import Pago
from .providers import CodigoResultado, EstadoPago, PaymentProvider, ResultadoPago
from .services import EstadoPagoPersistido, PersistenciaPagoError
from .stripe_provider import EscenarioStripeTest


class _EscenarioHTTP:
    def setUp(self):
        categoria, _ = CategoriaCliente.objects.get_or_create(nombre="Minorista")
        self.cliente_pago = Cliente.objects.create(
            nombre_razon_social="Cliente HTTP pagos", tipo_persona="FISICA",
            documento="http-pagos", categoria=categoria,
        )
        UsuarioCliente.objects.create(
            cliente=self.cliente_pago, keycloak_user_id="http-usuario", username="operador",
            rol_en_cliente="OPERADOR", activo=True,
        )
        self.origen, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"},
        )
        self.destino, _ = Moneda.objects.get_or_create(
            codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"},
        )
        self.metodo = MetodoPago.objects.create(nombre="Método HTTP pagos", naturaleza="ELECTRONICO")
        self.tasa = TasaComercial.objects.create(
            moneda_origen=self.origen, moneda_destino=self.destino,
            compra=Decimal("7000"), venta=Decimal("7200"), vigente=True,
            usuario_id="http-usuario", usuario_username="operador",
        )
        self.transaccion = self.crear_transaccion()
        from fondos.test_utils import crear_fondos_prueba
        crear_fondos_prueba((self.destino,))
        self.provider = Mock(spec=PaymentProvider)
        self.provider.iniciar.side_effect = lambda s: self.resultado(s)
        self.provider.consultar.side_effect = lambda s, ref: self.resultado(s, referencia=ref)
        self.provider.conciliar_sin_referencia.side_effect = lambda s: self.resultado(s)
        self.factory = patch("pagos.views.obtener_payment_provider", return_value=self.provider)
        self.factory_mock = self.factory.start()
        self.addCleanup(self.factory.stop)
        self.autenticar()

    def autenticar(self, cliente_http=None, roles=None):
        cliente_http = cliente_http or self.client
        session = cliente_http.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = time.time() + 600
        session[SESSION_ROLES] = roles if roles is not None else ["USUARIO"]
        session[SESSION_USUARIO] = {"sub": "http-usuario", "username": "operador"}
        session["selected_client"] = {"id": self.cliente_pago.pk}
        session.save()

    def crear_transaccion(self, **cambios):
        datos = dict(
            version_flujo=1, canal="ONLINE", naturaleza_metodo="ELECTRONICO",
            clave_idempotencia=str(uuid.uuid4()), cliente=self.cliente_pago,
            creado_por_keycloak_id="http-usuario", tipo="COMPRA",
            moneda_origen=self.origen, moneda_destino=self.destino,
            monto_origen=Decimal("12.34"), monto_destino=Decimal("86380"),
            tasa_comercial=self.tasa, tasa_aplicada=Decimal("7000"),
            porcentaje_comision=Decimal("0"), importe_comision=Decimal("0"),
            metodo_pago=self.metodo, metodo_pago_nombre=self.metodo.nombre, estado="PENDIENTE",
        )
        datos.update(cambios)
        return Transaccion.objects.create(**datos)

    def crear_pago(self, transaccion, estado, *, referencia=None):
        if estado not in (Pago.Estado.ERROR, Pago.Estado.RECHAZADO):
            from fondos.services import reservar
            with transaction.atomic():
                reservar(transaccion)
        return Pago.objects.create(
            transaccion=transaccion, metodo_pago=self.metodo, proveedor="stripe",
            monto=transaccion.monto_origen, moneda_codigo=self.origen.codigo,
            base_importe=Pago.BaseImporte.ORIGEN, iniciado_por_keycloak_id="http-usuario",
            estado=estado, referencia_externa=referencia,
            aprobado_en=timezone.now() if estado == Pago.Estado.APROBADO else None,
            trazabilidad=([dict(fecha=timezone.now().isoformat(), estado="ERROR", codigo="ERROR_SIN_EJECUCION")]
                          if estado == Pago.Estado.ERROR else []),
        )

    @staticmethod
    def resultado(solicitud, estado=EstadoPago.APROBADO, referencia=None):
        if estado == EstadoPago.ERROR:
            return ResultadoPago(estado, CodigoResultado.ERROR_SIN_EJECUCION)
        return ResultadoPago(
            estado, CodigoResultado.RESULTADO_DESCONOCIDO if estado == EstadoPago.INDETERMINADO else CodigoResultado(estado),
            referencia or "pi_" + str(solicitud.pago_id),
            solicitud.monto, solicitud.moneda,
        )

    def url(self, nombre, transaccion=None):
        return reverse("pagos:" + nombre, kwargs={"transaccion_id": (transaccion or self.transaccion).pk})

    def post(self, nombre, transaccion=None, cuerpo=b"{}", cliente_http=None, **extra):
        return (cliente_http or self.client).post(
            self.url(nombre, transaccion), data=cuerpo, content_type="application/json", **extra,
        )

    def assert_respuesta_pago(self, respuesta, transaccion, estado, *, post=False):
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        campos = {"transaccion_id", "pago_id", "estado", "codigo"}
        if post:
            campos.add("reutilizado")
        else:
            campos.update({"vigente", "puede_cambiar_metodo", "metodo_pago_id", "metodo_pago_nombre"})
            self.assertIsInstance(datos["vigente"], bool)
            self.assertIsInstance(datos["puede_cambiar_metodo"], bool)
        self.assertEqual(set(datos), campos)
        self.assertEqual(datos["transaccion_id"], transaccion.pk)
        self.assertEqual(datos["estado"], estado)
        self.assertIn("no-store", respuesta.headers["Cache-Control"])
        self.assertIn("private", respuesta.headers["Cache-Control"])
        return datos


class PagoHTTPFlujoTests(_EscenarioHTTP, TransactionTestCase):
    def test_inicio_sin_fondos_y_nuevo_intento_explicito_tras_reponer(self):
        """Como en QA #21, el primer POST da 400 sin Pago/Stripe; reponer y pulsar otra vez aprueba un único Pago."""
        from fondos.models import MovimientoFondo
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto="0.000001")
        primero = self.post("iniciar")
        self.assertEqual(primero.status_code, 400)
        self.assertEqual(primero.json()["codigo"], "DISPONIBILIDAD_INSUFICIENTE")
        self.assertIn("No se realizó ningún cobro en este intento", primero.json()["error"])
        self.assertFalse(Pago.objects.exists())
        self.provider.iniciar.assert_not_called()
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto=self.transaccion.monto_destino * 10)
        segundo = self.post("iniciar")
        self.assertEqual(segundo.status_code, 200)
        self.assertEqual(segundo.json()["estado"], "APROBADO")
        self.assertFalse(segundo.json()["reutilizado"])
        pago = Pago.objects.get(transaccion=self.transaccion)
        self.assertEqual(str(pago.pk), segundo.json()["pago_id"])
        self.assertEqual([e["codigo"] for e in pago.trazabilidad], ["RESERVADO", "APROBADO"])
        self.assertEqual(self.client.get(self.url("consultar")).json()["estado"], "APROBADO")
        self.provider.iniciar.assert_called_once()

    def test_disponibilidad_inicio_y_reintento_muestran_error_sin_cobro(self):
        """HTTP sin fondos muestra aviso seguro, preserva Pago ERROR y no invoca Stripe; fallo técnico da 500."""
        from fondos.models import MovimientoFondo
        from django.db import DatabaseError
        MovimientoFondo.objects.filter(operacion__isnull=True).update(monto="0.000001")
        for accion in ("iniciar", "reintentar"):
            if accion == "reintentar":
                pago = self.crear_pago(self.transaccion, Pago.Estado.ERROR)
                traza = list(pago.trazabilidad)
            respuesta = self.post(accion)
            self.assertEqual(respuesta.status_code, 400)
            self.assertEqual(respuesta.json(), {
                "codigo": "DISPONIBILIDAD_INSUFICIENTE",
                "error": "No hay disponibilidad suficiente para procesar esta operación. "
                         "No se realizó ningún cobro en este intento. Intenta más tarde.",
            })
            if accion == "iniciar":
                self.assertFalse(Pago.objects.exists())
            else:
                pago.refresh_from_db()
                self.assertEqual(pago.estado, "ERROR")
                self.assertEqual(pago.trazabilidad, traza)
        with patch("pagos.services.reservar", side_effect=DatabaseError("privado")):
            respuesta = self.post("reintentar")
        self.assertEqual(respuesta.status_code, 500)
        self.assertNotContains(respuesta, "disponibilidad", status_code=500)
        self.provider.iniciar.assert_not_called()

    def test_cajero_consulta_pago_sin_selected_client_usuario_no(self):
        """Cajero sin asociaciones consulta localmente; USUARIO conserva selección y asociación obligatorias."""
        pago = self.crear_pago(self.transaccion, Pago.Estado.ERROR)
        for roles, status in ((["CAJERO"], 200), (["USUARIO"], 400)):
            self.autenticar(roles=roles)
            sesion = self.client.session
            sesion.pop("selected_client", None)
            sesion.save()
            respuesta = self.client.get(self.url("consultar"))
            self.assertEqual(respuesta.status_code, status)
            if status == 200:
                self.assertEqual(respuesta.json()["pago_id"], str(pago.pk))
        self.autenticar(roles=["CAJERO"])
        sesion = self.client.session
        sesion.pop("selected_client", None)
        sesion[SESSION_USUARIO] = {"sub": "ajeno"}
        sesion.save()
        UsuarioCliente.objects.all().delete()
        self.assertEqual(self.client.get(self.url("consultar")).status_code, 200)
        self.autenticar(roles=["USUARIO"])
        self.assertEqual(self.client.get(self.url("consultar")).status_code, 404)
        self.factory_mock.assert_not_called()

    def test_lectura_cajero_no_amplia_recuperacion_externa(self):
        """Sin asociación, CAJERO/USUARIO lee Pago pero no recupera externamente ni inicia cobros."""
        self.crear_pago(self.transaccion, Pago.Estado.ERROR)
        UsuarioCliente.objects.all().delete()
        self.autenticar(roles=["CAJERO", "USUARIO"])
        self.assertEqual(self.client.get(self.url("consultar")).status_code, 200)
        self.assertEqual(self.post("recuperar").status_code, 404)
        for accion in ("iniciar", "reintentar"):
            self.assertEqual(self.post(accion).status_code, 403)
        self.provider.consultar.assert_not_called()
        self.provider.conciliar_sin_referencia.assert_not_called()
        self.provider.iniciar.assert_not_called()

    def test_cajero_consulta_pero_no_inicia_ni_reintenta_y_admin_no_opera(self):
        pago = self.crear_pago(self.transaccion, Pago.Estado.ERROR)
        for roles in (["CAJERO"], ["CAJERO", "USUARIO"], ["ADMINISTRADOR", "CAJERO", "USUARIO"]):
            with self.subTest(roles=roles):
                self.autenticar(roles=roles)
                for accion in ("iniciar", "reintentar"):
                    self.assertEqual(self.post(accion).status_code, 403)
                consulta = self.client.get(self.url("consultar"))
                self.assertEqual(consulta.status_code, 403 if "ADMINISTRADOR" in roles else 200)
                if consulta.status_code == 200:
                    self.assertEqual(consulta.json()["pago_id"], str(pago.pk))
                    self.assertEqual(consulta.json()["estado"], "ERROR")
        self.factory_mock.assert_not_called()
        self.provider.iniciar.assert_not_called()
        pago.refresh_from_db()
        self.assertEqual(pago.estado, "ERROR")

    def test_inicio_valido_repetido_y_estados_persistidos_siempre_200(self):
        """Repetir inicio reutiliza Pago; solo APROBADO completa y los demás estados conservan pendiente."""
        for estado in (EstadoPago.APROBADO, EstadoPago.RECHAZADO, EstadoPago.ERROR, EstadoPago.INDETERMINADO):
            with self.subTest(estado=estado):
                tx = self.crear_transaccion()
                self.provider.iniciar.side_effect = lambda s: self.resultado(s, estado)
                llamadas = self.provider.iniciar.call_count
                primero = self.assert_respuesta_pago(self.post("iniciar", tx, cuerpo=b""), tx, estado, post=True)
                segundo = self.assert_respuesta_pago(self.post("iniciar", tx), tx, estado, post=True)
                self.assertFalse(primero["reutilizado"])
                self.assertTrue(segundo["reutilizado"])
                self.assertEqual(primero["pago_id"], segundo["pago_id"])
                self.assertEqual(self.provider.iniciar.call_count, llamadas + 1)
                self.assertEqual(Pago.objects.filter(transaccion=tx).count(), 1)
                tx.refresh_from_db()
                self.assertEqual(tx.estado, "COMPLETADA" if estado == EstadoPago.APROBADO else "PENDIENTE")

    def test_venta_inicio_y_reintento_rechazados_sin_pago_ni_io(self):
        self.transaccion.tipo = "VENTA"
        self.transaccion.save()
        for nombre in ("iniciar", "reintentar"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.post(nombre).status_code, 400)
        self.provider.iniciar.assert_not_called()
        self.assertFalse(Pago.objects.exists())
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, "PENDIENTE")

    def test_inexistente_y_ajena_tienen_mismo_404_en_las_cuatro_rutas(self):
        ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente ajeno HTTP", tipo_persona="FISICA", documento="http-ajeno",
        )
        tx_ajena = self.crear_transaccion(cliente=ajeno)
        esperado = {"error": "La transacción solicitada no está disponible.", "codigo": "TRANSACCION_NO_DISPONIBLE"}
        for nombre in ("consultar", "iniciar", "reintentar", "recuperar"):
            for identificador in (tx_ajena.pk, tx_ajena.pk + 99999):
                with self.subTest(nombre=nombre, identificador=identificador):
                    url = reverse("pagos:" + nombre, kwargs={"transaccion_id": identificador})
                    respuesta = self.client.get(url) if nombre == "consultar" else self.client.post(url, data=b"{}", content_type="application/json")
                    self.assertEqual(respuesta.status_code, 404)
                    self.assertEqual(respuesta.json(), esperado)
                    self.assertIn("no-store", respuesta.headers["Cache-Control"])
        self.provider.iniciar.assert_not_called()
        self.provider.consultar.assert_not_called()
        self.provider.conciliar_sin_referencia.assert_not_called()

    def test_reintento_error_reutiliza_pago_y_solicitud(self):
        pago = self.crear_pago(self.transaccion, Pago.Estado.ERROR)
        datos = self.assert_respuesta_pago(self.post("reintentar"), self.transaccion, EstadoPago.APROBADO, post=True)
        self.assertEqual(datos["pago_id"], str(pago.pk))
        self.assertTrue(datos["reutilizado"])
        self.provider.iniciar.assert_called_once()
        self.assertEqual(self.provider.iniciar.call_args.args[0].pago_id, pago.pk)

    def test_reintento_fuera_error_devuelve_estado_existente_sin_nueva_llamada(self):
        for estado in (Pago.Estado.EN_PROCESO, Pago.Estado.INDETERMINADO, Pago.Estado.APROBADO, Pago.Estado.RECHAZADO):
            with self.subTest(estado=estado):
                tx = self.crear_transaccion()
                pago = self.crear_pago(tx, estado, referencia="pi_" + uuid.uuid4().hex if estado in (Pago.Estado.APROBADO, Pago.Estado.RECHAZADO) else None)
                antes = Pago.objects.values().get(pk=pago.pk)
                datos = self.assert_respuesta_pago(self.post("reintentar", tx), tx, estado, post=True)
                self.assertTrue(datos["reutilizado"])
                self.assertEqual(Pago.objects.values().get(pk=pago.pk), antes)
        self.provider.iniciar.assert_not_called()

    def test_recuperacion_indeterminada_con_y_sin_referencia_no_inicia_cobros(self):
        for referencia in (None, "pi_http_recuperar"):
            with self.subTest(referencia=referencia):
                tx = self.crear_transaccion()
                pago = self.crear_pago(tx, Pago.Estado.INDETERMINADO, referencia=referencia)
                datos = self.assert_respuesta_pago(self.post("recuperar", tx), tx, EstadoPago.APROBADO, post=True)
                self.assertEqual(datos["pago_id"], str(pago.pk))
                self.assertTrue(datos["reutilizado"])
        self.provider.iniciar.assert_not_called()
        self.provider.consultar.assert_called_once()
        self.provider.conciliar_sin_referencia.assert_called_once()


class PagoHTTPLecturaEntradaTests(_EscenarioHTTP, TestCase):
    def test_get_local_sin_pago_en_proceso_y_aprobado_historico_sin_provider_ni_locks(self):
        datos = self.assert_respuesta_pago(self.client.get(self.url("consultar")), self.transaccion, None)
        self.assertEqual(datos["codigo"], "PAGO_NO_INICIADO")
        self.assertIsNone(datos["pago_id"])
        for estado, estado_operacion in (
            (Pago.Estado.EN_PROCESO, "COMPLETADA"),
            (Pago.Estado.APROBADO, "COMPLETADA"),
            (Pago.Estado.APROBADO, "CANCELADA"),
        ):
            tx = self.crear_transaccion()
            pago = self.crear_pago(tx, estado, referencia="pi_" + uuid.uuid4().hex if estado == Pago.Estado.APROBADO else None)
            if estado_operacion == "CANCELADA":
                Transaccion.objects.filter(pk=tx.pk).update(
                    estado="CANCELADA", cancelado_por_keycloak_id="http-usuario",
                    cancelado_por_username="operador", cancelado_en=timezone.now(),
                    motivo_cancelacion="Antecedente histórico de prueba.",
                )
            else:
                Transaccion.objects.filter(pk=tx.pk).update(estado=estado_operacion)
            self.metodo.desactivar()
            antes = Pago.objects.values().get(pk=pago.pk)
            with CaptureQueriesContext(connection) as consultas:
                respuesta = self.client.get(self.url("consultar", tx))
            self.assert_respuesta_pago(respuesta, tx, estado)
            self.assertFalse(any("FOR UPDATE" in q["sql"] for q in consultas))
            self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in consultas))
            self.assertEqual(Pago.objects.values().get(pk=pago.pk), antes)
        self.factory_mock.assert_not_called()

    def test_namespace_metodos_incorrectos_y_vistas_fuera_de_atomic(self):
        for nombre, sufijo in (("iniciar", "iniciar/"), ("reintentar", "reintentar/"), ("recuperar", "recuperar/"), ("consultar", "")):
            with self.subTest(nombre=nombre):
                url = self.url(nombre)
                self.assertEqual(url, f"/api/operaciones/{self.transaccion.pk}/pago/{sufijo}")
                self.assertIn("default", resolve(url).func._non_atomic_requests)
                respuesta = self.client.post(url) if nombre == "consultar" else self.client.get(url)
                self.assertEqual(respuesta.status_code, 405)
                self.assertIn("no-store", respuesta.headers["Cache-Control"])
        self.factory_mock.assert_not_called()

    def test_autenticacion_roles_y_csrf_se_conservan(self):
        anonimo = Client()
        self.assertEqual(anonimo.get(self.url("consultar")).status_code, 401)
        for roles in (["ADMINISTRADOR", "USUARIO"], ["ANALISTA_CAMBIARIO"], []):
            self.autenticar(roles=roles)
            respuesta = self.client.get(self.url("consultar"))
            self.assertEqual(respuesta.status_code, 403)
            self.assertIn("no-store", respuesta.headers["Cache-Control"])
        protegido = Client(enforce_csrf_checks=True)
        self.autenticar(protegido)
        self.assertEqual(self.post("iniciar", cliente_http=protegido).status_code, 403)
        solicitud = RequestFactory().get("/")
        token = get_token(solicitud)
        protegido.cookies[settings.CSRF_COOKIE_NAME] = solicitud.META["CSRF_COOKIE"]
        resultado = EstadoPagoPersistido(uuid.uuid4(), EstadoPago.EN_PROCESO, CodigoResultado.EN_PROCESO, False)
        with patch("pagos.views.iniciar_pago", return_value=resultado):
            self.assertEqual(self.post("iniciar", cliente_http=protegido, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.provider.iniciar.assert_not_called()

    def test_contexto_cliente_ausente_invalido_o_no_entero_es_400(self):
        for seleccionado in (None, {}, {"id": True}, {"id": "1"}, {"id": 0}, {"id": -1}, []):
            session = self.client.session
            session["selected_client"] = seleccionado
            session.save()
            for nombre in ("consultar", "iniciar", "reintentar", "recuperar"):
                with self.subTest(seleccionado=seleccionado, nombre=nombre):
                    respuesta = self.client.get(self.url(nombre)) if nombre == "consultar" else self.post(nombre)
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertEqual(respuesta.json()["codigo"], "CONTEXTO_CLIENTE_INVALIDO")
        self.factory_mock.assert_not_called()

    def test_json_invalido_y_cualquier_campo_se_rechazan_antes_de_provider(self):
        cuerpos = [b"{", b"[]", b"null", b'"texto"', b"\xff"]
        campos = (
            "transaccion_id", "monto", "moneda", "tasa", "comision", "pago_id", "provider",
            "referencia_externa", "idempotency_key", "payment_method", "card", "otro",
        )
        cuerpos.extend(('{' + '"' + campo + '": "valor"}').encode() for campo in campos)
        for nombre in ("iniciar", "reintentar", "recuperar"):
            for cuerpo in cuerpos:
                with self.subTest(nombre=nombre, cuerpo=cuerpo):
                    respuesta = self.post(nombre, cuerpo=cuerpo)
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertEqual(respuesta.json()["codigo"], "ENTRADA_INVALIDA")
        with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1):
            respuesta = self.post("iniciar", cuerpo=b"{}")
            self.assertEqual(respuesta.status_code, 400)
            self.assertEqual(respuesta.json()["codigo"], "ENTRADA_INVALIDA")
        self.factory_mock.assert_not_called()

    def test_persistencia_503_y_error_inesperado_500_con_respuesta_cerrada(self):
        for excepcion, status, esperado in (
            (ValidationError({"campo": ["detalle secreto ficticio"]}), 400, {
                "error": "La solicitud de pago no es válida para esta operación.",
                "codigo": "SOLICITUD_PAGO_INVALIDA",
            }),
            (PersistenciaPagoError("detalle secreto ficticio"), 503, {
                "error": "No se pudo confirmar localmente el resultado del pago.",
                "codigo": "PAGO_RECUPERACION_PENDIENTE",
            }),
            (RuntimeError("detalle secreto ficticio"), 500, {
                "error": "No se pudo procesar la solicitud de pago.", "codigo": "ERROR_INTERNO",
            }),
        ):
            with self.subTest(status=status), patch("pagos.views.iniciar_pago", side_effect=excepcion):
                respuesta = self.post("iniciar")
                self.assertEqual(respuesta.status_code, status)
                self.assertEqual(respuesta.json(), esperado)
                self.assertNotIn(b"detalle secreto", respuesta.content)
                self.assertIn("no-store", respuesta.headers["Cache-Control"])

    def test_factory_construye_unicamente_stripe_test_con_escenario_fijo(self):
        with patch("pagos.factory.StripePaymentProvider") as construir:
            self.assertIs(obtener_payment_provider(), construir.return_value)
            construir.assert_called_once_with(escenario_test=EscenarioStripeTest.APROBACION)
