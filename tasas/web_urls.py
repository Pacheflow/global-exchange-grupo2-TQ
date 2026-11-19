from django.urls import path

from .views import configurar_notificaciones
from .historico import historico_web

app_name = "tasas_web"
urlpatterns = [
    path("historico/", historico_web, name="historico"),
    path("notificaciones/configurar/", configurar_notificaciones, name="configurar_notificaciones"),
]
