"""API de pagos: identidad de sesión, entrada cerrada y respuestas persistidas."""

import json
from functools import wraps

from django.core.exceptions import PermissionDenied, RequestDataTooBig, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from usuarios.decorators import requiere_alguno_de_roles
from usuarios.services.keycloak import SESSION_ROLES, SESSION_USUARIO, rol_efectivo

from .factory import obtener_payment_provider
from .services import (
    PersistenciaPagoError, consultar_estado_pago, iniciar_pago,
    recuperar_pago, reintentar_pago,
)


def _error(mensaje, codigo, status):
    return JsonResponse({"error": mensaje, "codigo": codigo}, status=status)


def _no_disponible():
    return _error("La transacción solicitada no está disponible.", "TRANSACCION_NO_DISPONIBLE", 404)


def _errores_controlados(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except PermissionDenied:
            return _no_disponible()
        except ValidationError as error:
            if getattr(error, "code", None) == "OPERACION_INEXISTENTE":
                return _no_disponible()
            # No enviar messages/message_dict: pueden contener valores externos.
            return _error("La solicitud de pago no es válida para esta operación.", "SOLICITUD_PAGO_INVALIDA", 400)
        except PersistenciaPagoError:
            return _error(
                "No se pudo confirmar localmente el resultado del pago.",
                "PAGO_RECUPERACION_PENDIENTE", 503,
            )
        except Exception:
            # No registrar excepción, traceback, payload ni configuración.
            return _error("No se pudo procesar la solicitud de pago.", "ERROR_INTERNO", 500)
    return wrapper


def _contexto(request, *, permitir_sin_cliente=False):
    seleccionado = request.session.get("selected_client")
    cliente_id = seleccionado.get("id") if isinstance(seleccionado, dict) else None
    if permitir_sin_cliente and rol_efectivo(request.session.get(SESSION_ROLES, [])) == "CAJERO":
        cliente_id = None
    elif type(cliente_id) is not int or cliente_id <= 0:
        return None
    usuario = request.session.get(SESSION_USUARIO, {})
    return dict(
        usuario_id=usuario.get("sub"), roles=request.session.get(SESSION_ROLES, []),
        cliente_seleccionado_id=cliente_id,
    )


def _serializar(transaccion_id, resultado, *, post=False):
    if resultado is None:
        return JsonResponse(dict(
            transaccion_id=transaccion_id, pago_id=None, estado=None, codigo="PAGO_NO_INICIADO",
        ))
    datos = dict(
        transaccion_id=transaccion_id, pago_id=str(resultado.pago_id),
        estado=resultado.estado, codigo=resultado.codigo,
    )
    if post:
        datos["reutilizado"] = resultado.reutilizado
    return JsonResponse(datos)


def _ejecutar_post(request, transaccion_id, servicio):
    try:
        datos = json.loads(request.body) if request.body else {}
    except (ValueError, UnicodeDecodeError, RequestDataTooBig):
        return _error("El cuerpo debe estar vacío o contener un objeto JSON vacío.", "ENTRADA_INVALIDA", 400)
    if not isinstance(datos, dict) or datos:
        return _error("El cuerpo debe estar vacío o contener un objeto JSON vacío.", "ENTRADA_INVALIDA", 400)
    contexto = _contexto(request)
    if contexto is None:
        return _error("Seleccione un cliente válido para operar.", "CONTEXTO_CLIENTE_INVALIDO", 400)
    resultado = servicio(
        transaccion_id=transaccion_id, **contexto, provider=obtener_payment_provider(),
    )
    return _serializar(transaccion_id, resultado, post=True)


@transaction.non_atomic_requests
@never_cache
@_errores_controlados
@requiere_alguno_de_roles("USUARIO")
@require_POST
def iniciar(request, transaccion_id):
    return _ejecutar_post(request, transaccion_id, iniciar_pago)


@transaction.non_atomic_requests
@never_cache
@_errores_controlados
@requiere_alguno_de_roles("USUARIO")
@require_POST
def reintentar(request, transaccion_id):
    return _ejecutar_post(request, transaccion_id, reintentar_pago)


@transaction.non_atomic_requests
@never_cache
@_errores_controlados
@requiere_alguno_de_roles("CAJERO", "USUARIO")
@require_POST
def recuperar(request, transaccion_id):
    return _ejecutar_post(request, transaccion_id, recuperar_pago)


@transaction.non_atomic_requests
@never_cache
@_errores_controlados
@requiere_alguno_de_roles("CAJERO", "USUARIO")
@require_GET
def consultar(request, transaccion_id):
    contexto = _contexto(request, permitir_sin_cliente=True)
    if contexto is None:
        return _error("Seleccione un cliente válido para operar.", "CONTEXTO_CLIENTE_INVALIDO", 400)
    resultado = consultar_estado_pago(transaccion_id=transaccion_id, **contexto)
    return _serializar(transaccion_id, resultado)
