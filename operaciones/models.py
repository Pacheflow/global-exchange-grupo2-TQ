from django.db import models
from django.db.models import F, Q


class Transaccion(models.Model):
    """Representa una operación de compra o venta realizada entre monedas."""

    TIPOS_TRANSACCION = [
        ("COMPRA", "Compra"),
        ("VENTA", "Venta"),
    ]

    ESTADOS_TRANSACCION = [
        ("PENDIENTE", "Pendiente"),
        ("CANCELADA", "Cancelada"),
    ]

    clave_idempotencia = models.CharField(
        max_length=255,
        unique=True,
    )

    cliente = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.PROTECT,
        related_name="transacciones",
    )

    creado_por_keycloak_id = models.CharField(
        max_length=255,
    )

    creado_por_username = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    tipo = models.CharField(
        max_length=10,
        choices=TIPOS_TRANSACCION,
    )

    moneda_origen = models.ForeignKey(
        "monedas.Moneda",
        on_delete=models.PROTECT,
        related_name="transacciones_origen",
    )

    moneda_destino = models.ForeignKey(
        "monedas.Moneda",
        on_delete=models.PROTECT,
        related_name="transacciones_destino",
    )

    monto_origen = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    monto_destino = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    tasa_comercial = models.ForeignKey(
        "tasas.TasaComercial",
        on_delete=models.PROTECT,
        related_name="transacciones",
    )

    tasa_aplicada = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    porcentaje_comision = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    importe_comision = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    metodo_pago = models.ForeignKey(
        "metodos_pago.MetodoPago",
        on_delete=models.PROTECT,
        related_name="transacciones",
    )

    metodo_pago_nombre = models.CharField(
        max_length=100,
    )

    estado = models.CharField(
        max_length=10,
        choices=ESTADOS_TRANSACCION,
        default="PENDIENTE",
    )

    cancelado_por_keycloak_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    cancelado_por_username = models.CharField(
        max_length=150,
        null=True,
        blank=True,
    )

    cancelado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    motivo_cancelacion = models.TextField(
        null=True,
        blank=True,
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-fecha_creacion",)
        verbose_name = "transacción"
        verbose_name_plural = "transacciones"

        constraints = [
            models.CheckConstraint(
                condition=~Q(moneda_origen=F("moneda_destino")),
                name="transaccion_monedas_distintas",
            ),
            models.CheckConstraint(
                condition=Q(monto_origen__gt=0),
                name="transaccion_monto_origen_positivo",
            ),
            models.CheckConstraint(
                condition=Q(monto_destino__gt=0),
                name="transaccion_monto_destino_positivo",
            ),
            models.CheckConstraint(
                condition=Q(tasa_aplicada__gt=0),
                name="transaccion_tasa_aplicada_positiva",
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_comision__gte=0),
                name="transaccion_comision_no_negativa",
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_comision__lte=100),
                name="transaccion_comision_maxima_100",
            ),
            models.CheckConstraint(
                condition=Q(importe_comision__gte=0),
                name="transaccion_importe_comision_no_negativo",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="CANCELADA")
                    | (
                        Q(cancelado_por_keycloak_id__isnull=False)
                        & Q(cancelado_por_username__isnull=False)
                        & Q(cancelado_en__isnull=False)
                        & Q(motivo_cancelacion__isnull=False)
                        & ~Q(motivo_cancelacion="")
                    )
                ),
                name="transaccion_cancelada_con_datos",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado="PENDIENTE")
                    | (
                        Q(cancelado_por_keycloak_id__isnull=True)
                        & Q(cancelado_por_username__isnull=True)
                        & Q(cancelado_en__isnull=True)
                        & Q(motivo_cancelacion__isnull=True)
                    )
                ),
                name="transaccion_pendiente_sin_cancelacion",
            ),
        ]

    def __str__(self):
        """Devuelve una descripción breve de la transacción."""
        return (
            f"{self.get_tipo_display()} "
            f"{self.moneda_origen.codigo}/{self.moneda_destino.codigo}"
        )