import base64
import hashlib
import secrets
import time
import json
from typing import cast
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from jwt.exceptions import InvalidTokenError
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from .services.keycloak import asignar_rol_usuario
from .decorators import requiere_autenticacion, requiere_rol, requiere_roles_web
from .keycloak import (
    ROLES_NEGOCIO,
    KeycloakError,
    actualizar_roles_usuario,
    admin_request,
    roles_usuario,
)
from .services.keycloak import (
    SESSION_ROLES,
    SESSION_USUARIO,
    establecer_sesion_oidc,
    validar_access_token,
)

OIDC_FLOWS_SESSION_KEY = "oidc_flows"
FLUJO_LOGIN = "login"
FLUJO_REGISTRO = "registro"


def _iniciar_flujo_oidc(request, tipo_flujo, endpoint):
    """Crea una transacción OIDC independiente, vinculando state y PKCE."""

    ahora = int(time.time())
    flows = request.session.get(OIDC_FLOWS_SESSION_KEY, {})
    if not isinstance(flows, dict):
        flows = {}

    flows = {
        state: flow
        for state, flow in flows.items()
        if isinstance(flow, dict)
        and ahora - flow.get("creado_en", 0) <= settings.OIDC_FLOW_MAX_AGE_SECONDS
    }

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    flows[state] = {
        "code_verifier": code_verifier,
        "tipo_flujo": tipo_flujo,
        "creado_en": ahora,
    }
    request.session[OIDC_FLOWS_SESSION_KEY] = flows

    params = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": settings.OIDC_CALLBACK_URL,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    return redirect(f"{endpoint}?{urlencode(params)}")


def _consumir_flujo_oidc(request, state_recibido):
    """Valida state con comparación segura y consume el flujo una sola vez."""

    flows = request.session.get(OIDC_FLOWS_SESSION_KEY, {})
    if not state_recibido or not isinstance(flows, dict):
        request.session.pop(OIDC_FLOWS_SESSION_KEY, None)
        return None

    state_valido = next(
        (
            state_guardado
            for state_guardado in flows
            if secrets.compare_digest(state_guardado, state_recibido)
        ),
        None,
    )

    if state_valido is None:
        request.session.pop(OIDC_FLOWS_SESSION_KEY, None)
        return None

    flow = flows.pop(state_valido)
    if flows:
        request.session[OIDC_FLOWS_SESSION_KEY] = flows
    else:
        request.session.pop(OIDC_FLOWS_SESSION_KEY, None)

    if (
        not isinstance(flow, dict)
        or int(time.time()) - flow.get("creado_en", 0)
        > settings.OIDC_FLOW_MAX_AGE_SECONDS
    ):
        return None

    return flow


def _respuesta_error_oidc(mensaje, status):
    """Responde JSON o usa el destino de error fijo configurado por backend."""

    if settings.OIDC_ERROR_URL:
        separador = "&" if "?" in settings.OIDC_ERROR_URL else "?"
        return redirect(
            f"{settings.OIDC_ERROR_URL}{separador}"
            f"{urlencode({'error': 'authentication_failed'})}"
        )

    return JsonResponse({"error": mensaje}, status=status)


@require_GET
def registro(request):
    """
    Redirige al usuario al formulario de registro administrado por Keycloak.
    """

    registration_endpoint = (
        f"{settings.KEYCLOAK_PUBLIC_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/registrations"
    )
    return _iniciar_flujo_oidc(request, FLUJO_REGISTRO, registration_endpoint)


@require_GET
def login(request):
    """
    Inicia sesión utilizando Keycloak mediante Authorization Code Flow + PKCE.
    """

    authorization_endpoint = (
        f"{settings.KEYCLOAK_PUBLIC_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/auth"
    )
    return _iniciar_flujo_oidc(request, FLUJO_LOGIN, authorization_endpoint)


