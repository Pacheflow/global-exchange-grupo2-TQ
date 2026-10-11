"""Contrato Stripe TEST con SDK real y transporte simulado; nunca usa Internet."""

import json
import logging
from dataclasses import FrozenInstanceError, asdict, replace
from decimal import Decimal, localcontext
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import stripe
from django.test import SimpleTestCase, override_settings

from .providers import CodigoResultado, EstadoPago, SolicitudPago
from .stripe_provider import EscenarioStripeTest, StripePaymentProvider


@override_settings(STRIPE_SECRET_KEY="sk_test_fixture_only", STRIPE_TIMEOUT_SECONDS=5)
class StripePaymentProviderTests(SimpleTestCase):
    def setUp(self):
        self.solicitud = SolicitudPago(uuid4(), 7, Decimal("12.34"), "USD", "a" * 64)
        self.intents = mock.Mock()
        self.client = SimpleNamespace(v1=SimpleNamespace(payment_intents=self.intents))
        self.provider = StripePaymentProvider(client=self.client)
        self.socket = self.enterContext(mock.patch("socket.socket.connect", side_effect=AssertionError("Red prohibida en tests.")))
        self.addCleanup(self.socket.assert_not_called)

    def intent(self, status="succeeded", **datos):
        resultado = {
            "object": "payment_intent", "id": "pi_fixture123", "livemode": False,
            "amount": 1234, "currency": "usd", "status": status,
            "amount_received": 1234 if status == "succeeded" else 0,
            "metadata": {
                "pago_id": str(self.solicitud.pago_id), "transaccion_id": "7",
                "huella_solicitud": self.solicitud.huella_solicitud,
            },
        }
        resultado.update(datos)
        return resultado

    def test_solicitud_inmutable_y_neutral(self):
        with self.assertRaises(FrozenInstanceError):
            self.solicitud.monto = Decimal("1")
        self.assertNotIn("escenario", asdict(self.solicitud))

    def test_inicio_aprobado_payload_y_clave_estables(self):
        self.intents.create.return_value = self.intent()
        primera = self.provider.iniciar(self.solicitud)
        segunda = self.provider.iniciar(self.solicitud)
        self.assertEqual(primera, segunda)
        self.assertEqual(primera.estado, EstadoPago.APROBADO)
        self.assertEqual(primera.monto, Decimal("12.34"))
        self.assertEqual(primera.moneda, "USD")
        args, kwargs = self.intents.create.call_args
        self.assertEqual(args[0]["amount"], 1234)
        self.assertTrue(args[0]["confirm"])
        self.assertEqual(args[0]["capture_method"], "automatic")
        self.assertNotIn("payment_method_types", args[0])
        self.assertEqual(args[0]["automatic_payment_methods"], {
            "enabled": True, "allow_redirects": "never",
        })
        self.assertNotIn("return_url", args[0])
        self.assertEqual(args[0]["currency"], "usd")
        self.assertNotIn("confirmation_method", args[0])
        self.assertEqual(args[0]["metadata"], {
            "pago_id": str(self.solicitud.pago_id),
            "transaccion_id": str(self.solicitud.transaccion_id),
            "huella_solicitud": self.solicitud.huella_solicitud,
        })
        self.assertNotIn("error_on_requires_action", args[0])
        self.assertEqual(args[0]["payment_method"], "pm_card_visa")
        self.assertEqual(kwargs["options"]["idempotency_key"], f"ge:hu28:pago:{self.solicitud.pago_id}:create:v1")
        self.assertEqual(self.intents.create.call_args_list[0], self.intents.create.call_args_list[1])

    def test_fixture_rechazo_solo_en_adaptador(self):
        provider = StripePaymentProvider(client=self.client, escenario_test=EscenarioStripeTest.RECHAZO)
        self.intents.create.return_value = self.intent(
            "requires_payment_method", last_payment_error={"type": "card_error", "code": "card_declined"},
        )
        self.assertEqual(provider.iniciar(self.solicitud).estado, EstadoPago.RECHAZADO)
        self.assertEqual(self.intents.create.call_args.args[0]["payment_method"], "pm_card_visa_chargeDeclined")

    def test_estados_normalizados_sin_optimismo(self):
        for status, esperado in (
            ("processing", EstadoPago.EN_PROCESO), ("requires_confirmation", EstadoPago.EN_PROCESO),
            ("requires_payment_method", EstadoPago.EN_PROCESO),
            ("requires_capture", EstadoPago.INDETERMINADO), ("requires_action", EstadoPago.INDETERMINADO),
            ("canceled", EstadoPago.RECHAZADO), ("nuevo_estado", EstadoPago.INDETERMINADO),
        ):
            with self.subTest(status=status):
                self.intents.create.return_value = self.intent(status)
                self.assertEqual(self.provider.iniciar(self.solicitud).estado, esperado)
        for status in ("canceled", "requires_payment_method", "processing"):
            self.intents.create.return_value = self.intent(status, amount_received=1234)
            self.assertEqual(self.provider.iniciar(self.solicitud).estado, EstadoPago.INDETERMINADO)
        self.intents.create.return_value = self.intent("requires_payment_method", last_payment_error={"type": "api_error"})
        self.assertEqual(self.provider.iniciar(self.solicitud).estado, EstadoPago.INDETERMINADO)

    def test_respuesta_valida_identidad_importe_moneda_modo_y_recibido(self):
        casos = (
            {"livemode": True}, {"livemode": 0}, {"object": "charge"}, {"id": "otra"},
            {"amount": 1235}, {"amount": "1234"}, {"amount": 1234.0}, {"amount": True},
            {"currency": "eur"}, {"amount_received": 1233}, {"amount_received": "1234"},
            {"amount_received": 1234.0}, {"amount_received": True},
            *({"metadata": {**self.intent()["metadata"], campo: "otro"}} for campo in self.intent()["metadata"]),
        )
        for cambios in casos:
            with self.subTest(cambios=cambios):
                self.intents.create.return_value = self.intent(**cambios)
                self.assertEqual(self.provider.iniciar(self.solicitud).estado, EstadoPago.INDETERMINADO)
        self.intents.create.return_value = "no-json"
        self.assertEqual(self.provider.iniciar(self.solicitud).codigo, CodigoResultado.RESPUESTA_INVALIDA)

    def test_conversion_exacta_monedas_admitidas(self):
        for moneda, monto, unidades in (
            ("PYG", "1234", 1234), ("USD", "12.34", 1234), ("EUR", "12.34", 1234),
            ("BRL", "12.34", 1234), ("ARS", "12.34", 1234),
        ):
            with self.subTest(moneda=moneda):
                solicitud = replace(self.solicitud, moneda=moneda, monto=Decimal(monto))
                self.intents.create.return_value = self.intent(currency=moneda.lower())
                with localcontext() as contexto:
                    contexto.prec = 2
                    resultado = self.provider.iniciar(solicitud)
                self.assertEqual(resultado.estado, EstadoPago.APROBADO)
                self.assertEqual(self.intents.create.call_args.args[0]["amount"], unidades)
                self.assertEqual(resultado.monto, Decimal(monto))

    def test_solicitud_invalida_no_envia_a_stripe(self):
        for cambios in (
            {"monto": Decimal("0")}, {"monto": Decimal("-1")}, {"monto": Decimal("NaN")},
            {"monto": Decimal("sNaN")}, {"monto": Decimal("Infinity")}, {"monto": 12.34},
            {"monto": Decimal("12.345")}, {"monto": Decimal("1000000")},
            {"moneda": "PYG", "monto": Decimal("1.1")}, {"moneda": "JPY"},
            {"moneda": "usd"}, {"transaccion_id": True}, {"transaccion_id": -1},
            {"pago_id": "no-uuid"}, {"huella_solicitud": "no-hash"},
        ):
            with self.subTest(cambios=cambios):
                resultado = self.provider.iniciar(replace(self.solicitud, **cambios))
                self.assertEqual(resultado.estado, EstadoPago.ERROR)
        self.intents.create.assert_not_called()

    def test_clave_live_ausente_timeout_invalido_y_escenario_no_envian(self):
        for clave in ("", "sk_live_fixture_only", "pk_test_fixture_only"):
            with self.subTest(clave=clave), override_settings(STRIPE_SECRET_KEY=clave):
                self.assertEqual(self.provider.iniciar(self.solicitud).codigo, CodigoResultado.CONFIGURACION_INVALIDA)
        for timeout in (0, -1, None, float("nan"), float("inf"), 61, True):
            with self.subTest(timeout=timeout), override_settings(STRIPE_TIMEOUT_SECONDS=timeout):
                self.assertEqual(self.provider.iniciar(self.solicitud).estado, EstadoPago.ERROR)
        resultado = StripePaymentProvider(client=self.client, escenario_test={}).iniciar(self.solicitud)
        self.assertEqual(resultado.estado, EstadoPago.ERROR)
        self.intents.create.assert_not_called()

    def test_carderror_verificado_sin_exponer_payload(self):
        intent = self.intent("requires_payment_method", last_payment_error={"type": "card_error", "code": "card_declined"})
        intent["client_secret"] = "MARCADOR_PRIVADO"
        self.intents.create.side_effect = stripe.CardError(
            "MARCADOR_PRIVADO", "payment_method", "card_declined", http_status=402,
            json_body={"error": {"payment_intent": intent}},
        )
        resultado = self.provider.iniciar(self.solicitud)
        self.assertEqual(resultado.estado, EstadoPago.RECHAZADO)
        self.assertNotIn("MARCADOR_PRIVADO", repr(resultado) + resultado.mensaje)

    def test_error_antes_ejecucion_y_errores_inciertos(self):
        for error, esperado in (
            (stripe.AuthenticationError("MARCADOR_PRIVADO", http_status=401), EstadoPago.ERROR),
            (stripe.InvalidRequestError("MARCADOR_PRIVADO", "amount", http_status=400), EstadoPago.ERROR),
            (stripe.APIConnectionError("MARCADOR_PRIVADO"), EstadoPago.INDETERMINADO),
            (stripe.APIError("MARCADOR_PRIVADO", http_status=500), EstadoPago.INDETERMINADO),
            (stripe.IdempotencyError("MARCADOR_PRIVADO", http_status=409), EstadoPago.INDETERMINADO),
            (TimeoutError("MARCADOR_PRIVADO"), EstadoPago.INDETERMINADO),
            (stripe.CardError("MARCADOR_PRIVADO", "payment_method", "card_declined"), EstadoPago.INDETERMINADO),
        ):
            with self.subTest(error=type(error).__name__):
                self.intents.create.side_effect = error
                resultado = self.provider.iniciar(self.solicitud)
                self.assertEqual(resultado.estado, esperado)
                self.assertNotIn("MARCADOR_PRIVADO", repr(resultado) + resultado.mensaje)

    def test_consulta_solo_retrieve_verifica_referencia(self):
        self.intents.retrieve.return_value = self.intent()
        self.assertEqual(self.provider.consultar(self.solicitud, "pi_fixture123").estado, EstadoPago.APROBADO)
        self.intents.retrieve.assert_called_once_with("pi_fixture123")
        self.intents.create.assert_not_called()
        self.intents.search.assert_not_called()
        self.intents.retrieve.return_value = self.intent(id="pi_otro123")
        self.assertEqual(self.provider.consultar(self.solicitud, "pi_fixture123").estado, EstadoPago.INDETERMINADO)

    def test_consulta_sin_referencia_y_error_no_crean_ni_buscan(self):
        self.assertEqual(self.provider.consultar(self.solicitud, None).estado, EstadoPago.INDETERMINADO)
        self.intents.retrieve.assert_not_called()
        self.intents.search.assert_not_called()
        self.intents.retrieve.side_effect = stripe.InvalidRequestError("MARCADOR_PRIVADO", "id", http_status=404)
        self.assertEqual(self.provider.consultar(self.solicitud, "pi_fixture123").estado, EstadoPago.INDETERMINADO)
        self.intents.create.assert_not_called()

    def test_conciliacion_excepcional_unico_candidato_vuelve_a_consultar(self):
        self.intents.search.return_value = {"has_more": False, "data": [{"id": "pi_fixture123"}]}
        self.intents.retrieve.return_value = self.intent()
        self.assertEqual(self.provider.conciliar_sin_referencia(self.solicitud).estado, EstadoPago.APROBADO)
        query = self.intents.search.call_args.args[0]["query"]
        for valor in self.intent()["metadata"].values():
            self.assertIn(valor, query)
        self.intents.retrieve.assert_called_once_with("pi_fixture123")
        self.intents.create.assert_not_called()

    def test_conciliacion_cero_multiples_paginacion_o_fallo_conserva_incertidumbre(self):
        for respuesta in (
            {"has_more": False, "data": []},
            {"has_more": False, "data": [{"id": "pi_uno"}, {"id": "pi_dos"}]},
            {"has_more": True, "data": [{"id": "pi_uno"}]}, "respuesta inválida",
        ):
            self.intents.search.return_value = respuesta
            self.assertEqual(self.provider.conciliar_sin_referencia(self.solicitud).estado, EstadoPago.INDETERMINADO)
        self.intents.search.side_effect = TimeoutError("MARCADOR_PRIVADO")
        self.assertEqual(self.provider.conciliar_sin_referencia(self.solicitud).estado, EstadoPago.INDETERMINADO)
        self.intents.retrieve.assert_not_called()
        self.intents.create.assert_not_called()

    def test_sdk_real_stripeobject_y_reintento_transportador_misma_clave(self):
        transporte = stripe.RequestsClient(timeout=5)
        cliente = stripe.StripeClient("sk_test_fixture_only", http_client=transporte, max_network_retries=1)
        provider = StripePaymentProvider(client=cliente)
        with mock.patch.object(transporte, "request", side_effect=[
            stripe.APIConnectionError("Error ficticio de conexión.", should_retry=True),
            (json.dumps(self.intent()), 200, {}),
        ]) as llamada, mock.patch("time.sleep"):
            resultado = provider.iniciar(self.solicitud)
        self.assertEqual(resultado.estado, EstadoPago.APROBADO)
        self.assertEqual(llamada.call_count, 2)
        claves = [call.args[2]["Idempotency-Key"] for call in llamada.call_args_list]
        self.assertEqual(claves, [f"ge:hu28:pago:{self.solicitud.pago_id}:create:v1"] * 2)

    def test_sdk_debug_no_emite_payload_ni_envia(self):
        cliente = stripe.StripeClient("sk_test_fixture_only", max_network_retries=1)
        provider = StripePaymentProvider(client=cliente)
        for parche, valor in (
            ("stripe.log", "debug"), ("stripe._util.STRIPE_LOG", "debug"),
            ("stripe.log", "info"), ("stripe._util.STRIPE_LOG", "info"),
        ):
            with mock.patch(parche, valor), mock.patch("stripe.RequestsClient.request") as llamada:
                self.assertEqual(provider.iniciar(self.solicitud).codigo, CodigoResultado.CONFIGURACION_INVALIDA)
                llamada.assert_not_called()
        logger = logging.getLogger("stripe")
        for nivel in (logging.DEBUG, logging.INFO):
            with mock.patch.object(logger, "getEffectiveLevel", return_value=nivel):
                self.assertEqual(provider.iniciar(self.solicitud).estado, EstadoPago.ERROR)
