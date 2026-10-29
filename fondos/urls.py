from django.urls import path
from . import views

app_name = "fondos"
urlpatterns = [path("", views.inicio, name="inicio"), path("cargar/", views.carga, name="cargar"),
               path("movimientos/", views.movimientos, name="movimientos")]
