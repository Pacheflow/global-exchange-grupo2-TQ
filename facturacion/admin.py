from django.contrib import admin

from .models import (
    Factura, IntentoEmisionFacturaSegura, NumeroFiscalAsignado,
    RangoNumeracionFiscal,
)


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
    list_display = (
        "id", "transaccion", "estado", "estado_sifen", "cdc",
        "codigo_error", "consultada_sifen_en", "actualizada_en",
    )
    list_filter = ("estado", "estado_sifen")
    search_fields = ("cdc", "transaccion__cliente__documento")
    readonly_fields = tuple(campo.name for campo in Factura._meta.fields)


@admin.register(RangoNumeracionFiscal)
class RangoNumeracionFiscalAdmin(IntentoEmisionFacturaSeguraAdmin):
    list_display = (
        "tipo_documento", "timbrado", "establecimiento", "punto_expedicion",
        "numero_desde", "numero_hasta", "siguiente_numero", "activo",
    )
    list_filter = ("activo", "tipo_documento")
    search_fields = ("timbrado", "establecimiento", "punto_expedicion")
    readonly_fields = tuple(campo.name for campo in RangoNumeracionFiscal._meta.fields)


@admin.register(NumeroFiscalAsignado)
class NumeroFiscalAsignadoAdmin(IntentoEmisionFacturaSeguraAdmin):
    list_display = ("factura", "rango", "numero", "asignado_en")
    list_filter = ()
    search_fields = ("factura__transaccion__cliente__documento", "numero")
    readonly_fields = tuple(campo.name for campo in NumeroFiscalAsignado._meta.fields)
