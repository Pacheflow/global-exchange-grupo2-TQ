from django.urls import path

from . import views

app_name = "operaciones"

urlpatterns = [
    path("presenciales/clientes/", views.clientes_presenciales, name="clientes_presenciales"),
    path("presenciales/metodos/", views.metodos_presenciales, name="metodos_presenciales"),
    path("presenciales/previsualizar/", views.previsualizar_operacion_view, {"presencial": True}, name="preview_presencial"),
    path("presenciales/crear/", views.crear_transaccion_view, {"presencial": True}, name="crear_presencial"),
    path(
        "<int:transaccion_id>/periodos-liquidacion/",
        views.periodos_liquidacion_view,
        name="periodos_liquidacion",
    ),
    path(
        "<int:transaccion_id>/liquidar/",
        views.liquidar_transaccion_view,
        name="liquidar_transaccion",
    ),
    path(
        "previsualizar/",
        views.previsualizar_operacion_view,
        name="previsualizar_operacion",
    ),
    path(
        "crear/",
        views.crear_transaccion_view,
        name="crear_transaccion",
    ),
    path(
        "cancelar/",
        views.cancelar_transaccion_view,
        name="cancelar_transaccion",
    ),
    path(
        "metodos-pago/",
        views.metodos_pago_operacion_view,
        name="metodos_pago_operacion",
    ),
    path(
        "historial/",
        views.historial_transacciones_view,
        name="historial_transacciones",
    ),
    path(
        "<int:transaccion_id>/detalle/",
        views.detalle_transaccion_view,
        name="detalle_transaccion",
    ),
]
