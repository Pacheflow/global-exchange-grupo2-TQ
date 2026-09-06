from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from monedas.models import Moneda


class ConsultaProveedorTasas(models.Model):
    """Última respuesta externa válida conservada para trazabilidad y fallback."""

    fuente = models.CharField(max_length=100)

    moneda_base = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="consultas_tasas",
    )

    fecha_hora_fuente = models.DateTimeField()
    recibida_en = models.DateTimeField(auto_now_add=True)
    respuesta = models.JSONField()

    class Meta:
        ordering = ("-recibida_en",)
        verbose_name = "consulta válida al proveedor de tasas"
        verbose_name_plural = "consultas válidas al proveedor de tasas"

    def __str__(self):
        return (
            f"{self.fuente} · "
            f"{self.moneda_base.codigo} · "
            f"{self.fecha_hora_fuente}"
        )


class TasaReferencia(models.Model):
    """Última tasa externa válida normalizada para un par de monedas."""

    moneda_base = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="tasas_referencia_base",
    )

    moneda_cotizada = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="tasas_referencia_cotizada",
    )

    valor = models.DecimalField(
        max_digits=24,
        decimal_places=10,
        validators=[
            MinValueValidator(
                Decimal("0.0000000001")
            )
        ],
    )

    fuente = models.CharField(max_length=100)
    fecha_hora_fuente = models.DateTimeField()
    vigente_hasta = models.DateTimeField()
    actualizada_en = models.DateTimeField(auto_now=True)

    consulta = models.ForeignKey(
        ConsultaProveedorTasas,
        on_delete=models.PROTECT,
        related_name="tasas",
    )

    class Meta:
        ordering = (
            "moneda_base__codigo",
            "moneda_cotizada__codigo",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "moneda_base",
                    "moneda_cotizada",
                ),
                name="tasa_referencia_par_unico",
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    moneda_base=models.F(
                        "moneda_cotizada"
                    )
                ),
                name=(
                    "tasa_referencia_"
                    "monedas_distintas"
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(valor__gt=0),
                name="tasa_referencia_valor_positivo",
            ),
        ]

    def __str__(self):
        return (
            f"{self.moneda_base.codigo}/"
            f"{self.moneda_cotizada.codigo}: "
            f"{self.valor}"
        )


class TasaComercial(models.Model):
    """
    Representa una tasa comercial de compra y venta
    entre dos monedas de Global Exchange.
    """

    moneda_origen = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="tasas_origen",
    )

    moneda_destino = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="tasas_destino",
    )

    compra = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    venta = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    vigente = models.BooleanField(
        default=True,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    usuario_id = models.CharField(
        max_length=255,
    )

    usuario_username = models.CharField(
        max_length=150,
        blank=True,
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ("-fecha_registro",)

        constraints = [
            models.CheckConstraint(
                condition=~Q(
                    moneda_origen=F(
                        "moneda_destino"
                    )
                ),
                name="tasa_monedas_distintas",
            ),
            models.UniqueConstraint(
                fields=[
                    "moneda_origen",
                    "moneda_destino",
                ],
                condition=Q(vigente=True),
                name="una_tasa_vigente_por_par",
            ),
        ]

    def clean(self):
        """Valida las reglas básicas de una tasa comercial."""

        if (
            self.moneda_origen_id
            and self.moneda_origen.estado != "ACTIVA"
        ):
            raise ValidationError(
                {
                    "moneda_origen": (
                        "La moneda de origen "
                        "debe estar activa."
                    )
                }
            )

        if (
            self.moneda_destino_id
            and self.moneda_destino.estado != "ACTIVA"
        ):
            raise ValidationError(
                {
                    "moneda_destino": (
                        "La moneda de destino "
                        "debe estar activa."
                    )
                }
            )

        if self.compra is not None and self.compra <= 0:
            raise ValidationError(
                {
                    "compra": (
                        "La tasa de compra "
                        "debe ser mayor que cero."
                    )
                }
            )

        if self.venta is not None and self.venta <= 0:
            raise ValidationError(
                {
                    "venta": (
                        "La tasa de venta "
                        "debe ser mayor que cero."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.moneda_origen.codigo}/"
            f"{self.moneda_destino.codigo} "
            f"- versión {self.version}"
        )