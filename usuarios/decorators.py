from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from .services.keycloak import (
    ROLES_SISTEMA,
    SESSION_ROLES,
    sesion_oidc_vigente,
)


def requiere_autenticacion(view_func):
    """Rechaza en backend solicitudes sin una sesión OIDC verificada."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not sesion_oidc_vigente(request):
            return JsonResponse(
                {"error": "Autenticación requerida"},
                status=401,
            )

        return view_func(request, *args, **kwargs)

    return wrapper


def requiere_rol(rol_requerido):
    """
    Verifica que el usuario autenticado tenga un rol específico.
    """

    if rol_requerido not in ROLES_SISTEMA:
        raise ValueError(f"Rol de sistema desconocido: {rol_requerido}")

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not sesion_oidc_vigente(request):
                return JsonResponse(
                    {"error": "Autenticación requerida"},
                    status=401,
                )

            roles = request.session.get(SESSION_ROLES, [])

            if rol_requerido not in roles:
                return JsonResponse(
                    {
                        "error": "Acceso denegado",
                        "rol_requerido": rol_requerido,
                    },
                    status=403,
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def requiere_alguno_de_roles(*roles_permitidos):
    """Protege una API cuando más de un rol puede consultar el recurso."""

    desconocidos = set(roles_permitidos) - ROLES_SISTEMA
    if desconocidos:
        raise ValueError(f"Roles de sistema desconocidos: {sorted(desconocidos)}")

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not sesion_oidc_vigente(request):
                return JsonResponse({"error": "Autenticación requerida"}, status=401)

            roles_usuario = set(request.session.get(SESSION_ROLES, []))
            if not roles_usuario.intersection(roles_permitidos):
                return JsonResponse(
                    {
                        "error": "Acceso denegado",
                        "roles_requeridos": roles_permitidos,
                    },
                    status=403,
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def requiere_roles_web(*roles_permitidos):
    """Protege vistas HTML y presenta respuestas apropiadas para navegador."""

    desconocidos = set(roles_permitidos) - ROLES_SISTEMA
    if desconocidos:
        raise ValueError(f"Roles de sistema desconocidos: {sorted(desconocidos)}")

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not sesion_oidc_vigente(request):
                request.session["next"] = request.get_full_path()
                messages.info(request, "Iniciá sesión para continuar.")
                return redirect("usuarios:login")
            roles_usuario = set(request.session.get(SESSION_ROLES, []))
            if not roles_usuario.intersection(roles_permitidos):
                return render(
                    request,
                    "usuarios/forbidden.html",
                    {"required_roles": roles_permitidos},
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
