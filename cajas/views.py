import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from usuarios.decorators import requiere_roles_web
from usuarios.services.keycloak import SESSION_ROLES, SESSION_USUARIO

from .forms import CajaForm, EstadoCajaForm
from .models import Caja
from .services import cambiar_estado_caja, crear_caja

logger = logging.getLogger(__name__)
ERROR_REGISTRO = "No fue posible registrar la caja. Intentá nuevamente."
ERROR_ESTADO = "No fue posible cambiar el estado de la caja. Intentá nuevamente."


def _identidad(request):
    """Obtiene la identidad y roles de la sesión verificada, nunca del formulario."""
    usuario = request.session.get(SESSION_USUARIO, {})
    return {"usuario_id": usuario.get("sub", ""), "roles": request.session.get(SESSION_ROLES, [])}


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def inicio(request):
    """Consulta el catálogo sin ofrecer operaciones futuras."""
    try:
        cajas = list(Caja.objects.all())
    except DatabaseError:
        logger.error("No fue posible consultar el catálogo de cajas.")
        return render(request, "frontend/cajas.html", {
            "cajas": [], "error": "No fue posible consultar las cajas. Intentá nuevamente.",
        }, status=500)
    return render(request, "frontend/cajas.html", {"cajas": cajas})


@requiere_roles_web("ADMINISTRADOR")
@require_http_methods(["GET", "POST"])
def crear(request):
    """Registra una caja con validaciones backend y CSRF."""
    formulario = CajaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        try:
            if not formulario.is_valid():
                return render(request, "frontend/caja_form.html", {"form": formulario}, status=400)
            usuario = request.session.get(SESSION_USUARIO, {})
            crear_caja(
                **formulario.cleaned_data,
                **_identidad(request),
                username=usuario.get("preferred_username", usuario.get("username", "")),
            )
        except ValidationError as error:
            formulario.add_error(None, " ".join(error.messages))
            return render(request, "frontend/caja_form.html", {"form": formulario}, status=400)
        except PermissionDenied:
            raise
        except Exception:
            # Frontera HTTP: los servicios propagan fallos y revierten su transacción.
            # No se muestran ni registran valores del formulario o detalles internos.
            logger.error("Error inesperado al registrar una caja.")
            return render(request, "frontend/caja_form.html", {
                "form": formulario, "error": ERROR_REGISTRO,
            }, status=500)
        else:
            messages.success(request, "Caja registrada correctamente.")
            return redirect("cajas:inicio")
    return render(request, "frontend/caja_form.html", {"form": formulario})


@requiere_roles_web("ADMINISTRADOR")
@require_POST
def cambiar_estado(request, caja_id):
    """Habilita o deshabilita una caja conservando su registro."""
    formulario = EstadoCajaForm(request.POST)
    if not formulario.is_valid():
        return render(request, "frontend/cajas.html", {
            "cajas": Caja.objects.all(), "error": "Estado de caja inválido.",
        }, status=400)
    try:
        cambiar_estado_caja(caja_id=caja_id, **formulario.cleaned_data, **_identidad(request))
    except Caja.DoesNotExist as error:
        raise Http404("La caja no existe.") from error
    except ValidationError as error:
        return render(request, "frontend/cajas.html", {
            "cajas": Caja.objects.all(), "error": " ".join(error.messages),
        }, status=400)
    except PermissionDenied:
        raise
    except Exception:
        logger.error("Error inesperado al cambiar la habilitación de una caja.")
        return render(request, "frontend/cajas.html", {
            "cajas": [], "error": ERROR_ESTADO,
        }, status=500)
    messages.success(request, "Estado de caja actualizado.")
    return redirect("cajas:inicio")
