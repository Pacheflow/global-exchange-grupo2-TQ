from django.urls import path

from . import views

app_name = "cajas"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("crear/", views.crear, name="crear"),
    path("operar/", views.operar, name="operar"),
    path("<int:caja_id>/abrir/", views.apertura, name="apertura"),
    path("periodos/<int:periodo_id>/", views.apertura_confirmada, name="apertura_confirmada"),
    path("<int:caja_id>/estado/", views.cambiar_estado, name="cambiar_estado"),
]
