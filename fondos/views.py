import logging
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_http_methods
from usuarios.decorators import requiere_roles_web
from usuarios.services.keycloak import SESSION_USUARIO, SESSION_ROLES
from .forms import CargaForm
from .models import MovimientoFondo
from .services import consultar, cargar, autorizar_admin

logger = logging.getLogger(__name__)


def _identidad(request):
    """Lee exclusivamente identidad y roles de la sesión OIDC verificada."""
    return dict(usuario_id=request.session.get(SESSION_USUARIO, {}).get("sub"),
                roles=request.session.get(SESSION_ROLES, []))


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def inicio(request):
    """Presenta saldos administrativos; no crea fondos ni modifica saldos."""
    return render(request, "frontend/fondos.html", {"filas": consultar(**_identidad(request))})


@requiere_roles_web("ADMINISTRADOR")
@require_http_methods(["GET", "POST"])
def carga(request):
    """Carga mediante POST/CSRF y redirige para no reenviar al refrescar."""
    autorizar_admin(**_identidad(request))
    form = CargaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            cargar(moneda_id=form.cleaned_data["moneda"].pk, monto=form.cleaned_data["importe"],
                   motivo=form.cleaned_data["motivo"], clave=form.cleaned_data["clave"], **_identidad(request))
        except ValidationError as error:
            form.add_error(None, error)
        except DatabaseError:
            logger.error("CARGA_FONDOS_FALLIDA")
            form.add_error(None, "No se pudo registrar la carga. Conservá la solicitud para intentar nuevamente.")
        else:
            messages.success(request, "Carga de fondos registrada.")
            return redirect("fondos:inicio")
    return render(request, "frontend/fondos_cargar.html", {"form": form},
                  status=400 if request.method == "POST" and form.errors else 200)


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def movimientos(request):
    """Consulta trazabilidad de Fondos con autorización también en backend."""
    autorizar_admin(**_identidad(request))
    return render(request, "frontend/fondos_movimientos.html", {
        "movimientos": MovimientoFondo.objects.select_related("fondo__moneda", "operacion").all()})