@require_GET
def callback(request):
    """
    Recibe la respuesta de Keycloak después del login.
    """

    state = request.GET.get("state")
    flow = _consumir_flujo_oidc(request, state)

    if flow is None:
        return _respuesta_error_oidc("State OIDC inválido o expirado", 400)

    if request.GET.get("error"):
        return _respuesta_error_oidc("Keycloak rechazó la autenticación", 400)

    code = request.GET.get("code")
    if not code:
        return _respuesta_error_oidc("No se recibió código de autorización", 400)

    token_endpoint = (
        f"{settings.KEYCLOAK_INTERNAL_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
    )

    code_verifier = flow.get("code_verifier")
    tipo_flujo = flow.get("tipo_flujo")
    if not code_verifier or tipo_flujo not in {FLUJO_LOGIN, FLUJO_REGISTRO}:
        return _respuesta_error_oidc(
            "No se encontró un flujo de autenticación válido", 400
        )

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "code": code,
        "redirect_uri": settings.OIDC_CALLBACK_URL,
        "code_verifier": code_verifier,
    }

    try:
        response = requests.post(
            token_endpoint,
            data=data,
            timeout=10,
        )
    except requests.RequestException:
        # SessionMiddleware no guarda sesiones para respuestas 5xx. Persistir
        # aquí garantiza que el state consumido no pueda reutilizarse.
        request.session.save()
        return _respuesta_error_oidc("Keycloak no está disponible", 502)

    if response.status_code != 200:
        return _respuesta_error_oidc("No se pudo autenticar con Keycloak", 400)

    try:
        tokens = response.json()
        claims = validar_access_token(tokens.get("access_token"))
        establecer_sesion_oidc(request, claims)
        id_token = tokens.get("id_token")
        if id_token:
            request.session["kc_id_token"] = id_token
    except (AttributeError, TypeError, ValueError, InvalidTokenError):
        return _respuesta_error_oidc("Keycloak devolvió un token inválido", 400)

    success_url = (
        settings.OIDC_REGISTRATION_SUCCESS_URL
        if tipo_flujo == FLUJO_REGISTRO
        else settings.OIDC_LOGIN_SUCCESS_URL
    )
    if success_url:
        return redirect(success_url)

    if "text/html" in request.headers.get("Accept", ""):
        return redirect("usuarios:dashboard")

    return JsonResponse(
        {
            "message": (
                "Registro y autenticación exitosos"
                if tipo_flujo == FLUJO_REGISTRO
                else "Login exitoso"
            ),
            "flujo": tipo_flujo,
            "usuario": request.session[SESSION_USUARIO],
            "roles": request.session[SESSION_ROLES],
        }
    )


@requiere_autenticacion
@require_GET
def perfil_usuario(request):
    """
    Devuelve la información del usuario autenticado y sus roles.
    """

    return JsonResponse(
        {
            "usuario": request.session[SESSION_USUARIO],
            "roles": request.session[SESSION_ROLES],
        }
    )


@requiere_rol("ADMINISTRADOR")
@require_GET
def acceso_administrador(request):
    """Vista mínima para comprobar autorización backend por rol."""

    return JsonResponse(
        {
            "message": "Acceso administrativo permitido",
            "usuario": request.session[SESSION_USUARIO],
        }
    )


@require_GET
def home(request):
    if request.session.get("kc_user"):
        return redirect("usuarios:dashboard")
    return render(request, "usuarios/home.html")


@require_GET
def logout(request):
    id_token = request.session.get("kc_id_token")
    request.session.flush()
    params = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "post_logout_redirect_uri": f"{settings.BACKEND_PUBLIC_URL}/",
    }
    if id_token:
        params["id_token_hint"] = id_token
    endpoint = (
        f"{settings.KEYCLOAK_PUBLIC_URL}/realms/{settings.KEYCLOAK_REALM}"
        "/protocol/openid-connect/logout"
    )
    return redirect(f"{endpoint}?{urlencode(params)}")


DASHBOARD_POR_ROL = {
    "ADMINISTRADOR": "figma/dashboard_administrador.html",
    "ANALISTA_CAMBIARIO": "figma/dashboard_analista.html",
    "CAJERO": "figma/dashboard_cajero.html",
    "USUARIO": "figma/dashboard_usuario.html",
}


@requiere_roles_web("ADMINISTRADOR", "CAJERO", "ANALISTA_CAMBIARIO", "USUARIO")
@require_GET
def dashboard(request):
    profile = request.session["kc_user"]
    display_name = (
        profile.get("given_name")
        or profile.get("name")
        or profile.get("preferred_username")
        or "Usuario"
    )
    roles = set(request.session.get("roles", []))
    template = next(
        (DASHBOARD_POR_ROL[rol] for rol in DASHBOARD_POR_ROL if rol in roles),
        "figma/dashboard_usuario.html",
    )
    return render(request, template, {"display_name": display_name})


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def usuarios(request):
    try:
        rows, error = admin_request("/users?max=100"), None
    except KeycloakError as exc:
        rows, error = [], str(exc)
    return render(request, "usuarios/user_list.html", {"users": rows, "api_error": error})


