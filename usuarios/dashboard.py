"""Lecturas del dashboard administrativo de Sprint 6, sin cálculo financiero.

Los conteos abarcan todo el histórico COMPLETADA, sin filtro temporal. La
actividad comparte ese alcance y se ordena por creación, no por liquidación.
"""

from django.db.models import Count, Q

from operaciones.models import Transaccion


def contrato_dashboard():
    """Contrato inicial: null financiero significa no disponible, nunca cero."""
    return {
        "ganancia_dia": None,
        "ganancia_semana": None,
        "ganancia_mes": None,
        "operaciones": None,
        "compras": None,
        "ventas": None,
        "volumen": None,
        "moneda": "PYG",
    }


def consultar_dashboard_administrativo():
    """Agrega conteos y lee como máximo cinco operaciones, sin efectos laterales.

    Solo debe invocarse después de autorizar ADMINISTRADOR en la vista.
    No consulta pagos, tasas, fondos, cajas ni facturas.
    """
    completadas = Transaccion.objects.filter(estado="COMPLETADA")
    resumen = contrato_dashboard()
    resumen.update(completadas.aggregate(
        operaciones=Count("pk"),
        compras=Count("pk", filter=Q(tipo="COMPRA")),
        ventas=Count("pk", filter=Q(tipo="VENTA")),
    ))
    recientes = list(completadas.select_related(
        "cliente", "moneda_origen", "moneda_destino",
    ).order_by("-fecha_creacion", "-pk")[:5])
    return resumen, recientes
