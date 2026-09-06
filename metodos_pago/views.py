from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from usuarios.decorators import requiere_roles_web

from .forms import MetodoPagoForm
from .models import MetodoPago


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def inicio_metodos_pago(request):
    """
    Muestra la página principal del módulo de métodos de pago.

    Presenta los métodos de pago configurados en el sistema.
    """
    metodos = MetodoPago.objects.select_related("cliente").all()

    return render(
        request,
        "metodos_pago/inicio.html",
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
    if request.method == "POST":
        form = MetodoPagoForm(request.POST)

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
                messages.success(
                    request,
                    f"Método de pago {metodo.nombre} registrado correctamente.",
                )

                return redirect("metodos_pago:consultar_metodos_pago")
    else:
        form = MetodoPagoForm()

    return render(
        request,
        "metodos_pago/registrar.html",
        {
            "form": form,
        },
    )


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def consultar_metodos_pago(request):
    """
    Lista los métodos de pago configurados.

    Los registros se consultan junto con su cliente para evitar
    consultas adicionales innecesarias a la base de datos.
    """
    metodos = MetodoPago.objects.select_related("cliente").all()

    return render(
        request,
        "metodos_pago/consultar.html",
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

    if request.method == "POST":
        form = MetodoPagoForm(
            request.POST,
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
                messages.success(
                    request,
                    "Método de pago actualizado correctamente.",
                )

                return redirect("metodos_pago:consultar_metodos_pago")
    else:
        form = MetodoPagoForm(
            instance=metodo,
        )

    return render(
        request,
        "metodos_pago/editar.html",
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

    if metodo.estado == "ACTIVO":
        metodo.desactivar()
        mensaje = "Método de pago desactivado correctamente."
    else:
        metodo.activar()
        mensaje = "Método de pago activado correctamente."

    messages.success(
        request,
        mensaje,
    )

    return redirect("metodos_pago:consultar_metodos_pago")
