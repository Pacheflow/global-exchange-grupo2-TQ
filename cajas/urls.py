from django.urls import path

from . import views

app_name = "cajas"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("crear/", views.crear, name="crear"),
    path("<int:caja_id>/estado/", views.cambiar_estado, name="cambiar_estado"),
]
