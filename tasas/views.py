import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from usuarios.decorators import (
    requiere_alguno_de_roles,
    requiere_autenticacion,
    requiere_rol,
)
from usuarios.services.keycloak import SESSION_USUARIO

from monedas.models import Moneda
from .models import TasaComercial
from .services import actualizar_tasa_comercial, consultar_tasas_referencia
from .simulador import simular_conversion


def _serializar_tasa_referencia(tasa, *, desactualizada):
    """Convierte una tasa externa persistida en datos aptos para JSON."""

    return {
        "id": tasa.id,
        "tipo": "REFERENCIA",
        "par": f"{tasa.moneda_base.codigo}/{tasa.moneda_cotizada.codigo}",
        "moneda_base": tasa.moneda_base.codigo,
        "moneda_cotizada": tasa.moneda_cotizada.codigo,
        "valor": str(tasa.valor),
        "fuente": tasa.fuente,
        "fecha_hora": tasa.fecha_hora_fuente.isoformat(),
        "vigente_hasta": tasa.vigente_hasta.isoformat(),
        "desactualizada": desactualizada,
    }


@requiere_autenticacion
@require_GET
def consultar_tasas(request):
    """Consulta tasas de referencia e informa su estado de frescura."""

    resultado = consultar_tasas_referencia()
    desactualizada = resultado.estado == "desactualizado"
    payload = {
        "estado": resultado.estado,
        "mensaje": resultado.mensaje,
        "tasas_referencia": [
            _serializar_tasa_referencia(
                tasa,
                desactualizada=desactualizada,
            )
            for tasa in resultado.tasas
        ],
        "tasas_comerciales": [],
    }

    return JsonResponse(
        payload,
        status=503 if resultado.estado == "indisponible" else 200,
    )


def _serializar_tasa(tasa):
    """Convierte una tasa comercial en datos aptos para JSON."""
    return {
        "id": tasa.id,
        "moneda_origen": {
            "id": tasa.moneda_origen.id,
            "codigo": tasa.moneda_origen.codigo,
        },
        "moneda_destino": {
            "id": tasa.moneda_destino.id,
            "codigo": tasa.moneda_destino.codigo,
        },
        "compra": str(tasa.compra),
        "venta": str(tasa.venta),
        "vigente": tasa.vigente,
        "version": tasa.version,
        "usuario_id": tasa.usuario_id,
        "usuario_username": tasa.usuario_username,
        "fecha_registro": tasa.fecha_registro.isoformat(),
    }


@require_POST
@requiere_rol("ANALISTA_CAMBIARIO")
def administrar_tasa_comercial(request):
    """
    Registra o modifica una tasa comercial.

    Cada modificación genera una nueva versión y conserva
    la versión anterior en el histórico.
    """
    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud no contiene JSON válido."},
            status=400,
        )

    moneda_origen_id = datos.get("moneda_origen_id")
    moneda_destino_id = datos.get("moneda_destino_id")

    if moneda_origen_id is None or moneda_destino_id is None:
        return JsonResponse(
            {
                "error": (
                    "Debe indicar la moneda de origen "
                    "y la moneda de destino."
                )
            },
            status=400,
        )

    usuario = request.session.get(SESSION_USUARIO, {})

    try:
        tasa = actualizar_tasa_comercial(
            moneda_origen_id=moneda_origen_id,
            moneda_destino_id=moneda_destino_id,
            compra=datos.get("compra"),
            venta=datos.get("venta"),
            usuario_id=usuario.get("sub", ""),
            usuario_username=usuario.get("username", ""),
        )

    except ValidationError as error:
        if hasattr(error, "message_dict"):
            errores = error.message_dict
        else:
            errores = {"error": error.messages}

        return JsonResponse(
            {"errores": errores},
            status=400,
        )

    return JsonResponse(
        {
            "mensaje": "Tasa comercial actualizada correctamente.",
            "tasa": _serializar_tasa(tasa),
        },
        status=201,
    )


@require_GET
@requiere_alguno_de_roles("ADMINISTRADOR", "ANALISTA_CAMBIARIO")
def historial_tasas_comerciales(request):
    """Devuelve el histórico de tasas comerciales registradas."""
    tasas = (
        TasaComercial.objects
        .select_related(
            "moneda_origen",
            "moneda_destino",
        )
        .all()
    )

    moneda_origen_id = request.GET.get("moneda_origen_id")
    moneda_destino_id = request.GET.get("moneda_destino_id")

    if moneda_origen_id:
        tasas = tasas.filter(
            moneda_origen_id=moneda_origen_id
        )

    if moneda_destino_id:
        tasas = tasas.filter(
            moneda_destino_id=moneda_destino_id
        )

    return JsonResponse(
        {
            "monedas": [
                {
                    "id": moneda.id,
                    "codigo": moneda.codigo,
                    "nombre": moneda.nombre,
                    "simbolo": moneda.simbolo,
                }
                for moneda in Moneda.objects.activas()
            ],
            "tasas": [
                _serializar_tasa(tasa)
                for tasa in tasas
            ]
        }
    )


@require_POST
def simular_conversion_view(request):
    """Simula una conversión pública sin crear transacciones."""

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener JSON válido."},
            status=400,
        )

    if not isinstance(datos, dict):
        return JsonResponse(
            {"error": "El cuerpo de la solicitud debe contener un objeto JSON."},
            status=400,
        )

    try:
        resultado = simular_conversion(
            moneda_origen_id=datos.get("moneda_origen_id"),
            moneda_destino_id=datos.get("moneda_destino_id"),
            monto=datos.get("monto"),
        )
    except ValidationError as exc:
        return JsonResponse(
            {
                "error": "No se pudo realizar la simulación.",
                "detalles": exc.message_dict,
            },
            status=400,
        )

    return JsonResponse(
        {
            "moneda_origen": resultado.moneda_origen.codigo,
            "moneda_destino": resultado.moneda_destino.codigo,
            "monto": str(resultado.monto),
            "tasa": str(resultado.tasa),
            "tipo_tasa": resultado.tipo_tasa,
            "fecha_hora": resultado.fecha_hora.isoformat(),
            "resultado": str(resultado.resultado),
        }
    )
