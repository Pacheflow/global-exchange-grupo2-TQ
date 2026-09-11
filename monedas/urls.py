from django.urls import path

from . import views


app_name = "monedas"


urlpatterns = [
    path(
        "",
        views.listar_monedas,
        name="listar_monedas",
    ),
    path(
        "activas/",
        views.listar_monedas_activas,
        name="listar_monedas_activas",
    ),
    path(
        "crear/",
        views.crear_moneda,
        name="crear_moneda",
    ),
    path(
        "<int:moneda_id>/editar/",
        views.editar_moneda,
        name="editar_moneda",
    ),
    path(
        "<int:moneda_id>/estado/",
        views.cambiar_estado_moneda,
        name="cambiar_estado_moneda",
    ),
]
