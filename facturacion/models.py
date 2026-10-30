from django.db import models
from django.db.models import Q


class IntentoEmisionFacturaSegura(models.Model):
    """Ledger tecnico que evita repetir ``generar_de`` ante concurrencia o timeout.

    No representa la factura fiscal de HU-29. La capa de dominio puede enlazar su
    Factura con esta evidencia mediante ``clave_idempotencia`` o ``cdc``.
    """

    class Estado(models.TextChoices):
        EN_PROCESO = "EN_PROCESO", "En proceso"
        GENERADA = "GENERADA", "Generada por el proveedor"
        INDETERMINADA = "INDETERMINADA", "Resultado indeterminado"
        ERROR = "ERROR", "Error confirmado sin resultado"

    clave_idempotencia = models.CharField(max_length=255, unique=True, editable=False)
    huella_documento = models.CharField(max_length=64, editable=False)
    estado = models.CharField(max_length=14, choices=Estado.choices, default=Estado.EN_PROCESO)
    cdc = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    operacion_id = models.CharField(max_length=255, blank=True, editable=False)
    codigo_proveedor = models.IntegerField(null=True, blank=True, editable=False)
    descripcion_proveedor = models.TextField(blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-creado_en", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__in=["EN_PROCESO", "GENERADA", "INDETERMINADA", "ERROR"]),
                name="factura_segura_intento_estado_valido",
            ),
            models.CheckConstraint(
                condition=~Q(estado="GENERADA") | (Q(cdc__isnull=False) & ~Q(cdc="")),
                name="factura_segura_generada_con_cdc",
            ),
        ]

    def __str__(self):
        return f"{self.clave_idempotencia} ({self.estado})"
