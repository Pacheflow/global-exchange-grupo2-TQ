"""Consulta y descarga de facturas protegidas por sesión y asociación activa."""
from io import BytesIO
import logging

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from usuarios.decorators import requiere_roles_web
from usuarios.services.keycloak import SESSION_USUARIO
from .services.facturas import facturas_del_usuario, obtener_comprobante

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
    return render(request, "frontend/facturas.html", {
        "pagina": Paginator(facturas, 20).get_page(request.GET.get("page")),
    })


@never_cache
@requiere_roles_web("USUARIO")
@require_GET
def detalle(request, pk):
    factura = _factura(request, pk)
    return render(request, "frontend/factura_detalle.html", {"factura": factura})


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
