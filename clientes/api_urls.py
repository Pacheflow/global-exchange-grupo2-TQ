from django.urls import path

from . import views

app_name = "clientes_api"


urlpatterns = [
    path(
        "crear/",
        views.crear_cliente_api,
        name="crear_cliente",
    ),
    path(
        "<int:cliente_id>/editar/",
        views.editar_cliente_api,
        name="editar_cliente",
    ),
    path(
        "<int:cliente_id>/baja/",
        views.dar_de_baja_cliente_api,
        name="dar_de_baja_cliente",
    ),
    path(
        "<int:cliente_id>/seleccionar/",
        views.seleccionar_cliente_api,
        name="seleccionar_cliente",
    ),
]