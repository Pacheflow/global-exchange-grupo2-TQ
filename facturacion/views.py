"""Consultas privadas y acciones POST protegidas por sesión, asociación y CSRF."""
from io import BytesIO
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from clientes.models import Cliente
from usuarios.decorators import requiere_roles_web
from usuarios.services.keycloak import SESSION_USUARIO
from .forms import CorreoFacturacionForm
from .services.facturas import facturas_del_usuario, autorizar_envio, enviar_factura, obtener_comprobante

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
    clientes = Cliente.objects.filter(usuarios_asignados__keycloak_user_id=_usuario(request),
                                     usuarios_asignados__activo=True, usuarios_asignados__rol_en_cliente="RESPONSABLE")
    return render(request, "frontend/facturas.html", {
        "pagina": Paginator(facturas, 20).get_page(request.GET.get("page")), "clientes": clientes,
    })


@never_cache
@requiere_roles_web("USUARIO")
@require_GET
def detalle(request, pk):
    factura = _factura(request, pk)
    asignaciones = factura.transaccion.cliente.usuarios_asignados.filter(keycloak_user_id=_usuario(request), activo=True)
    return render(request, "frontend/factura_detalle.html", {
        "factura": factura, "envio": factura.envios.first(),
        "puede_enviar": asignaciones.filter(rol_en_cliente__in=["RESPONSABLE", "OPERADOR"]).exists(),
        "puede_configurar_correo": asignaciones.filter(rol_en_cliente="RESPONSABLE").exists(),
    })


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


@never_cache
@requiere_roles_web("USUARIO")
@require_POST
def enviar(request, pk):
    factura = _factura(request, pk)
    autorizar_envio(factura, _usuario(request))
    try:
        envio = enviar_factura(factura.pk, reintentar=True)
    except ValidationError:
        messages.error(request, "La factura todavía no está disponible para enviar.")
    else:
        if envio.estado == "ENVIADO":
            messages.success(request, "La factura fue enviada al correo registrado del cliente.")
        elif envio.estado == "EN_PROCESO":
            messages.info(request, "Ya hay un envío en proceso.")
        else:
            messages.error(request, "No se pudo enviar. Revisá el correo del cliente e intentá nuevamente.")
    return redirect("facturacion:detalle", pk=pk)


@never_cache
@requiere_roles_web("USUARIO")
@require_http_methods(["GET", "POST"])
def correo_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id,
        usuarios_asignados__keycloak_user_id=_usuario(request), usuarios_asignados__activo=True,
        usuarios_asignados__rol_en_cliente="RESPONSABLE")
    form = CorreoFacturacionForm(request.POST if request.method == "POST" else None, instance=cliente)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Correo de facturación actualizado.")
        return redirect("facturacion:listado")
    return render(request, "frontend/factura_correo.html", {"form": form, "cliente": cliente},
                  status=400 if request.method == "POST" and form.errors else 200)
