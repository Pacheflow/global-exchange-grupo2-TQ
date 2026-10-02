from django.urls import path

from . import views

app_name = "operaciones_web"

urlpatterns = [
    path("", views.inicio_operaciones, name="inicio"),
]
