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
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from jwt.exceptions import InvalidTokenError
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
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
        establecer_sesion_oidc(
            request,
            claims,
            refresh_token=tokens.get("refresh_token"),
            refresh_expires_in=tokens.get("refresh_expires_in"),
        )
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


@ensure_csrf_cookie
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
    "ADMINISTRADOR": "frontend/dashboard_administrador.html",
    "ANALISTA_CAMBIARIO": "frontend/dashboard_analista.html",
    "CAJERO": "frontend/dashboard_cajero.html",
    "USUARIO": "frontend/dashboard_usuario.html",
}

ROLES_PANEL_INFO = (
    {
        "codigo": "ADMINISTRADOR",
        "nombre": "Administrador",
        "descripcion": (
            "Gestiona usuarios, clientes y la configuración operativa "
            "habilitada para Global Exchange."
        ),
    },
    {
        "codigo": "CAJERO",
        "nombre": "Cajero / Operador",
        "descripcion": (
            "Atiende las operaciones de caja autorizadas cuando el módulo "
            "de cajas se encuentre disponible."
        ),
    },
    {
        "codigo": "ANALISTA_CAMBIARIO",
        "nombre": "Analista cambiario",
        "descripcion": (
            "Administra tasas comerciales y consulta información cambiaria "
            "según los permisos recibidos."
        ),
    },
    {
        "codigo": "USUARIO",
        "nombre": "Usuario",
        "descripcion": (
            "Consulta cotizaciones, realiza simulaciones y accede a las "
            "funciones habilitadas para sus clientes asociados."
        ),
    },
)


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
        "frontend/dashboard_usuario.html",
    )
    context = {"display_name": display_name}
    if "ADMINISTRADOR" in roles:
        from clientes.models import Cliente
        from metodos_pago.models import MetodoPago
        from monedas.models import Moneda

        context.update(
            clientes_count=Cliente.objects.count(),
            monedas_activas_count=Moneda.objects.activas().count(),
            metodos_pago_count=MetodoPago.objects.count(),
        )
    elif roles.intersection({"CAJERO", "ANALISTA_CAMBIARIO"}):
        from clientes.models import UsuarioCliente
        from monedas.models import Moneda
        from tasas.models import TasaComercial

        user_id = profile.get("sub", "")
        context.update(
            clientes_asociados_count=UsuarioCliente.objects.filter(
                keycloak_user_id=user_id,
                activo=True,
            ).count(),
            monedas_activas_count=Moneda.objects.activas().count(),
            tasas_comerciales_vigentes_count=TasaComercial.objects.filter(
                vigente=True
            ).count(),
        )
        if "ANALISTA_CAMBIARIO" in roles:
            from tasas.simulador import simular_conversion

            for codigo, context_key in (
                ("USD", "tasa_usd_pyg"),
                ("EUR", "tasa_eur_pyg"),
            ):
                try:
                    origen = Moneda.objects.get(codigo=codigo, estado="ACTIVA")
                    destino = Moneda.objects.get(codigo="PYG", estado="ACTIVA")
                    context[context_key] = simular_conversion(
                        moneda_origen_id=origen.id,
                        moneda_destino_id=destino.id,
                        monto="1",
                    )
                except (Moneda.DoesNotExist, ValidationError):
                    context[context_key] = None
    return render(request, template, context)


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def roles_permisos(request):
    """Muestra los roles de negocio configurados en el realm de Keycloak."""

    api_error = None
    roles_keycloak = set()
    try:
        respuesta = admin_request("/roles") or []
        roles_keycloak = {
            rol.get("name")
            for rol in respuesta
            if isinstance(rol, dict) and rol.get("name") in ROLES_NEGOCIO
        }
    except KeycloakError as exc:
        api_error = str(exc)

    roles = [
        {
            **rol,
            "configurado": rol["codigo"] in roles_keycloak,
        }
        for rol in ROLES_PANEL_INFO
    ]
    return render(
        request,
        "frontend/roles_permisos.html",
        {
            "roles_sistema": roles,
            "api_error": api_error,
        },
    )


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def usuarios(request):
    try:
        rows, error = admin_request("/users?max=100"), None
    except KeycloakError as exc:
        rows, error = [], str(exc)
    return render(
        request,
        "frontend/usuarios.html",
        {
            "users": rows,
            "api_error": error,
            "business_roles": list(ROLES_NEGOCIO),
        },
    )


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
                roles_directos = [
                    rol
                    for rol in request.POST.getlist("roles")
                    if rol != "USUARIO"
                ]
                if created and roles_directos:
                    actualizar_roles_usuario(created[0]["id"], roles_directos)
                messages.success(request, "Usuario creado con sus roles de negocio.")
                return redirect("usuarios:list")
            except KeycloakError as exc:
                messages.error(request, str(exc))
    form_values = {name: request.POST.get(name, "") for name in ("username", "first_name", "last_name", "email")}
    return render(request, "usuarios/user_form.html", {
        "mode": "create",
        "form_values": form_values,
        "business_roles": ROLES_NEGOCIO,
        "selected_roles": request.POST.getlist("roles"),
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
    return render(request, "frontend/monedas.html")


@requiere_roles_web(*ROLES_PANEL)
@require_GET
def tasas(request):
    return render(request, "frontend/tasas.html")


@requiere_roles_web("ADMINISTRADOR", "ANALISTA_CAMBIARIO")
@require_GET
def tasas_comerciales(request):
    return render(request, "frontend/tasas_comerciales.html")


@requiere_roles_web(*ROLES_PANEL)
@require_GET
def simulador(request):
    return render(request, "frontend/simulador.html")


@requiere_roles_web(*ROLES_PANEL)
@require_GET
def seguridad(request):
    """Explica las protecciones activas sin exponer detalles sensibles."""

    return render(request, "frontend/seguridad.html")


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def pagos(request):
    return render(request, "frontend/pagos.html")


def _json_body(request):
    """Decodifica el cuerpo JSON de una solicitud de API."""
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None


@requiere_rol("ADMINISTRADOR")
@require_POST
def crear_usuario_api(request):
    """Crea un usuario en Keycloak y aplica sus roles de negocio (JSON)."""

    datos = _json_body(request)
    if not isinstance(datos, dict):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud no contiene JSON válido."},
            status=400,
        )

    password = datos.get("password", "")
    username = str(datos.get("username", "")).strip()
    email = str(datos.get("email", "")).strip()

    if not username or not email or len(password) < 8:
        return JsonResponse(
            {
                "error": "Completá usuario, email y una contraseña de al menos 8 caracteres."
            },
            status=400,
        )

    roles = datos.get("roles") or []
    if not isinstance(roles, list):
        return JsonResponse(
            {"error": "El campo roles debe ser una lista."},
            status=400,
        )

    payload = {
        "username": username,
        "email": email,
        "firstName": str(datos.get("first_name", "")).strip(),
        "lastName": str(datos.get("last_name", "")).strip(),
        "enabled": True,
        "emailVerified": False,
        "credentials": [
            {"type": "password", "value": password, "temporary": True}
        ],
    }
    try:
        admin_request("/users", method="POST", payload=payload)
        query = urlencode({"username": username, "exact": "true"})
        created = admin_request(f"/users?{query}") or []
        roles_directos = [rol for rol in roles if rol != "USUARIO"]
        if created and roles_directos:
            actualizar_roles_usuario(created[0]["id"], roles_directos)
    except KeycloakError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {"message": "Usuario creado con sus roles de negocio."},
        status=201,
    )


