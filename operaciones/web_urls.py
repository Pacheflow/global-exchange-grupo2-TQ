from django.urls import path

from . import views

app_name = "operaciones_web"

urlpatterns = [
    path("historial/", views.historial_operaciones_cajero, name="historial"),
    path("", views.inicio_operaciones, name="inicio"),
]
