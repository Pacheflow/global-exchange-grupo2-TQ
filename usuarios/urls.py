from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login, name="login"),
    path("registro/", views.registro, name="registro"),
    path("callback/", views.callback, name="callback"),
    path("logout/", views.logout, name="logout"),
    path("panel/", views.dashboard, name="dashboard"),
    path("roles-permisos/", views.roles_permisos, name="roles_permisos"),
    path("usuarios/", views.usuarios, name="list"),
    path("usuarios/nuevo/", views.crear_usuario, name="create"),
    path("usuarios/<str:user_id>/editar/", views.editar_usuario, name="edit"),
    path("usuarios/<str:user_id>/baja/", views.baja_usuario, name="disable"),
    path("clientes/seleccionar/", views.clientes, name="clients"),
    path("perfil/", views.perfil_usuario, name="perfil_usuario"),
    path("acceso-administrador/", views.acceso_administrador, name="acceso_administrador"),
    path("asignar-rol/", views.asignar_rol, name="asignar_rol"),
    path("monedas/", views.monedas, name="monedas"),
    path("tasas/", views.tasas, name="tasas"),
    path("tasas-comerciales/", views.tasas_comerciales, name="tasas_comerciales"),
    path("simulador/", views.simulador, name="simulador"),
    path("pagos/", views.pagos, name="pagos"),
]
