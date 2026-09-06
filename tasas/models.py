from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from monedas.models import Moneda


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
                condition=~Q(moneda_origen=F("moneda_destino")),
                name="tasa_monedas_distintas",
            ),
            models.UniqueConstraint(
                fields=["moneda_origen", "moneda_destino"],
                condition=Q(vigente=True),
                name="una_tasa_vigente_por_par",
            ),
        ]

    def clean(self):
        """Valida las reglas básicas de una tasa comercial."""

        if self.moneda_origen_id and self.moneda_origen.estado != "ACTIVA":
            raise ValidationError(
                {"moneda_origen": "La moneda de origen debe estar activa."}
            )

        if self.moneda_destino_id and self.moneda_destino.estado != "ACTIVA":
            raise ValidationError(
                {"moneda_destino": "La moneda de destino debe estar activa."}
            )

        if self.compra is not None and self.compra <= 0:
            raise ValidationError(
                {"compra": "La tasa de compra debe ser mayor que cero."}
            )

        if self.venta is not None and self.venta <= 0:
            raise ValidationError(
                {"venta": "La tasa de venta debe ser mayor que cero."}
            )

    def __str__(self):
        return (
            f"{self.moneda_origen.codigo}/"
            f"{self.moneda_destino.codigo} "
            f"- versión {self.version}"
        )