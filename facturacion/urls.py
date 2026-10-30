from django.urls import path
from . import views

app_name = "facturacion"
urlpatterns = [
    path("", views.listado, name="listado"),
    path("<int:pk>/procesar/", views.procesar, name="procesar"),
    path("<int:pk>/actualizar-estado-sifen/", views.actualizar_estado, name="actualizar_estado"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/ver/", views.visualizar, name="visualizar"),
    path("<int:pk>/descargar/<str:formato>/", views.descargar, name="descargar"),
]