@requiere_rol("ADMINISTRADOR")
@require_GET
def detalle_usuario_api(request, user_id):
    """Devuelve los datos del usuario y sus roles para el modal de edición."""

    try:
        user = cast(dict[str, object], admin_request(f"/users/{user_id}"))
        roles = roles_usuario(user_id)
    except KeycloakError:
        return JsonResponse(
            {"error": "El usuario no existe en Keycloak."},
            status=404,
        )

    return JsonResponse(
        {
            "username": user.get("username", ""),
            "first_name": user.get("firstName", ""),
            "last_name": user.get("lastName", ""),
            "email": user.get("email", ""),
            "enabled": bool(user.get("enabled", False)),
            "roles": roles,
        }
    )


@requiere_rol("ADMINISTRADOR")
@require_POST
def editar_usuario_api(request, user_id):
    """Actualiza datos, estado y roles de un usuario en Keycloak (JSON)."""

    datos = _json_body(request)
    if not isinstance(datos, dict):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud no contiene JSON válido."},
            status=400,
        )

    roles = datos.get("roles") or []
    if not isinstance(roles, list):
        return JsonResponse(
            {"error": "El campo roles debe ser una lista."},
            status=400,
        )

    try:
        user = cast(dict[str, object], admin_request(f"/users/{user_id}"))
    except KeycloakError:
        return JsonResponse(
            {"error": "El usuario no existe en Keycloak."},
            status=404,
        )

    user.update(
        {
            "email": str(datos.get("email", "")).strip(),
            "firstName": str(datos.get("first_name", "")).strip(),
            "lastName": str(datos.get("last_name", "")).strip(),
            "enabled": bool(datos.get("enabled", False)),
        }
    )
    try:
        admin_request(f"/users/{user_id}", method="PUT", payload=user)
        actualizar_roles_usuario(user_id, roles)
    except KeycloakError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({"message": "Usuario y roles actualizados."})


@requiere_rol("ADMINISTRADOR")
@require_POST
def baja_usuario_api(request, user_id):
    """Deshabilita un usuario en Keycloak conservando sus datos (JSON)."""

    try:
        user = cast(dict[str, object], admin_request(f"/users/{user_id}"))
    except KeycloakError:
        return JsonResponse(
            {"error": "El usuario no existe en Keycloak."},
            status=404,
        )

    user["enabled"] = False
    try:
        admin_request(f"/users/{user_id}", method="PUT", payload=user)
    except KeycloakError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {"message": "Usuario dado de baja; sus datos fueron conservados."}
    )
