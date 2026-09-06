from django.urls import path

from . import views


app_name = "tasas"


urlpatterns = [
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
]