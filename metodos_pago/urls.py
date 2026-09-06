from django.urls import path

from . import views

app_name = "metodos_pago"


urlpatterns = [
    path(
        "",
        views.inicio_metodos_pago,
        name="inicio_metodos_pago",
    ),
    path(
        "registrar/",
        views.registrar_metodo_pago,
        name="registrar_metodo_pago",
    ),
    path(
        "consultar/",
        views.consultar_metodos_pago,
        name="consultar_metodos_pago",
    ),
    path(
        "editar/<int:metodo_id>/",
        views.editar_metodo_pago,
        name="editar_metodo_pago",
    ),
    path(
        "estado/<int:metodo_id>/",
        views.cambiar_estado_metodo_pago,
        name="cambiar_estado_metodo_pago",
    ),
]
