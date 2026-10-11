"""Contrato de pagos independiente del SDK y de los estados de un proveedor."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class EstadoPago(StrEnum):
    EN_PROCESO = "EN_PROCESO"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    ERROR = "ERROR"
    INDETERMINADO = "INDETERMINADO"


class CodigoResultado(StrEnum):
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    EN_PROCESO = "EN_PROCESO"
    SOLICITUD_INVALIDA = "SOLICITUD_INVALIDA"
    CONFIGURACION_INVALIDA = "CONFIGURACION_INVALIDA"
    ERROR_SIN_EJECUCION = "ERROR_SIN_EJECUCION"
    RESULTADO_DESCONOCIDO = "RESULTADO_DESCONOCIDO"
    RESPUESTA_INVALIDA = "RESPUESTA_INVALIDA"


@dataclass(frozen=True)
class SolicitudPago:
    pago_id: UUID
    transaccion_id: int
    monto: Decimal
    moneda: str
    huella_solicitud: str


@dataclass(frozen=True)
class ResultadoPago:
    estado: EstadoPago
    codigo: CodigoResultado
    referencia_externa: str | None = None
    monto: Decimal | None = None
    moneda: str | None = None

    @property
    def mensaje(self):
        """Texto cerrado: nunca contiene mensajes ni payloads del proveedor."""
        return {
            CodigoResultado.APROBADO: "Pago aprobado.",
            CodigoResultado.RECHAZADO: "Pago rechazado.",
            CodigoResultado.EN_PROCESO: "Pago en procesamiento.",
            CodigoResultado.SOLICITUD_INVALIDA: "La solicitud de pago no es válida.",
            CodigoResultado.CONFIGURACION_INVALIDA: "El proveedor de prueba no está configurado correctamente.",
            CodigoResultado.ERROR_SIN_EJECUCION: "La solicitud no se pudo procesar.",
            CodigoResultado.RESULTADO_DESCONOCIDO: "El resultado debe verificarse antes de continuar.",
            CodigoResultado.RESPUESTA_INVALIDA: "No se pudo verificar la respuesta del proveedor.",
        }[self.codigo]


class PaymentProvider(Protocol):
    def iniciar(self, solicitud: SolicitudPago) -> ResultadoPago: ...

    def consultar(self, solicitud: SolicitudPago, referencia_externa: str) -> ResultadoPago: ...

    def conciliar_sin_referencia(self, solicitud: SolicitudPago) -> ResultadoPago: ...
