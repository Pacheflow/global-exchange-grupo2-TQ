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


class Factura(models.Model):
    """Comprobante de una operación; su emisión no altera efectos financieros."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de emisión"
        EN_PROCESO = "EN_PROCESO", "Emisión en proceso"
        GENERADA = "GENERADA", "Generada por el proveedor"
        ERROR = "ERROR", "Emisión con error"
        INDETERMINADA = "INDETERMINADA", "Emisión pendiente de conciliación"

    transaccion = models.OneToOneField("operaciones.Transaccion", on_delete=models.PROTECT, related_name="factura")
    intento = models.OneToOneField(IntentoEmisionFacturaSegura, null=True, blank=True, on_delete=models.PROTECT)
    estado = models.CharField(max_length=14, choices=Estado.choices, default=Estado.PENDIENTE)
    datos_operacion = models.JSONField(default=dict, editable=False)
    cdc = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    codigo_error = models.CharField(max_length=80, blank=True, editable=False)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)
    generada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-creada_en", "-pk")
        constraints = [
            models.CheckConstraint(condition=Q(estado__in=["PENDIENTE", "EN_PROCESO", "GENERADA", "ERROR", "INDETERMINADA"]), name="factura_estado_valido"),
            models.CheckConstraint(condition=~Q(estado="GENERADA") | (Q(cdc__isnull=False, generada_en__isnull=False, intento__isnull=False) & ~Q(cdc="")), name="factura_generada_con_evidencia"),
        ]


class EnvioFactura(models.Model):
    """Auditoría de cada intento de correo, independiente de la emisión."""

    class Estado(models.TextChoices):
        EN_PROCESO = "EN_PROCESO", "En proceso"
        ENVIADO = "ENVIADO", "Enviado"
        ERROR = "ERROR", "Error de envío"

    factura = models.ForeignKey(Factura, on_delete=models.PROTECT, related_name="envios")
    destinatario = models.EmailField(blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.EN_PROCESO)
    codigo_error = models.CharField(max_length=80, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    terminado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-creado_en", "-pk")
        constraints = [
            models.UniqueConstraint(fields=["factura"], condition=Q(estado__in=["EN_PROCESO", "ENVIADO"]), name="factura_un_envio_activo_o_exitoso"),
            models.CheckConstraint(condition=Q(estado__in=["EN_PROCESO", "ENVIADO", "ERROR"]), name="envio_factura_estado_valido"),
        ]
