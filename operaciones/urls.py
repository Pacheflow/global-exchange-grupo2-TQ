from django.urls import path

from . import views

app_name = "operaciones"

urlpatterns = [
    path(
        "previsualizar/",
        views.previsualizar_operacion_view,
        name="previsualizar_operacion",
    ),
    path(
        "crear/",
        views.crear_transaccion_view,
        name="crear_transaccion",
    ),
    path(
        "cancelar/",
        views.cancelar_transaccion_view,
        name="cancelar_transaccion",
    ),
    path(
        "metodos-pago/",
        views.metodos_pago_operacion_view,
        name="metodos_pago_operacion",
    ),
    path(
        "historial/",
        views.historial_transacciones_view,
        name="historial_transacciones",
    ),
    path(
        "<int:transaccion_id>/detalle/",
        views.detalle_transaccion_view,
        name="detalle_transaccion",
    ),
]
