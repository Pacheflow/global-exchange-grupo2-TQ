from django.urls import path

from .views import configurar_notificaciones

app_name = "tasas_web"
urlpatterns = [path("notificaciones/configurar/", configurar_notificaciones, name="configurar_notificaciones")]
