import json
from decimal import ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from clientes.models import Cliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from tasas.precision import normalizar_tasa
from usuarios.decorators import requiere_alguno_de_roles, requiere_roles_web
from usuarios.services.keycloak import SESSION_ROLES, SESSION_USUARIO, rol_efectivo

from .services import (
    PRECISION_MONTO,
    cancelar_transaccion,
    crear_transaccion,
    listar_transacciones,
    listar_metodos_pago_operacion,
    obtener_detalle_transaccion,
    previsualizar_operacion,
)

ROLES_OPERADORES = (
    "CAJERO",
    "USUARIO",
)
ROLES_HISTORIAL = ("ADMINISTRADOR", *ROLES_OPERADORES)


@requiere_roles_web(*ROLES_HISTORIAL)
@require_GET
def inicio_operaciones(request):
    """Presenta la interfaz de operaciones con catálogos activos.

    La consulta del cliente seleccionado respeta el mismo alcance que los
    servicios de operaciones. Las API vuelven a validar todos los datos al
    previsualizar, confirmar o cancelar una transacción.
    """

    es_supervisor = rol_efectivo(
        request.session.get(SESSION_ROLES, [])
    ) == "ADMINISTRADOR"
    cliente_operacion = None
    seleccion = request.session.get("selected_client", {})
    cliente_id = seleccion.get("id") if isinstance(seleccion, dict) else None

    if cliente_id and not es_supervisor:
        clientes = Cliente.objects.select_related(
            "categoria",
            "metodo_pago_preferido",
        ).filter(id=cliente_id, estado="ACTIVO")

        usuario_id, _ = _usuario_sesion(request)
        clientes = clientes.filter(
            usuarios_asignados__keycloak_user_id=usuario_id,
            usuarios_asignados__activo=True,
        )

        cliente_operacion = clientes.first()

    return render(
        request,
        "frontend/operaciones.html",
        {
            "cliente_operacion": cliente_operacion,
            "monedas_activas": Moneda.objects.activas() if not es_supervisor else (),
            "metodos_activos": MetodoPago.objects.activos() if not es_supervisor else (),
            "es_supervisor": es_supervisor,
        },
    )


def _usuario_sesion(request):
    """Devuelve la identidad Keycloak de la sesión o rechaza la solicitud.

    Args:
        request (HttpRequest): Solicitud HTTP.

    Returns:
        tuple: (usuario_id, usuario_username) cuando la sesión es válida,
        o (None, None) cuando no existe una identidad Keycloak.
    """

    usuario = request.session.get(SESSION_USUARIO, {})
    usuario_id = usuario.get("sub", "")
    if not usuario_id:
        return None, None
    return usuario_id, usuario.get("username", "")


def _leer_cuerpo_json(request):
    """Lee y valida el cuerpo JSON de una solicitud POST.

    Args:
        request (HttpRequest): Solicitud HTTP.

    Returns:
        dict | None: Objeto JSON válido o None cuando no es válido.
    """

    try:
        datos = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(datos, dict):
        return None

    return datos


def _cliente_seleccionado_id(request):
    """Obtiene el identificador del cliente seleccionado en la sesión.

    La selección facilita el contexto de navegación, pero los servicios de
    dominio vuelven a comprobar que el cliente exista, esté activo y resulte
    accesible para la identidad Keycloak.
    """

    seleccionado = request.session.get("selected_client", {})
    return seleccionado.get("id") if isinstance(seleccionado, dict) else None


def _detalles_error(error):
    """Convierte un ValidationError en detalles aptos para JSON.

    Args:
        error (ValidationError): Error de validación capturado.

    Returns:
        dict: Detalles del error por campo o mensaje general.
    """

    if hasattr(error, "message_dict") and error.message_dict:
        return error.message_dict
    return {"error": error.messages}


def _serializar_preview(resultado):
    """Convierte una previsualización en datos aptos para JSON."""

    return {
        "tipo": resultado.tipo,
        "cliente": {
            "id": resultado.cliente.id,
            "nombre_razon_social": resultado.cliente.nombre_razon_social,
        },
        "moneda_origen": {
            "id": resultado.moneda_origen.id,
            "codigo": resultado.moneda_origen.codigo,
        },
        "moneda_destino": {
            "id": resultado.moneda_destino.id,
            "codigo": resultado.moneda_destino.codigo,
        },
        "monto_origen": str(resultado.monto_origen),
        "tasa": str(resultado.tasa),
        "tasa_comercial": {
            "id": resultado.tasa_comercial.id,
            "version": resultado.tasa_comercial.version,
        },
        "monto_convertido": str(resultado.monto_convertido),
        "porcentaje_comision": str(resultado.porcentaje_comision),
        "categoria_preview_id": resultado.cliente.categoria_id,
        "importe_comision": str(resultado.importe_comision),
        "monto_destino": str(resultado.monto_destino),
        "metodo_pago": {
            "id": resultado.metodo_pago.id,
            "nombre": resultado.metodo_pago.nombre,
        },
    }


