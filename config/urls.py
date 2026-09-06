from django.contrib import admin
from django.urls import include, path

from metodos_pago import views as metodos_pago_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("clientes/", include("clientes.urls")),

    path("api/clientes/", include("clientes.api_urls")),
    path("api/usuarios/", include("usuarios.api_urls")),
    path("api/monedas/", include("monedas.urls")),
    path("api/metodos-pago/", include("metodos_pago.urls")),
    path("api/tasas/", include("tasas.urls")),

    path("metodos-pago/", metodos_pago_views.inicio_metodos_pago, name="metodos_pago_pagina"),

    path("", include("usuarios.urls")),
]