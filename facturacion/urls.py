from django.urls import path
from . import views

app_name = "facturacion"
urlpatterns = [
    path("", views.listado, name="listado"),
    path("cliente/<int:cliente_id>/correo/", views.correo_cliente, name="correo_cliente"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/ver/", views.visualizar, name="visualizar"),
    path("<int:pk>/descargar/<str:formato>/", views.descargar, name="descargar"),
    path("<int:pk>/enviar/", views.enviar, name="enviar"),
]
