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

from .forms import AperturaCajaForm, ArqueoCajaForm, CajaForm, EstadoCajaForm, MovimientoCajaForm
from .models import ArqueoCaja, Caja, PeriodoCaja
from .presentacion import contexto_acciones_periodo
from .services import (
    abrir_caja,
    cambiar_estado_caja,
    cerrar_caja,
    consultar_historial_caja,
    consultar_saldos_caja,
    crear_caja,
    firmar_catalogo,
    leer_catalogo,
    realizar_arqueo,
    registrar_movimiento_manual,
)

logger = logging.getLogger(__name__)
ERROR_REGISTRO = "No fue posible registrar la caja. Intentá nuevamente."
ERROR_ESTADO = "No fue posible cambiar el estado de la caja. Intentá nuevamente."


def _identidad(request):
    """Obtiene la identidad y roles de la sesión verificada, nunca del formulario."""
    usuario = request.session.get(SESSION_USUARIO, {})
    return {"usuario_id": usuario.get("sub", ""), "roles": request.session.get(SESSION_ROLES, [])}


def _filas_cajas(cajas):
    """Añade el período abierto ya precargado a cada fila del catálogo."""
    return [
        {
            "caja": caja,
            "periodo_abierto": next(
                (periodo for periodo in caja.periodos.all() if periodo.estado == "ABIERTO"),
                None,
            ),
        }
        for caja in cajas
    ]


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def inicio(request):
    """Consulta el catálogo sin ofrecer operaciones futuras."""
    try:
        cajas = list(Caja.objects.prefetch_related("periodos").all())
        filas = _filas_cajas(cajas)
    except DatabaseError:
        logger.error("No fue posible consultar el catálogo de cajas.")
        return render(request, "frontend/cajas.html", {
            "cajas": [], "error": "No fue posible consultar las cajas. Intentá nuevamente.",
        }, status=500)
    return render(request, "frontend/cajas.html", {"cajas": cajas, "filas": filas})


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
        cajas = list(Caja.objects.prefetch_related("periodos").all())
        return render(request, "frontend/cajas.html", {
            "cajas": cajas, "filas": _filas_cajas(cajas),
            "error": "Estado de caja inválido.",
        }, status=400)
    try:
        cambiar_estado_caja(caja_id=caja_id, **formulario.cleaned_data, **_identidad(request))
    except Caja.DoesNotExist as error:
        raise Http404("La caja no existe.") from error
    except ValidationError as error:
        if getattr(error, "code", None) == "caja_abierta":
            messages.error(request, " ".join(error.messages))
            return redirect("cajas:inicio")
        cajas = list(Caja.objects.prefetch_related("periodos").all())
        return render(request, "frontend/cajas.html", {
            "cajas": cajas, "filas": _filas_cajas(cajas),
            "error": " ".join(error.messages),
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
    filas = _filas_cajas(cajas)
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


def _consulta_periodo(request, *, seccion):
    """Selección explícita de navegación, sin persistir una Caja activa."""
    candidatos = PeriodoCaja.objects.filter(
        estado="ABIERTO", caja__estado="HABILITADA",
    ).select_related("caja").order_by("caja__codigo", "pk")
    contexto = {
        "seccion": seccion, "periodos_disponibles": candidatos,
        "periodo": None, "saldos": [], "movimientos": [],
    }
    seleccion = request.GET.get("periodo_id")
    status = 200
    if seleccion is not None:
        if (not seleccion.isdecimal() or len(seleccion) > 10
                or int(seleccion) <= 0
                or not candidatos.filter(pk=int(seleccion)).exists()):
            contexto["error"] = "Seleccioná un período abierto de una caja habilitada."
            status = 400
        else:
            try:
                periodo, saldos = consultar_saldos_caja(
                    periodo_id=int(seleccion), **_identidad(request),
                )
                contexto.update(periodo=periodo, saldos=saldos)
                contexto.update(contexto_acciones_periodo(periodo))
                if seccion == "movimientos":
                    contexto["movimientos"] = periodo.movimientos.select_related("moneda").all()
            except (ValidationError, PeriodoCaja.DoesNotExist):
                contexto["error"] = "El período seleccionado ya no está disponible."
                status = 400
    return render(request, "frontend/caja_consulta.html", contexto, status=status)


@requiere_roles_web("ADMINISTRADOR", "CAJERO")
@require_GET
def saldos(request):
    return _consulta_periodo(request, seccion="saldos")


@requiere_roles_web("ADMINISTRADOR", "CAJERO")
@require_GET
def movimientos(request):
    return _consulta_periodo(request, seccion="movimientos")


@requiere_roles_web("ADMINISTRADOR", "CAJERO")
@require_GET
def saldo(request, periodo_id):
    """Muestra saldo por moneda y movimientos del período abierto."""

    try:
        periodo, saldos = consultar_saldos_caja(
            periodo_id=periodo_id,
            **_identidad(request),
        )
    except PeriodoCaja.DoesNotExist as error:
        raise Http404("El período no existe.") from error
    except PermissionDenied:
        raise
    except ValidationError as error:
        return render(
            request,
            "frontend/caja_saldo.html",
            {"periodo": None, "saldos": [], "movimientos": [], "error": " ".join(error.messages)},
            status=400,
        )

    movimientos = periodo.movimientos.select_related("moneda").all()
    return render(
        request,
        "frontend/caja_saldo.html",
        {"periodo": periodo, "saldos": saldos, "movimientos": movimientos,
         **contexto_acciones_periodo(periodo)},
    )


@requiere_roles_web("CAJERO")
@require_http_methods(["GET", "POST"])
def registrar_movimiento(request, periodo_id):
    """Registra un movimiento manual validado y vuelve al saldo de caja."""

    periodo = get_object_or_404(
        PeriodoCaja.objects.select_related("caja"),
        pk=periodo_id,
    )
    formulario = MovimientoCajaForm(
        periodo,
        request.POST if request.method == "POST" else None,
    )
    if request.method == "POST" and formulario.is_valid():
        usuario = request.session.get(SESSION_USUARIO, {})
        try:
            registrar_movimiento_manual(
                periodo_id=periodo.id,
                tipo=formulario.cleaned_data["tipo"],
                moneda_id=formulario.cleaned_data["moneda"].id,
                monto=formulario.cleaned_data["monto"],
                motivo=formulario.cleaned_data["motivo"],
                username=usuario.get("username", usuario.get("preferred_username", "")),
                **_identidad(request),
            )
        except PermissionDenied:
            raise
        except ValidationError as error:
            formulario.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Movimiento registrado correctamente.")
            return redirect("cajas:saldo", periodo_id=periodo.id)

    return render(
        request,
        "frontend/caja_movimiento_form.html",
        {"periodo": periodo, "form": formulario},
        status=400 if request.method == "POST" else 200,
    )
@requiere_roles_web("CAJERO")
@require_http_methods(["GET", "POST"])
def arqueo(request, periodo_id):
    """Permite al cajero realizar y guardar el arqueo de una caja abierta."""

    try:
        periodo, saldos = consultar_saldos_caja(
            periodo_id=periodo_id,
            **_identidad(request),
        )
    except PermissionDenied:
        raise
    except ValidationError as error:
        return render(
            request,
            "frontend/caja_arqueo.html",
            {
                "periodo": None,
                "saldos": [],
                "form": None,
                "error": " ".join(error.messages),
            },
            status=400,
        )

    formulario = ArqueoCajaForm(
        saldos,
        request.POST if request.method == "POST" else None,
    )

    if request.method == "POST" and formulario.is_valid():
        usuario = request.session.get(SESSION_USUARIO, {})

        try:
            realizar_arqueo(
                periodo_id=periodo.id,
                saldos_fisicos=formulario.saldos_fisicos(),
                observacion=formulario.cleaned_data["observacion"],
                username=usuario.get(
                    "username",
                    usuario.get("preferred_username", ""),
                ),
                **_identidad(request),
            )
        except PermissionDenied:
            raise
        except ValidationError as error:
            formulario.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Arqueo registrado correctamente.")
            return redirect("cajas:saldo", periodo_id=periodo.id)

    return render(
        request,
        "frontend/caja_arqueo.html",
        {
            "periodo": periodo,
            "saldos": saldos,
            "form": formulario,
        },
        status=400 if request.method == "POST" else 200,
    )
@requiere_roles_web("CAJERO")
@require_http_methods(["GET", "POST"])
def cierre(request, periodo_id):
    """Muestra un cierre elegible o informa el rechazo una sola vez mediante redirección a GET."""

    periodo = get_object_or_404(
        PeriodoCaja.objects.select_related("caja"),
        pk=periodo_id,
    )

    avisos = {
        "Debe realizarse un arqueo antes de cerrar la caja.":
            "Debes realizar un arqueo antes de cerrar la caja.",
        "Se registraron movimientos después del arqueo. Debe realizarse un nuevo arqueo antes de cerrar la caja.":
            "La caja tiene movimientos posteriores al último arqueo. Realiza un nuevo arqueo antes de cerrarla.",
    }

    if request.method == "POST":
        usuario = request.session.get(SESSION_USUARIO, {})
        try:
            cerrar_caja(
                periodo_id=periodo.id,
                username=usuario.get("username", usuario.get("preferred_username", "")),
                **_identidad(request),
            )
        except PermissionDenied:
            raise
        except ValidationError as error:
            motivo = " ".join(error.messages)
            messages.error(request, avisos.get(motivo, motivo))
            periodo.refresh_from_db(fields=["estado"])
            if periodo.estado == "ABIERTO":
                return redirect("cajas:saldo", periodo_id=periodo.pk)
            return redirect("cajas:historial", caja_id=periodo.caja_id)
        messages.success(request, "Caja cerrada correctamente.")
        return redirect("cajas:historial", caja_id=periodo.caja_id)

    if periodo.estado != "ABIERTO":
        return render(
            request,
            "frontend/caja_cierre.html",
            {
                "periodo": periodo,
                "arqueo": None,
                "error": "La caja debe encontrarse abierta para realizar el cierre.",
            },
            status=400,
        )

    arqueo = (
        ArqueoCaja.objects
        .filter(periodo=periodo)
        .prefetch_related("detalles__moneda")
        .order_by("-fecha_arqueo", "-id")
        .first()
    )

    if arqueo is None:
        messages.error(request, avisos["Debe realizarse un arqueo antes de cerrar la caja."])
        return redirect("cajas:saldo", periodo_id=periodo.pk)
    if periodo.movimientos.filter(fecha_registro__gt=arqueo.fecha_arqueo).exists():
        messages.error(request, avisos["Se registraron movimientos después del arqueo. Debe realizarse un nuevo arqueo antes de cerrar la caja."])
        return redirect("cajas:saldo", periodo_id=periodo.pk)

    return render(
        request,
        "frontend/caja_cierre.html",
        {
            "periodo": periodo,
            "arqueo": arqueo,
        },
    )
@requiere_roles_web("ADMINISTRADOR", "CAJERO")
@require_GET
def historial_selector(request):
    """Selecciona explícitamente una Caja, incluyendo cajas sin período abierto."""
    cajas = Caja.objects.order_by("codigo", "pk")
    seleccion = request.GET.get("caja_id")
    error = None
    if seleccion is not None:
        if (not seleccion.isdecimal() or len(seleccion) > 10
                or int(seleccion) <= 0 or not cajas.filter(pk=int(seleccion)).exists()):
            error = "Seleccioná una Caja válida para consultar su historial."
        else:
            return redirect("cajas:historial", caja_id=int(seleccion))
    return render(request, "frontend/caja_historial_selector.html", {
        "cajas": cajas, "error": error,
    }, status=400 if error else 200)


@requiere_roles_web("ADMINISTRADOR", "CAJERO")
@require_GET
def historial(request, caja_id):
    """Muestra el historial completo de períodos de una caja."""

    try:
        caja, periodos = consultar_historial_caja(
            caja_id=caja_id,
            **_identidad(request),
        )
    except PermissionDenied:
        raise
    except ValidationError as error:
        return render(
            request,
            "frontend/caja_historial.html",
            {
                "caja": None,
                "periodos": [],
                "error": " ".join(error.messages),
            },
            status=400,
        )

    return render(
        request,
        "frontend/caja_historial.html",
        {
            "caja": caja,
            "periodos": periodos,
        },
    )