@requiere_roles_web("ADMINISTRADOR")
@require_http_methods(["GET", "POST"])
def crear_usuario(request):
    if request.method == "POST":
        password = request.POST.get("password", "")
        payload = {
            "username": request.POST.get("username", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "firstName": request.POST.get("first_name", "").strip(),
            "lastName": request.POST.get("last_name", "").strip(),
            "enabled": True,
            "emailVerified": False,
            "credentials": [{"type": "password", "value": password, "temporary": True}],
        }
        if not payload["username"] or not payload["email"] or len(password) < 8:
            messages.error(request, "Completá usuario, email y una contraseña de al menos 8 caracteres.")
        else:
            try:
                admin_request("/users", method="POST", payload=payload)
                query = urlencode({"username": payload["username"], "exact": "true"})
                created = admin_request(f"/users?{query}") or []
                if created:
                    actualizar_roles_usuario(created[0]["id"], request.POST.getlist("roles") or ["USUARIO"])
                messages.success(request, "Usuario creado con sus roles de negocio.")
                return redirect("usuarios:list")
            except KeycloakError as exc:
                messages.error(request, str(exc))
    form_values = {name: request.POST.get(name, "") for name in ("username", "first_name", "last_name", "email")}
    return render(request, "usuarios/user_form.html", {
        "mode": "create",
        "form_values": form_values,
        "business_roles": ROLES_NEGOCIO,
        "selected_roles": request.POST.getlist("roles") or ["USUARIO"],
    })


@requiere_roles_web("ADMINISTRADOR")
@require_http_methods(["GET", "POST"])
def editar_usuario(request, user_id):
    try:
        user = cast(dict[str, object], admin_request(f"/users/{user_id}"))
        if request.method == "POST":
            user.update({
                "email": request.POST.get("email", "").strip(),
                "firstName": request.POST.get("first_name", "").strip(),
                "lastName": request.POST.get("last_name", "").strip(),
                "enabled": request.POST.get("enabled") == "on",
            })
            admin_request(f"/users/{user_id}", method="PUT", payload=user)
            actualizar_roles_usuario(user_id, request.POST.getlist("roles"))
            messages.success(request, "Usuario y roles actualizados.")
            return redirect("usuarios:list")
        selected_roles = roles_usuario(user_id)
    except KeycloakError as exc:
        messages.error(request, str(exc))
        return redirect("usuarios:list")
    form_values = {
        "first_name": user.get("firstName", ""),
        "last_name": user.get("lastName", ""),
        "email": user.get("email", ""),
    }
    return render(request, "usuarios/user_form.html", {
        "mode": "edit",
        "managed_user": user,
        "form_values": form_values,
        "business_roles": ROLES_NEGOCIO,
        "selected_roles": selected_roles,
    })


@requiere_roles_web("ADMINISTRADOR")
@require_POST
def baja_usuario(request, user_id):
    if request.method == "POST":
        try:
            user = cast(dict[str, object], admin_request(f"/users/{user_id}"))
            user["enabled"] = False
            admin_request(f"/users/{user_id}", method="PUT", payload=user)
            messages.success(request, "Usuario dado de baja; sus datos fueron conservados.")
        except KeycloakError as exc:
            messages.error(request, str(exc))
    return redirect("usuarios:list")


@requiere_roles_web("ADMINISTRADOR", "CAJERO", "ANALISTA_CAMBIARIO", "USUARIO")
@require_GET
def clientes(request):
    return redirect("consultar_clientes")


@require_POST
@requiere_rol("ADMINISTRADOR")
def asignar_rol(request):
    """Asigna un rol de sistema a un usuario existente en Keycloak."""

    try:
        datos = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "El cuerpo de la solicitud no contiene JSON válido."},
            status=400,
        )

    usuario_id = datos.get("usuario_id")
    rol = datos.get("rol")

    if not usuario_id or not rol:
        return JsonResponse(
            {"error": "Los campos usuario_id y rol son obligatorios."},
            status=400,
        )

    try:
        asignar_rol_usuario(usuario_id, rol)
    except ValueError as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400,
        )
    except requests.RequestException:
        return JsonResponse(
            {"error": "No fue posible completar la operación en Keycloak."},
            status=502,
        )

    return JsonResponse(
        {
            "message": "Rol asignado correctamente.",
            "usuario_id": usuario_id,
            "rol": rol,
        },
        status=200,
    )


ROLES_PANEL = ("ADMINISTRADOR", "CAJERO", "ANALISTA_CAMBIARIO", "USUARIO")


@requiere_roles_web(*ROLES_PANEL)
@require_GET
def monedas(request):
    return render(request, "figma/monedas.html")


@requiere_roles_web(*ROLES_PANEL)
@require_GET
def tasas(request):
    return render(request, "figma/tasas.html")


@requiere_roles_web("ADMINISTRADOR", "ANALISTA_CAMBIARIO")
@require_GET
def tasas_comerciales(request):
    return render(request, "figma/tasas_comerciales.html")


@requiere_roles_web(*ROLES_PANEL)
@require_GET
def simulador(request):
    return render(request, "figma/simulador.html")


@requiere_roles_web(*ROLES_PANEL)
@require_GET
def pagos(request):
    return render(request, "figma/pagos.html")
