from django.urls import path

from . import views


app_name = "pagos"

urlpatterns = [
    path("<int:transaccion_id>/pago/cambiar-metodo/", views.cambiar_metodo, name="cambiar_metodo"),
    path("<int:transaccion_id>/pago/intentos/", views.intentos, name="intentos"),
    path("<int:transaccion_id>/pago/iniciar/", views.iniciar, name="iniciar"),
    path("<int:transaccion_id>/pago/", views.consultar, name="consultar"),
    path("<int:transaccion_id>/pago/reintentar/", views.reintentar, name="reintentar"),
    path("<int:transaccion_id>/pago/recuperar/", views.recuperar, name="recuperar"),
]
