from django.urls import path

from . import views
from .historico import historico_api
from .dashboard_analista import dashboard_analista_api


app_name = "tasas"

urlpatterns = [
    path("dashboard-analista/", dashboard_analista_api, name="dashboard_analista"),
    path("historico/", historico_api, name="historico"),
    path(
        "",
        views.consultar_tasas,
        name="consultar",
    ),
    path(
        "comerciales/",
        views.administrar_tasa_comercial,
        name="administrar_tasa_comercial",
    ),
    path(
        "comerciales/historial/",
        views.historial_tasas_comerciales,
        name="historial_tasas_comerciales",
    ),
    path(
        "comerciales/<int:tasa_id>/desactivar/",
        views.desactivar_tasa_comercial_view,
        name="desactivar_tasa_comercial",
    ),
    path(
        "simular/",
        views.simular_conversion_view,
        name="simular_conversion",
    ),
]
