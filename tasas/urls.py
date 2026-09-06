from django.urls import path

from . import views


app_name = "tasas"

urlpatterns = [
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
        "simular/",
        views.simular_conversion_view,
        name="simular_conversion",
    ),
]