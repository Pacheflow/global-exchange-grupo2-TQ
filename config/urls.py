from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("clientes/", include("clientes.urls")),
    path("monedas/", include("monedas.urls")),
    path("metodos-pago/", include("metodos_pago.urls")),
    path("tasas/", include("tasas.urls")),
    path("", include("usuarios.urls")),
]
