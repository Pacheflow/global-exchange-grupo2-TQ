"""Context processors para datos de sesión Keycloak en plantillas.

Expone los valores de la sesión de manera segura para que las plantillas no
dependan de lookups profundos sobre `request.session` que con DEBUG activo
provocan `VariableDoesNotExist` cuando una clave no existe (p. ej. un
visitante sin autenticación no tiene `kc_user`).

Este módulo solo LEE la sesión; no modifica la autenticación Keycloak, los
roles, los modelos ni la arquitectura del backend.
"""


def kc_user_context(request):
    profile = request.session.get("kc_user") or {}
    roles = request.session.get("roles") or []
    if not isinstance(roles, list):
        roles = list(roles)

    selected_client = request.session.get("selected_client")

    display_name = (
        profile.get("given_name")
        or profile.get("name")
        or profile.get("preferred_username")
        or "Usuario"
    )
    initial = display_name[:1].upper() or "U"
    email = profile.get("email") or ""

    return {
        "kc_user": profile,
        "kc_roles": roles,
        "selected_client": selected_client,
        "kc_display_name": display_name,
        "kc_initial": initial,
        "kc_email": email,
    }