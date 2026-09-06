from django.urls import path

from . import views

app_name = "usuarios_api"


urlpatterns = [
    path(
        "crear/",
        views.crear_usuario_api,
        name="crear_usuario",
    ),
    path(
        "<str:user_id>/detalle/",
        views.detalle_usuario_api,
        name="detalle_usuario",
    ),
    path(
        "<str:user_id>/editar/",
        views.editar_usuario_api,
        name="editar_usuario",
    ),
    path(
        "<str:user_id>/baja/",
        views.baja_usuario_api,
        name="baja_usuario",
    ),
]