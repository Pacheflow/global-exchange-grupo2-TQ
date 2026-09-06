import json
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from usuarios.decorators import requiere_rol

from .forms import MonedaForm
from .models import Moneda


def _moneda_data(moneda):
    """Convierte una moneda en un diccionario para respuestas JSON."""

    return {
        "id": moneda.id,
        "codigo": moneda.codigo,
        "nombre": moneda.nombre,
        "simbolo": moneda.simbolo,
        "estado": moneda.estado,
        "fecha_registro": moneda.fecha_registro.isoformat(),
        "fecha_actualizacion": moneda.fecha_actualizacion.isoformat(),
    }


@requiere_rol("ADMINISTRADOR")
@require_GET
def listar_monedas(request):
    """Devuelve todas las monedas configuradas."""

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
    """Registra una nueva moneda."""

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
    """Actualiza los datos permitidos de una moneda."""

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
    """Activa o desactiva una moneda sin eliminarla."""

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


@requiere_rol("ADMINISTRADOR")
@require_GET
def listar_monedas_activas(request):
    """Devuelve únicamente monedas disponibles para nuevas operaciones."""

    monedas = Moneda.objects.activas()

    return JsonResponse(
        {
            "monedas": [_moneda_data(moneda) for moneda in monedas],
        },
        status=200,
    )
