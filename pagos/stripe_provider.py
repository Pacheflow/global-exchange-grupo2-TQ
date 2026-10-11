"""Adaptador Stripe TEST. No persiste pagos, no modifica operaciones ni decide reintentos."""

import math
import logging
import re
from decimal import Decimal, localcontext
from enum import StrEnum
from uuid import UUID

import stripe
from django.conf import settings

from .providers import CodigoResultado, EstadoPago, ResultadoPago, SolicitudPago


class EscenarioStripeTest(StrEnum):
    APROBACION = "APROBACION"
    RECHAZO = "RECHAZO"


class StripePaymentProvider:
    DECIMALES = {"PYG": 0, "USD": 2, "EUR": 2, "BRL": 2, "ARS": 2}
    MAX_UNIDADES = 99_999_999
    METODOS_TEST = {
        EscenarioStripeTest.APROBACION: "pm_card_visa",
        EscenarioStripeTest.RECHAZO: "pm_card_visa_chargeDeclined",
    }
    CODIGOS_RECHAZO = frozenset({"card_declined", "expired_card", "incorrect_cvc", "incorrect_number"})

    def __init__(self, *, client=None, escenario_test=EscenarioStripeTest.APROBACION):
        # Se selecciona exclusivamente al construir el adaptador TEST, no en la solicitud.
        self._escenario = escenario_test
        self._client = client

    @staticmethod
    def _fallo(codigo, *, consulta=False):
        estado = EstadoPago.INDETERMINADO if consulta else EstadoPago.ERROR
        if codigo in (CodigoResultado.RESULTADO_DESCONOCIDO, CodigoResultado.RESPUESTA_INVALIDA):
            estado = EstadoPago.INDETERMINADO
        return ResultadoPago(estado=estado, codigo=codigo)

    def _configuracion_valida(self):
        clave = settings.STRIPE_SECRET_KEY
        timeout = settings.STRIPE_TIMEOUT_SECONDS
        return (
            isinstance(clave, str) and bool(re.fullmatch(r"sk_test_[A-Za-z0-9_]+", clave))
            and isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
            and math.isfinite(timeout) and 0 < timeout <= 60
            and isinstance(self._escenario, EscenarioStripeTest)
            and self._escenario in self.METODOS_TEST
            and self._logging_seguro()
        )

    @staticmethod
    def _logging_seguro():
        """SDK 16: DEBUG/INFO pueden emitir payloads o errores incluso por stderr.

        Comprobación aislada de una API interna: revisar al actualizar el SDK.
        No altera el logging global ni permite llamadas en modo inseguro.
        """
        return (
            stripe._util._console_log_level() not in ("debug", "info")
            and logging.getLogger("stripe").getEffectiveLevel() > logging.INFO
        )

    def _cliente(self):
        if self._client is None:
            self._client = stripe.StripeClient(
                settings.STRIPE_SECRET_KEY,
                http_client=stripe.RequestsClient(timeout=settings.STRIPE_TIMEOUT_SECONDS),
                max_network_retries=1,
            )
        return self._client

    def _unidades(self, solicitud):
        if (
            not isinstance(solicitud, SolicitudPago) or not isinstance(solicitud.pago_id, UUID)
            or type(solicitud.transaccion_id) is not int or not 0 < solicitud.transaccion_id < 2**63
            or not isinstance(solicitud.monto, Decimal) or not solicitud.monto.is_finite()
            or not 0 < solicitud.monto < Decimal("1000000000000")
            or not isinstance(solicitud.moneda, str) or solicitud.moneda not in self.DECIMALES
            or not isinstance(solicitud.huella_solicitud, str)
            or not re.fullmatch(r"[0-9a-f]{64}", solicitud.huella_solicitud)
        ):
            raise ValueError("Solicitud inválida.")
        with localcontext() as contexto:
            contexto.prec = max(28, len(solicitud.monto.as_tuple().digits) + 2)
            unidades = solicitud.monto * (Decimal(10) ** self.DECIMALES[solicitud.moneda])
            if unidades != unidades.to_integral_value() or not 0 < unidades <= self.MAX_UNIDADES:
                raise ValueError("Precisión o importe no representable.")
            return int(unidades)

    @staticmethod
    def _metadata(solicitud):
        return {
            "pago_id": str(solicitud.pago_id),
            "transaccion_id": str(solicitud.transaccion_id),
            "huella_solicitud": solicitud.huella_solicitud,
        }

    @staticmethod
    def _referencia_valida(referencia):
        return isinstance(referencia, str) and bool(re.fullmatch(r"pi_[A-Za-z0-9]{1,252}", referencia))

    @staticmethod
    def _datos(objeto):
        if isinstance(objeto, stripe.StripeObject):
            return objeto.to_dict()
        if isinstance(objeto, dict):
            return objeto
        raise ValueError("Respuesta inválida.")

    def _normalizar(self, objeto, solicitud, unidades, referencia_esperada=None):
        try:
            datos = self._datos(objeto)
            referencia = datos.get("id")
            recibido = datos.get("amount_received")
            if (
                datos.get("object") != "payment_intent" or datos.get("livemode") is not False
                or not self._referencia_valida(referencia)
                or (referencia_esperada is not None and referencia != referencia_esperada)
                or type(datos.get("amount")) is not int or datos["amount"] != unidades
                or datos.get("currency") != solicitud.moneda.lower()
                or datos.get("metadata") != self._metadata(solicitud)
                or type(recibido) is not int or recibido < 0
            ):
                return self._fallo(CodigoResultado.RESPUESTA_INVALIDA)
            estado = EstadoPago.INDETERMINADO
            codigo = CodigoResultado.RESULTADO_DESCONOCIDO
            status = datos.get("status")
            if status == "succeeded" and recibido == unidades:
                estado, codigo = EstadoPago.APROBADO, CodigoResultado.APROBADO
            elif recibido == 0:
                if status in ("processing", "requires_confirmation"):
                    estado, codigo = EstadoPago.EN_PROCESO, CodigoResultado.EN_PROCESO
                elif status == "canceled":
                    estado, codigo = EstadoPago.RECHAZADO, CodigoResultado.RECHAZADO
                elif status == "requires_payment_method":
                    error = datos.get("last_payment_error")
                    if error is None:
                        estado, codigo = EstadoPago.EN_PROCESO, CodigoResultado.EN_PROCESO
                    elif isinstance(error, dict) and error.get("type") == "card_error" and error.get("code") in self.CODIGOS_RECHAZO:
                        estado, codigo = EstadoPago.RECHAZADO, CodigoResultado.RECHAZADO
            with localcontext() as contexto:
                contexto.prec = 28
                monto = Decimal(unidades) / (Decimal(10) ** self.DECIMALES[solicitud.moneda])
            return ResultadoPago(estado, codigo, referencia, monto, solicitud.moneda)
        except (ValueError, TypeError, KeyError, AttributeError):
            return self._fallo(CodigoResultado.RESPUESTA_INVALIDA)

    def iniciar(self, solicitud):
        """Primera solicitud: clave estable. Recuperar incertidumbre mediante GET, no otro POST.

        Stripe puede depurar claves tras 24 horas; este adaptador no promete
        deduplicación indefinida ni decide volver a iniciar un pago indeterminado.
        """
        try:
            unidades = self._unidades(solicitud)
        except ValueError:
            return self._fallo(CodigoResultado.SOLICITUD_INVALIDA)
        if not self._configuracion_valida():
            return self._fallo(CodigoResultado.CONFIGURACION_INVALIDA)
        try:
            respuesta = self._cliente().v1.payment_intents.create(
                {
                    "amount": unidades, "currency": solicitud.moneda.lower(),
                    "metadata": self._metadata(solicitud), "confirm": True,
                    "capture_method": "automatic",
                    "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
                    "payment_method": self.METODOS_TEST[self._escenario],
                },
                options={"idempotency_key": f"ge:hu28:pago:{solicitud.pago_id}:create:v1"},
            )
            return self._normalizar(respuesta, solicitud, unidades)
        except stripe.CardError as error:
            cuerpo = error.json_body
            if isinstance(cuerpo, dict) and isinstance(cuerpo.get("error"), dict):
                intento = cuerpo["error"].get("payment_intent")
                if isinstance(intento, (dict, stripe.StripeObject)):
                    return self._normalizar(intento, solicitud, unidades)
            return self._fallo(CodigoResultado.RESULTADO_DESCONOCIDO)
        except (stripe.AuthenticationError, stripe.PermissionError):
            return self._fallo(CodigoResultado.ERROR_SIN_EJECUCION)
        except stripe.InvalidRequestError as error:
            if error.http_status in (400, 404) and error.code != "payment_intent_action_required":
                return self._fallo(CodigoResultado.ERROR_SIN_EJECUCION)
            return self._fallo(CodigoResultado.RESULTADO_DESCONOCIDO)
        except Exception:
            # Incluye conexión, timeout, 5xx, rate limit e idempotency_error.
            # No registrar ni devolver mensajes o cuerpos externos.
            return self._fallo(CodigoResultado.RESULTADO_DESCONOCIDO)

    def consultar(self, solicitud, referencia_externa):
        """Consulta normal por referencia persistida; nunca crea ni confirma un cobro."""
        try:
            unidades = self._unidades(solicitud)
        except ValueError:
            return self._fallo(CodigoResultado.SOLICITUD_INVALIDA, consulta=True)
        if not self._configuracion_valida():
            return self._fallo(CodigoResultado.CONFIGURACION_INVALIDA, consulta=True)
        if not self._referencia_valida(referencia_externa):
            return self._fallo(CodigoResultado.RESULTADO_DESCONOCIDO)
        try:
            respuesta = self._cliente().v1.payment_intents.retrieve(referencia_externa)
            return self._normalizar(respuesta, solicitud, unidades, referencia_externa)
        except Exception:
            return self._fallo(CodigoResultado.RESULTADO_DESCONOCIDO)

    def conciliar_sin_referencia(self, solicitud):
        """Recuperación excepcional por metadata; búsqueda eventualmente consistente.

        Cero o varios resultados conservan incertidumbre; jamás permiten recrear
        el cobro. Un único candidato se vuelve a consultar y validar por ID.
        """
        try:
            self._unidades(solicitud)
        except ValueError:
            return self._fallo(CodigoResultado.SOLICITUD_INVALIDA, consulta=True)
        if not self._configuracion_valida():
            return self._fallo(CodigoResultado.CONFIGURACION_INVALIDA, consulta=True)
        query = " AND ".join(f"metadata['{clave}']:'{valor}'" for clave, valor in self._metadata(solicitud).items())
        try:
            respuesta = self._datos(self._cliente().v1.payment_intents.search({"query": query, "limit": 2}))
            candidatos = respuesta.get("data")
            if respuesta.get("has_more") is not False or not isinstance(candidatos, list) or len(candidatos) != 1:
                return self._fallo(CodigoResultado.RESULTADO_DESCONOCIDO)
            referencia = self._datos(candidatos[0]).get("id")
            return self.consultar(solicitud, referencia)
        except Exception:
            return self._fallo(CodigoResultado.RESULTADO_DESCONOCIDO)
