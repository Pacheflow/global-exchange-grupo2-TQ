import json
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from usuarios.decorators import requiere_rol

from .forms import MonedaForm
from .models import Moneda


def _moneda_data(moneda):
    """Serializa una moneda con sus fechas para las respuestas JSON de la API."""

    return {
        "id": moneda.id,
        "codigo": moneda.codigo,
        "nombre": moneda.nombre,
        "simbolo": moneda.simbolo,
        "estado": moneda.estado,
        "fecha_registro": moneda.fecha_registro.isoformat(),
        "fecha_actualizacion": moneda.fecha_actualizacion.isoformat(),
    }


def _moneda_publica_data(moneda):
    """Serializa una moneda con los campos mínimos del catálogo público.

    No expone las fechas internas de auditoría.
    """

    return {
        "id": moneda.id,
        "codigo": moneda.codigo,
        "nombre": moneda.nombre,
        "simbolo": moneda.simbolo,
        "estado": moneda.estado,
    }


@requiere_rol("ADMINISTRADOR")
@require_GET
def listar_monedas(request):
    """Devuelve todas las monedas configuradas, activas e inactivas.

    Solo disponible para el rol ADMINISTRADOR.
    """

    monedas = Moneda.objects.all()

    return JsonResponse(
        {
            "monedas": [_moneda_data(moneda) for moneda in monedas],
        },
        status=200,
    )


@requiere_rol("ADMINISTRADOR")
@require_POST
def crear_moneda(request):
    """Registra una nueva moneda vía la API JSON.

    Solo disponible para el rol ADMINISTRADOR. Un código duplicado se
    responde con estado 409.
    """

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener JSON válido."},
            status=400,
        )

    form = MonedaForm(datos)

    if not form.is_valid():
        errores_codigo = form.errors.get("codigo", [])

        if any(error.code == "duplicate" for error in errores_codigo.as_data()):
            return JsonResponse(
                {
                    "error": "Ya existe una moneda con ese código."
                },
                status=409,
            )

        return JsonResponse(
            {
                "error": "Los datos de la moneda no son válidos.",
                "detalles": form.errors.get_json_data(),
            },
            status=400,
        )
    try:
        moneda = form.save()
    except IntegrityError:
        return JsonResponse(
            {"error": "Ya existe una moneda con ese código."},
            status=409,
        )
    except Exception:
        return JsonResponse(
            {"error": "No fue posible guardar la moneda."},
            status=500,
        )

    return JsonResponse(
        {
            "message": "Moneda registrada correctamente.",
            "moneda": _moneda_data(moneda),
        },
        status=201,
    )


@requiere_rol("ADMINISTRADOR")
@require_POST
def editar_moneda(request, moneda_id):
    """Actualiza los datos permitidos de una moneda vía la API JSON.

    Solo disponible para el rol ADMINISTRADOR. Un código duplicado se
    responde con estado 409.
    """

    moneda = get_object_or_404(
        Moneda,
        id=moneda_id,
    )

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener JSON válido."},
            status=400,
        )

    form = MonedaForm(
        datos,
        instance=moneda,
    )

    if not form.is_valid():
        errores_codigo = form.errors.get("codigo", [])

        if any(error.code == "duplicate" for error in errores_codigo.as_data()):
            return JsonResponse(
                {
                    "error": "Ya existe una moneda con ese código."
                },
                status=409,
            )

        return JsonResponse(
            {
                "error": "Los datos de la moneda no son válidos.",
                "detalles": form.errors.get_json_data(),
            },
            status=400,
        )

    try:
        moneda = form.save()
    except IntegrityError:
        return JsonResponse(
            {"error": "Ya existe una moneda con ese código."},
            status=409,
        )
    except Exception:
        return JsonResponse(
            {"error": "No fue posible actualizar la moneda."},
            status=500,
        )

    return JsonResponse(
        {
            "message": "Moneda actualizada correctamente.",
            "moneda": _moneda_data(moneda),
        },
        status=200,
    )


@requiere_rol("ADMINISTRADOR")
@require_POST
def cambiar_estado_moneda(request, moneda_id):
    """Activa o desactiva una moneda existente sin eliminarla.

    Solo disponible para el rol ADMINISTRADOR. La desactivación es una
    baja lógica: el registro se conserva para no perder historial.
    """

    moneda = get_object_or_404(
        Moneda,
        id=moneda_id,
    )

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener JSON válido."},
            status=400,
        )

    estado = datos.get("estado")

    if estado not in {"ACTIVA", "INACTIVA"}:
        return JsonResponse(
            {"error": "El estado debe ser ACTIVA o INACTIVA."},
            status=400,
        )

    moneda.estado = estado

    try:
        moneda.save()
    except Exception:
        return JsonResponse(
            {"error": "No fue posible actualizar el estado de la moneda."},
            status=500,
        )

    return JsonResponse(
        {
            "message": "Estado de la moneda actualizado correctamente.",
            "moneda": _moneda_data(moneda),
        },
        status=200,
    )


@require_GET
def listar_monedas_activas(request):
    """Devuelve públicamente el catálogo activo usado por el conversor.

    Endpoint público: no requiere autenticación ni rol.
    """

    monedas = Moneda.objects.activas()

    return JsonResponse(
        {
            "monedas": [_moneda_publica_data(moneda) for moneda in monedas],
        },
        status=200,
    )
