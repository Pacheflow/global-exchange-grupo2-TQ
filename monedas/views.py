import json
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from usuarios.decorators import requiere_rol

from .forms import MonedaForm
from .models import Moneda


def _moneda_data(moneda):
    """Convierte una moneda en un diccionario para respuestas JSON.

    Filtro por estado: aspecto interno del backend JSON; se usa para
    serializar ``Moneda`` en las vistas de administración de la API.

    Args:
        moneda: instancia de ``Moneda`` con ``fecha_registro`` y
            ``fecha_actualizacion`` pobladas.

    Returns:
        dict con claves ``id``, ``codigo``, ``nombre``, ``simbolo``,
        ``estado``, ``fecha_registro`` y ``fecha_actualizacion`` — estas
        dos últimas en formato ISO 8601 vía ``isoformat()``.
    """

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
    """Expone únicamente los campos necesarios para consulta y simulación.

    Representación reducida usada por el catálogo público de monedas
    activas (no expone fechas internas de auditoría).

    Args:
        moneda: instancia de ``Moneda``.

    Returns:
        dict con claves ``id``, ``codigo``, ``nombre``, ``simbolo`` y
        ``estado``.
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
    """Devuelve todas las monedas configuradas (API de administración).

    Permisos: requiere rol ``ADMINISTRADOR`` (vía ``@requiere_rol``).
    Método: ``GET`` (``@require_GET``).

    Args:
        request: objeto ``HttpRequest`` con sesión autenticada de admin.

    Returns:
        ``JsonResponse`` 200 con clave ``monedas``: lista de dicts de
        ``_moneda_data`` para el total de ``Moneda.objects.all()``
        (incluye activas e inactivas, sin filtrar).
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

    Permisos: rol ``ADMINISTRADOR``. Método: ``POST`` (``@require_POST``).
    Flujo: parsea el ``JSON`` del cuerpo y valida con ``MonedaForm``; si un
    ``codigo`` duplicado (preexistente en la base) es detectado por el
    formulario, responde 409 "Ya existe una moneda con ese código." y por
    ``IntegrityError`` en ``save`` también responde 409 de forma directa.

    Args:
        request: objeto ``HttpRequest``; ``request.body`` debe ser JSON con
            ``codigo``, ``nombre`` y ``simbolo``.

    Returns:
        ``JsonResponse``: ``201`` con ``message`` "Moneda registrada
        correctamente." y la moneda vía ``_moneda_data`` si se creó; ``400``
        si el cuerpo no es JSON válido o los datos son inválidos (con
        ``detalles`` de ``form.errors.get_json_data()``); ``409`` si ya
        existe una moneda con ese ``codigo``; ``500`` si el guardado falla
        por otra excepción.
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

    Permisos: requiere rol ``ADMINISTRADOR`` (``@requiere_rol``) y método
    ``POST`` (``@require_POST``).

    Args:
        request: ``HttpRequest`` cuyo ``body`` debe ser JSON.
        moneda_id: id de la ``Moneda`` a editar.

    Returns:
        ``JsonResponse``:
            - ``200`` con ``message`` "Moneda actualizada correctamente."
              y la moneda vía ``_moneda_data``;
            - ``400`` si el ``body`` no es JSON válido o ``MonedaForm`` no
              valida (agregando ``detalles`` con ``form.errors``);
            - ``409`` si el ``codigo`` ya existe (duplicado) — debido al
              ``ValidationError`` de código ``duplicate`` **o** al
              ``IntegrityError`` al guardar;
            - ``500`` si ocurre cualquier otra excepción al guardar.

    Raises:
        Http404: si no existe una moneda con ``moneda_id``
            (vía ``get_object_or_404``).
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

    Permisos: requiere rol ``ADMINISTRADOR`` (``@requiere_rol``) y método
    ``POST`` (``@require_POST``).

    Args:
        request: ``HttpRequest`` con ``body`` JSON conteniendo ``estado``.
        moneda_id: id de la ``Moneda`` cuyo estado se desea cambiar.

    Returns:
        ``JsonResponse``:
            - ``200`` con ``message`` "Estado de la moneda actualizado
              correctamente." y la moneda vía ``_moneda_data``;
            - ``400`` si el ``body`` no es JSON válido o si ``estado`` no
              está entre ``{"ACTIVA", "INACTIVA"}``;
            - ``500`` si ocurre una excepción al guardar el cambio.

    Raises:
        Http404: si no existe una moneda con ``moneda_id``
            (vía ``get_object_or_404``).

    Notas:
        - La desactivación es una baja lógica (``estado="INACTIVA"``); no
          elimina la información histórica de la moneda.
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

    Permisos: **público** — sin requerir autenticación ni rol; ``@require_GET``.

    Args:
        request: ``HttpRequest`` de tipo ``GET``.

    Returns:
        ``JsonResponse`` con ``200`` y clave ``monedas``: lista de
        ``_moneda_publica_data`` para cada ``Moneda.objects.activas()``
        (solo las de estado ``ACTIVA``).
    """

    monedas = Moneda.objects.activas()

    return JsonResponse(
        {
            "monedas": [_moneda_publica_data(moneda) for moneda in monedas],
        },
        status=200,
    )
