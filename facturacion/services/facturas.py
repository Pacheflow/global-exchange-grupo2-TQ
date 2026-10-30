"""Dominio HU-29/HU-30. Toda llamada externa ocurre fuera de atomic()."""
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from operaciones.models import Transaccion
from facturacion.models import Factura, IntentoEmisionFacturaSegura
from .emision import generar_documento_una_vez
from .factura_segura import FacturaSeguraError, obtener_factura_segura_client

logger = logging.getLogger(__name__)


def facturas_del_usuario(usuario_id):
    """La asociación activa es necesaria aun con una URL o ID conocidos."""
    if not isinstance(usuario_id, str) or not usuario_id.strip():
        raise PermissionDenied("Se requiere una identidad válida.")
    return Factura.objects.filter(
        transaccion__cliente__usuarios_asignados__keycloak_user_id=usuario_id,
        transaccion__cliente__usuarios_asignados__activo=True,
    ).select_related("transaccion__cliente")


def _datos_operacion(op):
    """Snapshot comercial: no asigna impuestos ni inventa un DE fiscal."""
    return {
        "transaccion_id": op.pk, "cliente_id": op.cliente_id,
        "cliente": op.cliente.nombre_razon_social, "documento": op.cliente.documento,
        "tipo_persona": op.cliente.tipo_persona, "tipo": op.tipo,
        "ruc": op.cliente.ruc, "dv": op.cliente.dv,
        "correo_facturacion": op.cliente.correo_facturacion,
        "moneda_origen": op.moneda_origen.codigo, "moneda_destino": op.moneda_destino.codigo,
        "monto_origen": str(op.monto_origen), "monto_destino": str(op.monto_destino),
        "tasa_aplicada": str(op.tasa_aplicada), "importe_comision": str(op.importe_comision),
        "porcentaje_comision": str(op.porcentaje_comision),
    }


def preparar_factura(transaccion_id):
    """Una única factura local por transacción completada, sin IO externo."""
    op = Transaccion.objects.select_related("cliente", "moneda_origen", "moneda_destino").get(pk=transaccion_id)
    if op.estado != "COMPLETADA":
        raise ValidationError("La transacción debe estar completada.")
    factura, _ = Factura.objects.get_or_create(transaccion=op, defaults={"datos_operacion": _datos_operacion(op)})
    return factura


def preparar_despues_de_commit(transaccion_id):
    """Un fallo de facturación nunca revierte la liquidación confirmada.

    El comando procesar_facturas recupera eventos que no pudieron prepararse.
    """
    try:
        preparar_factura(transaccion_id)
    except Exception:
        logger.error("FACTURA_PREPARACION_FALLIDA transaccion=%s", transaccion_id)


def emitir_factura(factura_id, *, contrato=None, client=None):
    """Usa un contrato fiscal explícito; nunca acepta documentos del navegador.

    contrato.construir_de(snapshot) y contrato.extraer_de_calculado(resultado)
    deben implementarse al recibir el esquema real del emisor. Sin contrato,
    queda PENDIENTE y no se contacta al proveedor.
    """
    with transaction.atomic():
        factura = Factura.objects.select_for_update().select_related("transaccion").get(pk=factura_id)
        if factura.estado != Factura.Estado.PENDIENTE:
            return factura
        if factura.transaccion.estado != "COMPLETADA":
            raise ValidationError("La transacción debe estar completada.")
        ruta = getattr(settings, "FACTURACION_CONTRATO", "")
        if contrato is None and not ruta:
            factura.codigo_error = "CONTRATO_FISCAL_PENDIENTE"
            factura.save(update_fields=["codigo_error", "actualizada_en"])
            return factura
        factura.estado = Factura.Estado.EN_PROCESO
        factura.codigo_error = ""
        factura.save(update_fields=["estado", "codigo_error", "actualizada_en"])
    try:
        contrato = contrato or import_string(ruta)()
        client = client or obtener_factura_segura_client()
        de = contrato.construir_de(factura.datos_operacion.copy())
        calculo = client.calcular_de(de)
        calculado = contrato.extraer_de_calculado(calculo)
        resultado = generar_documento_una_vez(
            clave_idempotencia=f"factura:transaccion:{factura.transaccion_id}:v1",
            de_calculado=calculado, client=client,
        )
        intento = resultado.intento
        factura.intento = intento
        factura.estado = intento.estado
        factura.cdc = intento.cdc
        if intento.estado == "GENERADA":
            factura.generada_en = timezone.now()
        else:
            factura.codigo_error = "EMISION_" + intento.estado
    except Exception as error:
        # Recuperar evidencia si el adaptador reservó antes de fallar. No
        # reemitir automáticamente un intento ya existente ni registrar secretos.
        intento = IntentoEmisionFacturaSegura.objects.filter(
            clave_idempotencia=f"factura:transaccion:{factura.transaccion_id}:v1"
        ).first()
        factura.intento = intento
        if intento and intento.estado == "GENERADA":
            factura.estado = Factura.Estado.GENERADA
            factura.cdc = intento.cdc
            factura.generada_en = timezone.now()
        elif intento and intento.estado != "ERROR":
            factura.estado = Factura.Estado.INDETERMINADA
        else:
            factura.estado = Factura.Estado.ERROR
        factura.codigo_error = type(error).__name__ if isinstance(error, FacturaSeguraError) else "EMISION_FALLIDA"
        logger.error("FACTURA_EMISION_FALLIDA factura=%s codigo=%s", factura.pk, factura.codigo_error)
    factura.save(update_fields=["estado", "intento", "cdc", "codigo_error", "generada_en", "actualizada_en"])
    return factura


def obtener_comprobante(factura, *, formato="pdf", client=None):
    """Descarga solo comprobantes generados. El llamador valida autorización."""
    if factura.estado != Factura.Estado.GENERADA or not factura.cdc:
        raise ValidationError("El comprobante todavía no está disponible.")
    if formato not in {"pdf", "xml"}:
        raise ValidationError("Formato de comprobante no válido.")
    client = client or obtener_factura_segura_client()
    return client.descargar_kude(factura.cdc) if formato == "pdf" else client.descargar_xml(factura.cdc)
