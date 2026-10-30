"""Coordinacion persistente de una unica llamada a ``generar_de``."""

from dataclasses import dataclass
import hashlib
import json
import re

from django.db import IntegrityError, transaction

from facturacion.models import IntentoEmisionFacturaSegura

from .factura_segura import (
    FacturaSeguraAutenticacionError,
    FacturaSeguraConfiguracionError,
    FacturaSeguraProveedorError,
    FacturaSeguraRespuestaInvalida,
    FacturaSeguraResultadoIndeterminado,
    FacturaSeguraValidacionError,
    obtener_factura_segura_client,
)


CLAVE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{7,254}")


@dataclass(frozen=True)
class ResultadoEmision:
    intento: IntentoEmisionFacturaSegura
    reutilizado: bool


def _huella(documento):
    if not isinstance(documento, dict) or not documento:
        raise FacturaSeguraValidacionError("El DE calculado debe ser un objeto JSON no vacio.")
    try:
        canonico = json.dumps(documento, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as error:
        raise FacturaSeguraValidacionError("El DE calculado debe contener datos JSON validos.") from error
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _reservar(clave, huella):
    try:
        with transaction.atomic():
            return IntentoEmisionFacturaSegura.objects.create(
                clave_idempotencia=clave, huella_documento=huella,
            ), False
    except IntegrityError:
        intento = IntentoEmisionFacturaSegura.objects.get(clave_idempotencia=clave)
        if intento.huella_documento != huella:
            raise FacturaSeguraValidacionError(
                "La clave de idempotencia ya fue usada con otro documento."
            ) from None
        return intento, True


def generar_documento_una_vez(*, clave_idempotencia, de_calculado, client=None):
    """Reserva antes del IO y nunca repite una clave existente.

    ``INDETERMINADA`` y un ``EN_PROCESO`` abandonado requieren conciliacion
    administrativa o soporte del proveedor; esta funcion no los reemite.
    """
    if not isinstance(clave_idempotencia, str) or not CLAVE_RE.fullmatch(clave_idempotencia):
        raise FacturaSeguraValidacionError("La clave de idempotencia no es valida.")
    huella = _huella(de_calculado)
    intento, reutilizado = _reservar(clave_idempotencia, huella)
    if reutilizado:
        return ResultadoEmision(intento=intento, reutilizado=True)

    try:
        client = client or obtener_factura_segura_client()
        resultado = client.generar_de(de_calculado)
    except (FacturaSeguraResultadoIndeterminado, FacturaSeguraRespuestaInvalida):
        intento.estado = intento.Estado.INDETERMINADA
        intento.save(update_fields=["estado", "actualizado_en"])
        return ResultadoEmision(intento=intento, reutilizado=False)
    except FacturaSeguraProveedorError as error:
        intento.estado = intento.Estado.ERROR
        intento.codigo_proveedor = error.codigo
        intento.descripcion_proveedor = error.descripcion
        intento.operacion_id = error.operacion_id or ""
        intento.save(update_fields=[
            "estado", "codigo_proveedor", "descripcion_proveedor",
            "operacion_id", "actualizado_en",
        ])
        return ResultadoEmision(intento=intento, reutilizado=False)
    except (FacturaSeguraAutenticacionError, FacturaSeguraConfiguracionError):
        intento.estado = intento.Estado.ERROR
        intento.save(update_fields=["estado", "actualizado_en"])
        raise

    intento.estado = intento.Estado.GENERADA
    intento.cdc = resultado.cdc
    intento.operacion_id = resultado.operacion_id or ""
    intento.codigo_proveedor = resultado.codigo
    intento.descripcion_proveedor = resultado.descripcion
    intento.save(update_fields=[
        "estado", "cdc", "operacion_id", "codigo_proveedor",
        "descripcion_proveedor", "actualizado_en",
    ])
    return ResultadoEmision(intento=intento, reutilizado=False)
