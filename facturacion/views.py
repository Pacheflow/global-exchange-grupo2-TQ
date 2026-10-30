"""Consulta y descarga de facturas protegidas por sesión y asociación activa."""
from io import BytesIO
import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from usuarios.decorators import requiere_roles_web
from usuarios.services.keycloak import SESSION_USUARIO
from clientes.models import UsuarioCliente
from .services.factura_segura import FacturaSeguraError
from .services.facturas import (
    actualizar_estado_sifen,
    emitir_factura,
    facturas_del_usuario,
    obtener_comprobante,
)

logger = logging.getLogger(__name__)


def _usuario(request):
    return request.session.get(SESSION_USUARIO, {}).get("sub")


def _factura(request, pk):
    return get_object_or_404(facturas_del_usuario(_usuario(request)), pk=pk)


@never_cache
@requiere_roles_web("USUARIO")
@require_GET
def listado(request):
    facturas = facturas_del_usuario(_usuario(request))
    pagina = Paginator(facturas, 20).get_page(request.GET.get("page"))
    clientes_operables = set(
        UsuarioCliente.objects.filter(
            keycloak_user_id=_usuario(request), activo=True,
            rol_en_cliente__in=("RESPONSABLE", "OPERADOR"),
        ).values_list("cliente_id", flat=True)
    )
    for factura in pagina.object_list:
        factura.puede_procesar = factura.transaccion.cliente_id in clientes_operables
    return render(request, "frontend/facturas.html", {"pagina": pagina})


@never_cache
@requiere_roles_web("USUARIO")
@require_GET
def detalle(request, pk):
    factura = _factura(request, pk)
    return render(request, "frontend/factura_detalle.html", {"factura": factura})


@never_cache
@requiere_roles_web("USUARIO")
@require_POST
def procesar(request, pk):
    """Emite una factura pendiente autorizada mediante el contrato ESI TEST."""
    factura = _factura(request, pk)
    if not UsuarioCliente.objects.filter(
        cliente_id=factura.transaccion.cliente_id,
        keycloak_user_id=_usuario(request), activo=True,
        rol_en_cliente__in=("RESPONSABLE", "OPERADOR"),
    ).exists():
        raise PermissionDenied("El rol en el cliente permite solamente consultar facturas.")
    if factura.estado != factura.Estado.PENDIENTE:
        messages.info(request, "La factura ya fue procesada o requiere revisión.")
        return redirect("facturacion:detalle", pk=factura.pk)

    factura = emitir_factura(factura.pk)
    if factura.estado == factura.Estado.GENERADA:
        messages.success(request, "Factura generada correctamente.")
    elif factura.estado == factura.Estado.INDETERMINADA:
        messages.warning(
            request,
            "No se pudo confirmar el resultado. No vuelvas a emitirla hasta conciliar el intento.",
        )
    elif factura.estado == factura.Estado.ERROR:
        messages.error(request, "Factura Segura rechazó la emisión o no pudo procesarla.")
    else:
        messages.info(request, "La factura continúa pendiente de emisión.")
    return redirect("facturacion:detalle", pk=factura.pk)


@never_cache
@requiere_roles_web("USUARIO")
@require_POST
def actualizar_estado(request, pk):
    """Consulta get_estado_sifen para una factura visible, sin reemitirla."""
    factura = _factura(request, pk)
    try:
        factura = actualizar_estado_sifen(factura.pk)
    except (FacturaSeguraError, ValidationError) as error:
        logger.error(
            "FACTURA_ESTADO_SIFEN_FALLIDO factura=%s codigo=%s",
            factura.pk,
            type(error).__name__,
        )
        messages.error(request, "No se pudo actualizar el estado de SIFEN.")
    else:
        messages.success(request, f"Estado de SIFEN actualizado: {factura.estado_sifen}.")
    return redirect("facturacion:detalle", pk=factura.pk)


def _archivo(request, pk, formato, *, adjunto):
    factura = _factura(request, pk)
    try:
        archivo = obtener_comprobante(factura, formato=formato)
    except ValidationError:
        return HttpResponse("El comprobante o formato solicitado no está disponible.", status=409)
    except Exception:
        logger.error("FACTURA_DESCARGA_FALLIDA factura=%s", pk)
        return HttpResponse("No se pudo obtener el comprobante. Intentá nuevamente más tarde.", status=503)
    respuesta = FileResponse(BytesIO(archivo.contenido), as_attachment=adjunto,
                             filename=f"factura-{factura.transaccion_id}.{formato}", content_type=archivo.content_type)
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


@never_cache
@requiere_roles_web("USUARIO")
@require_GET
def visualizar(request, pk):
    return _archivo(request, pk, "pdf", adjunto=False)


@never_cache
@requiere_roles_web("USUARIO")
@require_GET
def descargar(request, pk, formato):
    return _archivo(request, pk, formato, adjunto=True)
