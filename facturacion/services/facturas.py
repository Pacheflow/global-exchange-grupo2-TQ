"""Dominio HU-29/HU-30. Toda llamada externa ocurre fuera de atomic()."""
import logging
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from operaciones.models import Transaccion
from tasas.models import TasaReferencia
from facturacion.models import Factura, IntentoEmisionFacturaSegura
from .emision import generar_documento_una_vez
from .factura_segura import (
    FacturaSeguraError,
    FacturaSeguraRespuestaInvalida,
    obtener_factura_segura_client,
)

logger = logging.getLogger(__name__)


def _decimal_texto(valor):
    texto = format(valor, "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def _conversion_comision_pyg(op):
    """Congela la conversión de la comisión a PYG para la factura.

    La tasa aplicada siempre expresa ``moneda_origen -> moneda_destino``. Si
    PYG no participa del par se utiliza una referencia vigente persistida; no
    se consulta un proveedor externo durante la facturación.
    """
    origen = op.moneda_origen.codigo
    destino = op.moneda_destino.codigo
    if destino == "PYG":
        tasa, fuente, fecha = Decimal("1"), "MONEDA_DESTINO_PYG", op.fecha_creacion
    elif origen == "PYG":
        tasa = Decimal("1") / op.tasa_aplicada
        fuente, fecha = "TASA_OPERACION_INVERSA", op.fecha_creacion
    else:
        vigentes = TasaReferencia.objects.filter(vigente_hasta__gte=timezone.now()).select_related(
            "moneda_base", "moneda_cotizada"
        )
        referencia = vigentes.filter(
            moneda_base=op.moneda_destino, moneda_cotizada__codigo="PYG"
        ).first()
        if referencia:
            tasa, fuente, fecha = referencia.valor, referencia.fuente, referencia.fecha_hora_fuente
        else:
            referencia = vigentes.filter(
                moneda_base__codigo="PYG", moneda_cotizada=op.moneda_destino
            ).first()
            if referencia:
                tasa = Decimal("1") / referencia.valor
                fuente, fecha = referencia.fuente, referencia.fecha_hora_fuente
            else:
                cotizada_destino = vigentes.filter(moneda_cotizada=op.moneda_destino).first()
                cotizada_pyg = None
                if cotizada_destino:
                    cotizada_pyg = vigentes.filter(
                        moneda_base=cotizada_destino.moneda_base,
                        moneda_cotizada__codigo="PYG",
                    ).first()
                if not cotizada_destino or not cotizada_pyg:
                    return {
                        "importe_comision_pyg": None, "tasa_conversion_pyg": None,
                        "fuente_conversion_pyg": "NO_DISPONIBLE", "fecha_conversion_pyg": None,
                    }
                tasa = cotizada_pyg.valor / cotizada_destino.valor
                fuente = f"{cotizada_destino.fuente}:{cotizada_destino.moneda_base.codigo}"
                fecha = min(cotizada_destino.fecha_hora_fuente, cotizada_pyg.fecha_hora_fuente)
    importe = (op.importe_comision * tasa).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return {
        "importe_comision_pyg": _decimal_texto(importe),
        "tasa_conversion_pyg": _decimal_texto(tasa),
        "fuente_conversion_pyg": fuente,
        "fecha_conversion_pyg": fecha.isoformat() if fecha else None,
    }


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
        "correo_facturacion": op.cliente.correo_facturacion,
        "tipo_persona": op.cliente.tipo_persona, "tipo": op.tipo,
        "canal": op.canal, "naturaleza_metodo": op.naturaleza_metodo,
        "moneda_origen": op.moneda_origen.codigo, "moneda_destino": op.moneda_destino.codigo,
        "monto_origen": str(op.monto_origen), "monto_destino": str(op.monto_destino),
        "tasa_aplicada": str(op.tasa_aplicada), "importe_comision": str(op.importe_comision),
        "porcentaje_comision": str(op.porcentaje_comision),
        **_conversion_comision_pyg(op),
    }