def _serializar_transaccion(transaccion):
    """Convierte una transacción en datos aptos para JSON.

    Utiliza los snapshots guardados; el monto convertido se deriva de los
    valores persistidos con la misma precisión de seis decimales usada al
    crear la operación, sin consultar la cotización actual.
    """

    monto_convertido = (transaccion.monto_origen * transaccion.tasa_aplicada).quantize(
        PRECISION_MONTO,
        rounding=ROUND_HALF_UP,
    )

    return {
        "id": transaccion.id,
        "clave_idempotencia": transaccion.clave_idempotencia,
        "tipo": transaccion.tipo,
        "cliente": {
            "id": transaccion.cliente.id,
            "nombre_razon_social": transaccion.cliente.nombre_razon_social,
            "categoria": (
                transaccion.cliente.categoria.nombre
                if transaccion.cliente.categoria_id
                else None
            ),
        },
        "moneda_origen": {
            "id": transaccion.moneda_origen.id,
            "codigo": transaccion.moneda_origen.codigo,
        },
        "moneda_destino": {
            "id": transaccion.moneda_destino.id,
            "codigo": transaccion.moneda_destino.codigo,
        },
        "monto_origen": str(transaccion.monto_origen),
        "monto_convertido": str(monto_convertido),
        "tasa_aplicada": str(normalizar_tasa(transaccion.tasa_aplicada)),
        "porcentaje_comision": str(transaccion.porcentaje_comision),
        "importe_comision": str(transaccion.importe_comision),
        "monto_destino": str(transaccion.monto_destino),
        "tasa_comercial": {
            "id": transaccion.tasa_comercial.id,
            "version": transaccion.tasa_comercial.version,
        },
        "metodo_pago": {
            "id": transaccion.metodo_pago.id,
            "nombre": transaccion.metodo_pago_nombre,
        },
        "estado": transaccion.estado,
        "creado_por": {
            "keycloak_id": transaccion.creado_por_keycloak_id,
            "username": transaccion.creado_por_username,
        },
        "fecha_creacion": transaccion.fecha_creacion.isoformat(),
        "fecha_actualizacion": transaccion.fecha_actualizacion.isoformat(),
        "cancelacion": {
            "cancelado_por_keycloak_id": transaccion.cancelado_por_keycloak_id,
            "cancelado_por_username": transaccion.cancelado_por_username,
            "cancelado_en": (
                transaccion.cancelado_en.isoformat()
                if transaccion.cancelado_en
                else None
            ),
            "motivo_cancelacion": transaccion.motivo_cancelacion,
        },
    }


@require_POST
@requiere_alguno_de_roles(*ROLES_OPERADORES)
def previsualizar_operacion_view(request):
    """Previsualiza una operación de cambio sin persistir nada (JSON)."""

    usuario_id, usuario_username = _usuario_sesion(request)
    if not usuario_id:
        return JsonResponse(
            {"error": "No se encontró una identidad Keycloak válida."},
            status=401,
        )

    datos = _leer_cuerpo_json(request)
    if datos is None:
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener un objeto JSON."},
            status=400,
        )

    try:
        resultado = previsualizar_operacion(
            usuario_id=usuario_id,
            usuario_username=usuario_username,
            cliente_id=datos.get("cliente_id"),
            tipo=datos.get("tipo"),
            moneda_origen_id=datos.get("moneda_origen_id"),
            moneda_destino_id=datos.get("moneda_destino_id"),
            monto=datos.get("monto"),
            metodo_pago_id=datos.get("metodo_pago_id"),
        )
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "No se pudo previsualizar la operación.",
                "detalles": _detalles_error(exc),
            },
            status=400,
        )

    return JsonResponse(_serializar_preview(resultado))


@require_POST
@requiere_alguno_de_roles(*ROLES_OPERADORES)
def crear_transaccion_view(request):
    """Confirma y persiste una operación de cambio (JSON).

    Revalida la versión de la tasa vigente contra la versión mostrada en
    la previsualización. Si cambió, rechaza la solicitud sin crear registros.
    """

    usuario_id, usuario_username = _usuario_sesion(request)
    if not usuario_id:
        return JsonResponse(
            {"error": "No se encontró una identidad Keycloak válida."},
            status=401,
        )

    datos = _leer_cuerpo_json(request)
    if datos is None:
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener un objeto JSON."},
            status=400,
        )

    try:
        resultado = crear_transaccion(
            usuario_id=usuario_id,
            usuario_username=usuario_username,
            cliente_id=datos.get("cliente_id"),
            tipo=datos.get("tipo"),
            moneda_origen_id=datos.get("moneda_origen_id"),
            moneda_destino_id=datos.get("moneda_destino_id"),
            monto=datos.get("monto"),
            metodo_pago_id=datos.get("metodo_pago_id"),
            clave_idempotencia=datos.get("clave_idempotencia"),
            version_preview=datos.get("version_preview"),
            tasa_preview=datos.get("tasa_preview"),
            categoria_preview_id=datos.get("categoria_preview_id"),
            porcentaje_comision_preview=datos.get("porcentaje_comision_preview"),
        )
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "No se pudo confirmar la operación.",
                "detalles": _detalles_error(exc),
            },
            status=400,
        )

    transaccion = resultado.transaccion
    payload = {
        "transaccion": _serializar_transaccion(transaccion),
        "repetida": resultado.repetida,
        "cambio_cotizacion": resultado.cambio_cotizacion,
    }

    return JsonResponse(
        payload,
        status=200 if resultado.repetida else 201,
    )


