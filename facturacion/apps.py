from django.apps import AppConfig


class FacturacionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "facturacion"
    verbose_name = "Facturacion electronica"

    def ready(self):
        from . import signals  # noqa: F401
