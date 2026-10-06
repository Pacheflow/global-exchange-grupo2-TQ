from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from usuarios.services.keycloak import rol_efectivo

from .forms import CajaForm, EstadoCajaForm
from .models import Caja


def _validar_administrador(roles, usuario_id):
    """Aplica la prioridad multirrol y exige identidad externa válida."""
    if rol_efectivo(roles) != "ADMINISTRADOR":
        raise PermissionDenied("Solo ADMINISTRADOR puede configurar cajas.")
    if not isinstance(usuario_id, str) or not usuario_id.strip():
        raise ValidationError("No se encontró una identidad Keycloak válida.")


def crear_caja(*, codigo, nombre, estado="HABILITADA", usuario_id, username="", roles):
    """Registra una caja normalizada con trazabilidad y unicidad en la BD."""
    _validar_administrador(roles, usuario_id)
    formulario = CajaForm({"codigo": codigo, "nombre": nombre, "estado": estado})
    if not formulario.is_valid():
        raise ValidationError(formulario.errors.as_data())
    caja = formulario.save(commit=False)
    caja.creado_por_keycloak_id = usuario_id.strip()
    caja.creado_por_username = username
    caja.actualizado_por_keycloak_id = usuario_id.strip()
    caja.full_clean()
    try:
        with transaction.atomic():
            caja.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == "caja_codigo_unico":
            raise ValidationError("Ya existe una caja con ese código.", code="duplicate") from error
        raise
    return caja


def cambiar_estado_caja(*, caja_id, estado, usuario_id, roles):
    """Cambia la habilitación bajo el bloqueo que compartirá HU-39.

    HU-39 añadirá la comprobación de período abierto antes de deshabilitar.
    """
    _validar_administrador(roles, usuario_id)
    formulario = EstadoCajaForm({"estado": estado})
    if not formulario.is_valid():
        raise ValidationError(formulario.errors.as_data())
    with transaction.atomic():
        caja = Caja.objects.select_for_update().get(pk=caja_id)
        caja.estado = formulario.cleaned_data["estado"]
        caja.actualizado_por_keycloak_id = usuario_id.strip()
        caja.save(update_fields=["estado", "actualizado_por_keycloak_id", "fecha_actualizacion"])
    return caja
