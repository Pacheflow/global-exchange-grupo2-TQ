import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from usuarios.decorators import requiere_autenticacion

from .services import consultar_tasas_referencia
from .simulador import simular_conversion


def _serializar_tasa(tasa, *, desactualizada):
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
    """Consulta tasas reales y comunica expresamente frescura o indisponibilidad."""

    resultado = consultar_tasas_referencia()
    desactualizada = resultado.estado == "desactualizado"

    payload = {
        "estado": resultado.estado,
        "mensaje": resultado.mensaje,
        "tasas_referencia": [
            _serializar_tasa(
                tasa,
                desactualizada=desactualizada,
            )
            for tasa in resultado.tasas
        ],
        # Contrato reservado para HU-21.
        "tasas_comerciales": [],
    }

    return JsonResponse(
        payload,
        status=503 if resultado.estado == "indisponible" else 200,
    )


@require_POST
def simular_conversion_view(request):
    """
    Simula una conversión entre monedas.

    Esta funcionalidad es pública y no genera
    transacciones ni modifica datos.
    """

    try:
        datos = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                "error": (
                    "El cuerpo de la solicitud "
                    "debe contener JSON válido."
                )
            },
            status=400,
        )

    if not isinstance(datos, dict):
        return JsonResponse(
            {
                "error": (
                    "El cuerpo de la solicitud "
                    "debe contener un objeto JSON."
                )
            },
            status=400,
        )

    moneda_origen_id = datos.get("moneda_origen_id")
    moneda_destino_id = datos.get("moneda_destino_id")
    monto = datos.get("monto")

    try:
        resultado = simular_conversion(
            moneda_origen_id=moneda_origen_id,
            moneda_destino_id=moneda_destino_id,
            monto=monto,
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
        },
        status=200,
    )