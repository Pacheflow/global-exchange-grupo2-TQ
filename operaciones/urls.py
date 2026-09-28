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
        "historial/",
        views.historial_transacciones_view,
        name="historial_transacciones",
    ),
]