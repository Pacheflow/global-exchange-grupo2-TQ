from django.urls import path

from . import reportes, views

app_name = "operaciones_web"

urlpatterns = [
    path(
        "reportes/transacciones/",
        reportes.reporte_administrativo_transacciones,
        name="reporte_administrativo_transacciones",
    ),
    path(
        "reportes/transacciones/exportar-pdf/",
        reportes.reporte_administrativo_transacciones,
        {"exportar": True},
        name="exportar_transacciones_pdf",
    ),
    path(
        "reportes/transacciones/<int:transaccion_id>/",
        reportes.detalle_reporte_transaccion,
        name="detalle_reporte_transaccion",
    ),
    path("efectivo/", views.inicio_operaciones, {"presencial": True}, name="presencial"),
    path("historial/", views.historial_operaciones_cajero, name="historial"),
    path("", views.inicio_operaciones, name="inicio"),
]
