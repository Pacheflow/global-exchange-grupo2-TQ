import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from usuarios.decorators import requiere_roles_web
from usuarios.services.keycloak import SESSION_ROLES, SESSION_USUARIO

from monedas.models import Moneda

from .forms import AperturaCajaForm, CajaForm, EstadoCajaForm
from .models import Caja, PeriodoCaja
from .services import abrir_caja, cambiar_estado_caja, crear_caja, firmar_catalogo, leer_catalogo

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
    """Cambia habilitación; el rechazo por período abierto redirige con aviso único."""
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
        if getattr(error, "code", None) == "caja_abierta":
            messages.error(request, " ".join(error.messages))
            return redirect("cajas:inicio")
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


@requiere_roles_web("CAJERO")
@require_GET
def operar(request):
    """Ofrece al cajero cajas habilitadas sin conceder configuración administrativa."""
    cajas = Caja.objects.habilitadas().prefetch_related("periodos")
    filas = [{"caja": caja, "abierta": any(p.estado == "ABIERTO" for p in caja.periodos.all())} for caja in cajas]
    return render(request, "frontend/cajas_operar.html", {"filas": filas})


def _formulario_actual(caja):
    """Captura una única consulta del catálogo y firma los pares mostrados."""
    monedas = list(Moneda.objects.activas())
    pares = sorted([[m.id, m.codigo] for m in monedas])
    return AperturaCajaForm(pares, initial={"catalogo": firmar_catalogo(caja.id, monedas)})


@requiere_roles_web("CAJERO")
@require_http_methods(["GET", "POST"])
def apertura(request, caja_id):
    """Captura, revisa y confirma la apertura; GET y revisión no escriben.

    Por acuerdo del proyecto, el rol efectivo CAJERO autoriza cualquier caja
    habilitada. La validación final y la identidad se imponen en el servicio.
    """
    caja = get_object_or_404(Caja, pk=caja_id)
    error = None
    confirmar = False
    estado_http = 200
    if request.method == "GET":
        formulario = _formulario_actual(caja)
    else:
        try:
            pares = leer_catalogo(caja.id, request.POST.get("catalogo", ""))
            formulario = AperturaCajaForm(pares, request.POST)
            if not formulario.is_valid():
                estado_http = 400
            elif not pares:
                error = "No hay monedas activas configuradas."
                estado_http = 400
            elif request.POST.get("accion") == "revisar":
                confirmar = True
            elif request.POST.get("accion") == "editar":
                confirmar = False
            elif request.POST.get("accion") == "confirmar":
                usuario = request.session.get(SESSION_USUARIO, {})
                periodo = abrir_caja(
                    caja_id=caja.id, catalogo=formulario.cleaned_data["catalogo"],
                    saldos=formulario.saldos(), **_identidad(request),
                    username=usuario.get("username", usuario.get("preferred_username", "")),
                )
                return redirect("cajas:apertura_confirmada", periodo_id=periodo.id)
            else:
                error = "Seleccioná revisar o confirmar la apertura."
                estado_http = 400
        except ValidationError as fallo:
            error = " ".join(fallo.messages)
            estado_http = 400
            if getattr(fallo, "code", None) in {"catalogo_invalido", "catalogo_cambiado"}:
                formulario = _formulario_actual(caja)
        except PermissionDenied:
            raise
        except Exception:
            logger.error("Error inesperado al abrir una caja.")
            error = "No fue posible abrir la caja. Intentá nuevamente."
            estado_http = 500
            # Se conserva el formulario cuando ya se pudo construir, sin repetir consultas.
            if "formulario" not in locals():
                formulario = AperturaCajaForm([])
    return render(request, "frontend/caja_apertura.html", {
        "caja": caja, "form": formulario, "error": error, "confirmar": confirmar,
        "sin_monedas": not formulario.pares,
    }, status=estado_http)


@requiere_roles_web("CAJERO")
@require_GET
def apertura_confirmada(request, periodo_id):
    """Muestra solo al responsable el período creado y sus saldos iniciales completos."""
    usuario_id = _identidad(request)["usuario_id"]
    periodo = get_object_or_404(
        PeriodoCaja.objects.select_related("caja").prefetch_related("saldos_iniciales__moneda"),
        pk=periodo_id, responsable_keycloak_id=usuario_id,
    )
    return render(request, "frontend/caja_apertura_confirmada.html", {"periodo": periodo})