def preparar_factura(transaccion_id):
    """Una única factura local por transacción completada, sin IO externo."""
    op = Transaccion.objects.select_related("cliente", "moneda_origen", "moneda_destino").get(pk=transaccion_id)
    if op.estado != "COMPLETADA":
        raise ValidationError("La transacción debe estar completada.")
    factura, creada = Factura.objects.get_or_create(
        transaccion=op, defaults={"datos_operacion": _datos_operacion(op)}
    )
    # Compatibilidad con facturas PENDIENTE creadas antes del contrato fiscal.
    # Una factura ya procesada conserva su snapshot original sin mutaciones.
    if not creada and factura.estado == Factura.Estado.PENDIENTE and factura.intento_id is None:
        requeridos = {"correo_facturacion", "canal", "naturaleza_metodo"}
        if not requeridos <= set(factura.datos_operacion):
            factura.datos_operacion = _datos_operacion(op)
            factura.save(update_fields=["datos_operacion", "actualizada_en"])
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
        factura = Factura.objects.select_for_update().select_related(
            "transaccion__cliente", "transaccion__moneda_origen", "transaccion__moneda_destino"
        ).get(pk=factura_id)
        if factura.estado != Factura.Estado.PENDIENTE:
            return factura
        if factura.transaccion.estado != "COMPLETADA":
            raise ValidationError("La transacción debe estar completada.")
        if "importe_comision_pyg" not in factura.datos_operacion:
            factura.datos_operacion = _datos_operacion(factura.transaccion)
            factura.save(update_fields=["datos_operacion", "actualizada_en"])
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


def _campo_sifen(datos, nombre, maximo):
    valor = datos.get(nombre, "")
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise FacturaSeguraRespuestaInvalida("El estado de SIFEN tiene un formato inválido.")
    valor = valor.strip()
    if len(valor) > maximo or any(ord(c) < 32 and c not in "\r\n\t" for c in valor):
        raise FacturaSeguraRespuestaInvalida("El estado de SIFEN contiene texto inválido.")
    return valor


def actualizar_estado_sifen(factura_id, *, client=None):
    """Consulta y persiste el estado fiscal sin generar ni reenviar el DE."""
    factura = Factura.objects.get(pk=factura_id)
    if factura.estado != Factura.Estado.GENERADA or not factura.cdc:
        raise ValidationError("La factura todavía no posee un CDC consultable.")

    cdc = factura.cdc
    client = client or obtener_factura_segura_client()
    resultado = client.consultar_estado(cdc)
    if not resultado.resultados or not isinstance(resultado.resultados[0], dict):
        raise FacturaSeguraRespuestaInvalida("Factura Segura no devolvió el estado de SIFEN.")
    datos = resultado.resultados[0]
    estado = _campo_sifen(datos, "estado_sifen", 40)
    if not estado:
        raise FacturaSeguraRespuestaInvalida("Factura Segura no devolvió un estado de SIFEN.")
    descripcion = _campo_sifen(datos, "desc_sifen", 4000)
    error = _campo_sifen(datos, "error_sifen", 4000)
    fecha = _campo_sifen(datos, "fch_sifen", 40)

    with transaction.atomic():
        factura = Factura.objects.select_for_update().get(pk=factura_id)
        if factura.cdc != cdc:
            raise ValidationError("El CDC de la factura cambió durante la consulta.")
        factura.estado_sifen = estado
        factura.descripcion_sifen = descripcion
        factura.error_sifen = error
        factura.fecha_sifen = fecha
        factura.consultada_sifen_en = timezone.now()
        factura.save(update_fields=[
            "estado_sifen", "descripcion_sifen", "error_sifen",
            "fecha_sifen", "consultada_sifen_en", "actualizada_en",
        ])
    logger.info(
        "FACTURA_ESTADO_SIFEN_ACTUALIZADO factura=%s estado=%s",
        factura.pk,
        factura.estado_sifen,
    )
    return factura
