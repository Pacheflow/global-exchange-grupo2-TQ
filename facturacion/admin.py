from django.contrib import admin

from .models import IntentoEmisionFacturaSegura, Factura


@admin.register(IntentoEmisionFacturaSegura)
class IntentoEmisionFacturaSeguraAdmin(admin.ModelAdmin):
    list_display = (
        "clave_idempotencia", "estado", "cdc", "operacion_id",
        "codigo_proveedor", "actualizado_en",
    )
    list_filter = ("estado",)
    search_fields = ("clave_idempotencia", "cdc", "operacion_id")
    readonly_fields = tuple(campo.name for campo in IntentoEmisionFacturaSegura._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Factura)
class FacturaAdmin(IntentoEmisionFacturaSeguraAdmin):
    list_display = ("id", "transaccion", "estado", "cdc", "codigo_error", "actualizada_en")
    list_filter = ("estado",)
    search_fields = ("cdc", "transaccion__cliente__documento")
    readonly_fields = tuple(campo.name for campo in Factura._meta.fields)