@require_POST
@requiere_alguno_de_roles(*ROLES_OPERADORES)
def cancelar_transaccion_view(request):
    """Cancela una transacción pendiente (JSON).

    La verificación se realiza en el servicio de dominio. La vista solo
    obtiene la identidad de sesión, lee los datos y devuelve la respuesta.
    """

    usuario_id, usuario_username = _usuario_sesion(request)
    if not usuario_id:
        return JsonResponse(
            {"error": "No se encontró una identidad Keycloak válida."},
            status=401,
        )

    datos = _leer_cuerpo_json(request)
    if datos is None:
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener un objeto JSON."},
            status=400,
        )

    try:
        transaccion_obj = cancelar_transaccion(
            transaccion_id=datos.get("transaccion_id"),
            usuario_id=usuario_id,
            usuario_username=usuario_username,
        )
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "No se pudo cancelar la transacción.",
                "detalles": _detalles_error(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "mensaje": "La transacción fue cancelada correctamente.",
            "transaccion": _serializar_transaccion(transaccion_obj),
        },
        status=200,
    )


@require_GET
@requiere_alguno_de_roles(*ROLES_OPERADORES)
def metodos_pago_operacion_view(request):
    """Lista métodos activos y el preferido válido del cliente seleccionado."""

    usuario_id, _ = _usuario_sesion(request)
    if not usuario_id:
        return JsonResponse(
            {"error": "No se encontró una identidad Keycloak válida."},
            status=401,
        )

    cliente_id = _cliente_seleccionado_id(request)
    if cliente_id is None:
        return JsonResponse(
            {"error": "Debe seleccionar un cliente para operar."},
            status=400,
        )

    try:
        cliente, metodos, preferido = listar_metodos_pago_operacion(
            usuario_id=usuario_id,
            cliente_id=cliente_id,
        )
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "No se pudieron consultar los métodos de pago.",
                "detalles": _detalles_error(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "cliente": {
                "id": cliente.id,
                "nombre_razon_social": cliente.nombre_razon_social,
            },
            "metodos_pago": [
                {"id": metodo.id, "nombre": metodo.nombre}
                for metodo in metodos
            ],
            "metodo_pago_preferido": (
                {"id": preferido.id, "nombre": preferido.nombre}
                if preferido
                else None
            ),
        }
    )


@require_GET
@requiere_alguno_de_roles(*ROLES_HISTORIAL)
def historial_transacciones_view(request):
    """Consulta el historial del cliente o el historial global administrativo."""

    usuario_id, _ = _usuario_sesion(request)
    if not usuario_id:
        return JsonResponse(
            {"error": "No se encontró una identidad Keycloak válida."},
            status=401,
        )

    es_admin = rol_efectivo(
        request.session.get(SESSION_ROLES, [])
    ) == "ADMINISTRADOR"
    cliente_id = None if es_admin else _cliente_seleccionado_id(request)
    if not es_admin and cliente_id is None:
        return JsonResponse(
            {"error": "Debe seleccionar un cliente para consultar su historial."},
            status=400,
        )

    try:
        transacciones = listar_transacciones(
            usuario_id=usuario_id,
            es_admin=es_admin,
            cliente_id=cliente_id,
        )
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "No se pudo consultar el historial.",
                "detalles": _detalles_error(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "transacciones": [
                _serializar_transaccion(transaccion)
                for transaccion in transacciones
            ]
        }
    )


@require_GET
@requiere_alguno_de_roles(*ROLES_HISTORIAL)
def detalle_transaccion_view(request, transaccion_id):
    """Devuelve el detalle histórico de una transacción autorizada (JSON)."""

    usuario_id, _ = _usuario_sesion(request)
    if not usuario_id:
        return JsonResponse(
            {"error": "No se encontró una identidad Keycloak válida."},
            status=401,
        )

    es_admin = rol_efectivo(
        request.session.get(SESSION_ROLES, [])
    ) == "ADMINISTRADOR"
    cliente_id = None if es_admin else _cliente_seleccionado_id(request)
    if not es_admin and cliente_id is None:
        return JsonResponse(
            {"error": "Debe seleccionar un cliente para consultar el detalle."},
            status=400,
        )

    try:
        transaccion = obtener_detalle_transaccion(
            transaccion_id=transaccion_id,
            usuario_id=usuario_id,
            cliente_id=cliente_id,
            es_admin=es_admin,
        )
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "La transacción solicitada no está disponible.",
                "detalles": _detalles_error(exc),
            },
            status=404,
        )

    return JsonResponse({"transaccion": _serializar_transaccion(transaccion)})
