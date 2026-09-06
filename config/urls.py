from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("clientes/", include("clientes.urls")),

    path("api/clientes/", include("clientes.api_urls")),
    path("api/usuarios/", include("usuarios.api_urls")),
    path("api/monedas/", include("monedas.urls")),
    path("api/metodos-pago/", include("metodos_pago.urls")),
    path("api/tasas/", include("tasas.urls")),

    path("", include("usuarios.urls")),
]