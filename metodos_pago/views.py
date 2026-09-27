import json

from django.contrib import messages
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from usuarios.decorators import requiere_roles_web

from .forms import MetodoPagoForm
from .models import MetodoPago


def _solicita_json(request):
    """Detecta las solicitudes realizadas por la pantalla Frontend."""

    return (
        request.content_type == "application/json"
        or "application/json" in request.headers.get("Accept", "")
    )


def _metodo_data(metodo):
    """Serializa una opción del catálogo global con sus campos persistidos."""

    return {
        "id": metodo.id,
        "nombre": metodo.nombre,
        "descripcion": metodo.descripcion,
        "activo": metodo.activo,
        "fecha_registro": metodo.fecha_registro.isoformat(),
        "fecha_actualizacion": metodo.fecha_actualizacion.isoformat(),
    }


def _datos_json(request):
    """Decodifica el cuerpo JSON y devuelve ``None`` cuando es inválido."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _respuesta_formulario_invalido(form):
    """Construye la respuesta JSON estándar para errores de formulario."""
    return JsonResponse(
        {
            "error": "Los datos del método de pago no son válidos.",
            "detalles": form.errors.get_json_data(),
        },
        status=400,
    )


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def inicio_metodos_pago(request):
    """
    Muestra la página principal del módulo de métodos de pago.

    Presenta los métodos de pago configurados en el sistema.
    """
    metodos = MetodoPago.objects.all()

    if _solicita_json(request):
        return JsonResponse(
            {"metodos": [_metodo_data(metodo) for metodo in metodos]}
        )

    return render(
        request,
        "frontend/pagos.html",
        {
            "metodos": metodos,
        },
    )


@requiere_roles_web("ADMINISTRADOR")
@require_http_methods(["GET", "POST"])
def registrar_metodo_pago(request):
    """
    Registra un nuevo método de pago.

    El formulario valida los datos antes de crear el registro.
    Si la validación es correcta, el método queda persistido
    en la base de datos.
    """
    respuesta_json = _solicita_json(request)
    if request.method == "POST":
        datos = _datos_json(request) if respuesta_json else request.POST
        if datos is None:
            return JsonResponse(
                {"error": "El cuerpo de la solicitud debe contener JSON válido."},
                status=400,
            )
        form = MetodoPagoForm(datos)

        if form.is_valid():
            try:
                metodo = form.save()
            except IntegrityError:
                form.add_error(
                    None,
                    "No fue posible guardar el método de pago. "
                    "Verifique los datos e intente nuevamente.",
                )
            except Exception:
                form.add_error(
                    None,
                    "No fue posible guardar el método de pago. "
                    "Intente nuevamente más tarde.",
                )
            else:
                if respuesta_json:
                    return JsonResponse(
                        {
                            "message": "Método de pago registrado correctamente.",
                            "metodo": _metodo_data(metodo),
                        },
                        status=201,
                    )
                messages.success(
                    request,
                    f"Método de pago {metodo.nombre} registrado correctamente.",
                )

                return redirect("metodos_pago:consultar_metodos_pago")
    else:
        form = MetodoPagoForm()

    if respuesta_json:
        return _respuesta_formulario_invalido(form)

    return render(
        request,
        "frontend/pagos.html",
        {
            "form": form,
        },
    )


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def consultar_metodos_pago(request):
    """
    Lista los métodos de pago configurados.

    El listado representa un catálogo único y no aplica filtros por cliente.
    """
    metodos = MetodoPago.objects.all()

    if _solicita_json(request):
        return JsonResponse(
            {"metodos": [_metodo_data(metodo) for metodo in metodos]}
        )

    return render(
        request,
        "frontend/pagos.html",
        {
            "metodos": metodos,
        },
    )


@requiere_roles_web("ADMINISTRADOR")
@require_http_methods(["GET", "POST"])
def editar_metodo_pago(request, metodo_id):
    """
    Permite modificar los datos de un método de pago existente.

    El registro actual se excluye automáticamente de la validación
    de duplicados realizada por MetodoPagoForm.
    """
    metodo = get_object_or_404(
        MetodoPago,
        id=metodo_id,
    )

    respuesta_json = _solicita_json(request)
    if request.method == "POST":
        datos = _datos_json(request) if respuesta_json else request.POST
        if datos is None:
            return JsonResponse(
                {"error": "El cuerpo de la solicitud debe contener JSON válido."},
                status=400,
            )
        form = MetodoPagoForm(
            datos,
            instance=metodo,
        )

        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error(
                    None,
                    "No fue posible actualizar el método de pago. "
                    "Verifique los datos e intente nuevamente.",
                )
            except Exception:
                form.add_error(
                    None,
                    "No fue posible actualizar el método de pago. "
                    "Intente nuevamente más tarde.",
                )
            else:
                if respuesta_json:
                    metodo.refresh_from_db()
                    return JsonResponse(
                        {
                            "message": "Método de pago actualizado correctamente.",
                            "metodo": _metodo_data(metodo),
                        }
                    )
                messages.success(
                    request,
                    "Método de pago actualizado correctamente.",
                )

                return redirect("metodos_pago:consultar_metodos_pago")
    else:
        form = MetodoPagoForm(
            instance=metodo,
        )

    if respuesta_json:
        return _respuesta_formulario_invalido(form)

    return render(
        request,
        "frontend/pagos.html",
        {
            "form": form,
            "metodo": metodo,
        },
    )


@requiere_roles_web("ADMINISTRADOR")
@require_POST
def cambiar_estado_metodo_pago(request, metodo_id):
    """
    Activa o desactiva un método de pago sin eliminarlo.

    La desactivación conserva el registro para mantener su información
    histórica y evitar la pérdida de datos.
    """
    metodo = get_object_or_404(
        MetodoPago,
        id=metodo_id,
    )

    if metodo.activo:
        metodo.desactivar()
        mensaje = "Método de pago desactivado correctamente."
    else:
        metodo.activar()
        mensaje = "Método de pago activado correctamente."

    messages.success(
        request,
        mensaje,
    )

    if _solicita_json(request):
        metodo.refresh_from_db()
        return JsonResponse(
            {
                "message": mensaje,
                "metodo": _metodo_data(metodo),
            }
        )

    return redirect("metodos_pago:consultar_metodos_pago")
