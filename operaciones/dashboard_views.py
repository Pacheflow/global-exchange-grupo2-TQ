"""Endpoint de lectura del tablero administrativo con filtros coordinados."""
import logging

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from usuarios.decorators import requiere_rol
from usuarios.dashboard import consultar_dashboard_administrativo, divisas_dashboard, validar_filtros


@never_cache
@requiere_rol("ADMINISTRADOR")
@require_GET
def metricas_dashboard(request):
    """Devuelve todos los componentes del panel para una misma selección válida."""
    try:
        filtros = validar_filtros(request.GET, divisas=divisas_dashboard())
        return JsonResponse(consultar_dashboard_administrativo(filtros))
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    except DatabaseError:
        logging.getLogger(__name__).error("DASHBOARD_ADMIN_METRICAS_FALLIDAS")
        return JsonResponse({"error": "No se pudieron cargar las métricas. Intentá nuevamente."}, status=503)
