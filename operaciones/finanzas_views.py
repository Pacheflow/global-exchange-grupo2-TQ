"""API administrativa común para dashboard y reportes del sprint 6."""
import re
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from usuarios.decorators import requiere_rol
from .finanzas import reporte_financiero


@requiere_rol("ADMINISTRADOR")
@require_GET
def metricas_financieras(request):
    """GET desde/hasta ISO inclusivos y agrupacion=dia|semana|mes.

    Por defecto, últimos 30 días incluyendo hoy. Rechaza parámetros desconocidos
    y duplicados para evitar filtros ignorados silenciosamente.
    """
    try:
        if set(request.GET) - {"desde", "hasta", "agrupacion"}:
            raise ValidationError("Parámetro desconocido.")
        if any(len(request.GET.getlist(key)) != 1 for key in request.GET):
            raise ValidationError("No se permiten parámetros duplicados.")
        hoy = timezone.localdate()
        fechas = {}
        for campo, defecto in (("desde", hoy - timedelta(days=29)), ("hasta", hoy)):
            valor = request.GET.get(campo, defecto.isoformat())
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
                raise ValueError
            fechas[campo] = date.fromisoformat(valor)
        if fechas["hasta"] == date.max:
            raise ValueError
        resultado = reporte_financiero(**fechas, agrupacion=request.GET.get("agrupacion", "dia"))
    except (ValueError, OverflowError):
        return JsonResponse({"error": "Usá fechas válidas YYYY-MM-DD."}, status=400)
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    response = JsonResponse(resultado)
    response["Cache-Control"] = "no-store"
    return response
