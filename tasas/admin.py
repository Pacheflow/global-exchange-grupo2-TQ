from django.contrib import admin

from .models import ConsultaProveedorTasas, TasaReferencia


@admin.register(ConsultaProveedorTasas)
class ConsultaProveedorTasasAdmin(admin.ModelAdmin):
    list_display = ("fuente", "moneda_base", "fecha_hora_fuente", "recibida_en")
    readonly_fields = ("fuente", "moneda_base", "fecha_hora_fuente", "recibida_en", "respuesta")


@admin.register(TasaReferencia)
class TasaReferenciaAdmin(admin.ModelAdmin):
    list_display = (
        "moneda_base",
        "moneda_cotizada",
        "valor",
        "fuente",
        "fecha_hora_fuente",
        "vigente_hasta",
    )
    readonly_fields = ("actualizada_en",)
