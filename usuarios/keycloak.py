"""Cliente mínimo OpenID Connect para el realm de Global Exchange."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class KeycloakError(Exception):
    """Error controlado al comunicarse con Keycloak."""


_admin_token_cache = {"access_token": None, "expires_at": 0}

ROLES_NEGOCIO = ("USUARIO", "CAJERO", "ANALISTA_CAMBIARIO", "ADMINISTRADOR")


def _error_detail(exc, fallback):
    """Extrae mensajes de error de Admin API y de OAuth/OpenID Connect."""
    try:
        payload = json.loads(exc.read())
    except (ValueError, AttributeError):
        return fallback
    return (payload.get("errorMessage") or payload.get("error_description")
            or payload.get("error") or fallback)


def endpoint(path="", *, internal=False):
    """Construye endpoints públicos para el navegador o internos para Django."""
    server_url = settings.KEYCLOAK_INTERNAL_URL if internal else settings.KEYCLOAK_SERVER_URL
    base = f"{server_url.rstrip('/')}/realms/{settings.KEYCLOAK_REALM}"
    return f"{base}{path}"


def _request(url, *, method="GET", data=None, token=None):
    """Ejecuta una petición con urlopen y devuelve el JSON de respuesta.

    Args:
        url (str): URL completa del endpoint de Keycloak.
        method (str): Método HTTP (GET, POST, PUT, DELETE). Por defecto GET.
        data (dict | None): Datos de formulario a enviar como ``x-www-form-urlencoded``.
        token (str | None): Access token opcional para la cabecera Authorization.

    Returns:
        dict | list | None: Carga JSON de la respuesta, o ``None`` si el
        cuerpo está vacío.

    Raises:
        KeycloakError: Si Keycloak rechaza la operación o no se puede conectar.
    """
    headers = {"Accept": "application/json"}
    body = urlencode(data).encode() if data is not None else None
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=8) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        raise KeycloakError(_error_detail(exc, "Keycloak rechazó la operación.")) from exc
    except URLError as exc:
        raise KeycloakError("No se pudo conectar con Keycloak. Verificá que esté iniciado.") from exc


def exchange_code(code, redirect_uri):
    """Intercambia un código de autorización por tokens OIDC.

    Args:
        code (str): Código de autorización devuelto por Keycloak.
        redirect_uri (str): URI de redirección registrada en el cliente.

    Returns:
        dict | None: Tokens de acceso y refresh emitidos por Keycloak.
    """
    return _request(endpoint("/protocol/openid-connect/token", internal=True), method="POST", data={
        "grant_type": "authorization_code", "client_id": settings.KEYCLOAK_CLIENT_ID,
        "code": code, "redirect_uri": redirect_uri,
    })


def userinfo(access_token):
    """Obtiene los datos del usuario autenticado desde el endpoint userinfo.

    Args:
        access_token (str): Access token emitido por Keycloak.

    Returns:
        dict | None: Reclamaciones de perfil del usuario autenticado.
    """
    return _request(endpoint("/protocol/openid-connect/userinfo", internal=True), token=access_token)


def admin_access_token():
    """Obtiene y reutiliza el token de la cuenta de servicio del backend."""
    now = time.monotonic()
    if _admin_token_cache["access_token"] and now < _admin_token_cache["expires_at"]:
        return _admin_token_cache["access_token"]

    tokens = _request(endpoint("/protocol/openid-connect/token", internal=True), method="POST", data={
        "grant_type": "client_credentials",
        "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
        "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
    })
    if not isinstance(tokens, dict):
        raise KeycloakError("Keycloak devolvió una respuesta de token inválida.")

    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise KeycloakError("Keycloak devolvió una respuesta de token inválida.")

    try:
        expires_in = int(tokens.get("expires_in", 60))
    except (TypeError, ValueError) as exc:
        raise KeycloakError(
            "Keycloak devolvió una respuesta de token inválida."
        ) from exc

    # Renovar con margen evita que el token venza durante una operación.
    _admin_token_cache.update({
        "access_token": access_token,
        "expires_at": now + max(expires_in - 30, 1),
    })
    return access_token


def admin_request(path, token=None, *, method="GET", payload=None):
    """Llama a Admin REST API con la cuenta de servicio del backend.

    ``token`` se conserva temporalmente en la firma para compatibilidad con
    llamadas existentes, pero los tokens de usuarios nunca autorizan acciones
    administrativas.
    """
    url = f"{settings.KEYCLOAK_INTERNAL_URL.rstrip('/')}/admin/realms/{settings.KEYCLOAK_REALM}{path}"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {admin_access_token()}"}
    body = json.dumps(payload).encode() if payload is not None else None
    if body:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=8) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        raise KeycloakError(_error_detail(exc, "No tenés permisos para administrar usuarios.")) from exc
    except URLError as exc:
        raise KeycloakError("No se pudo conectar con Keycloak.") from exc


def roles_usuario(user_id):
    """Lista los roles de negocio asignados directamente a un usuario."""

    mappings = admin_request(f"/users/{user_id}/role-mappings/realm") or []
    return sorted(
        role["name"]
        for role in mappings
        if isinstance(role, dict) and role.get("name") in ROLES_NEGOCIO
    )


def actualizar_roles_usuario(user_id, nuevos_roles):
    """Sincroniza exclusivamente los roles de negocio sin tocar roles internos."""

    nuevos = set(nuevos_roles).intersection(ROLES_NEGOCIO)
    actuales_payload = admin_request(f"/users/{user_id}/role-mappings/realm") or []
    actuales = {role["name"]: role for role in actuales_payload if role.get("name") in ROLES_NEGOCIO}

    quitar = [actuales[name] for name in actuales.keys() - nuevos]
    agregar = []
    for name in nuevos - actuales.keys():
        agregar.append(admin_request(f"/roles/{name}"))

    if quitar:
        admin_request(f"/users/{user_id}/role-mappings/realm", method="DELETE", payload=quitar)
    if agregar:
        admin_request(f"/users/{user_id}/role-mappings/realm", method="POST", payload=agregar)
