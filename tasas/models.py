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
        max_digits=24,
        decimal_places=10,
    )

    venta = models.DecimalField(
        max_digits=24,
        decimal_places=10,
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


class ConfiguracionNotificacionTasa(models.Model):
    """Acuerdo HU-20: umbral global persistente; no es un porcentaje impuesto por la ERS."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    umbral_porcentaje = models.DecimalField(max_digits=24, decimal_places=10, default=Decimal("3"))

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="notificacion_config_unica"),
            models.CheckConstraint(condition=Q(umbral_porcentaje__gt=0), name="notificacion_umbral_positivo"),
        ]

    def clean(self):
        """El umbral debe ser decimal, finito y positivo, sin redondeo silencioso."""
        super().clean()
        valor = self.umbral_porcentaje
        if not isinstance(valor, Decimal) or not valor.is_finite() or valor <= 0:
            raise ValidationError({"umbral_porcentaje": "Ingresá un porcentaje finito y mayor que cero."})


class EventoNotificacionTasa(models.Model):
    """Actualización comercial confirmada y criterio capturado antes del commit.

    No es una tarea programada ni tiene reintentos. La callback posterior al
    commit lo procesa una vez y conserva el resultado de obtener destinatarios.
    """

    tasa = models.OneToOneField(TasaComercial, on_delete=models.PROTECT, related_name="evento_notificacion")
    compra_anterior = models.DecimalField(max_digits=24, decimal_places=10, null=True)
    venta_anterior = models.DecimalField(max_digits=24, decimal_places=10, null=True)
    umbral_porcentaje = models.DecimalField(max_digits=24, decimal_places=10)
    procesado = models.BooleanField(default=False)
    error_destinatarios = models.CharField(max_length=100, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)


class BaseNotificacionTasa(models.Model):
    """Últimos valores notificados con éxito para una identidad Keycloak y un par.

    Compra y venta avanzan independientemente. La primera tasa o la vigente
    anterior inicializan valores ausentes sin generar un aviso por sí mismas.
    """

    destinatario_id = models.CharField(max_length=255)
    moneda_origen = models.ForeignKey(Moneda, on_delete=models.PROTECT, related_name="bases_notificacion_origen")
    moneda_destino = models.ForeignKey(Moneda, on_delete=models.PROTECT, related_name="bases_notificacion_destino")
    compra = models.DecimalField(max_digits=24, decimal_places=10)
    venta = models.DecimalField(max_digits=24, decimal_places=10)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["destinatario_id", "moneda_origen", "moneda_destino"], name="base_notificacion_usuario_par_unica",
        )]


class ResultadoNotificacionTasa(models.Model):
    """Trazabilidad mínima y deduplicación por actualización y destinatario.

    ENVIADO significa aceptación por el backend, no entrega final. Un resultado
    EN_PROCESO tras una interrupción es indeterminado: SMTP y BD no son atómicos.
    No se persisten tokens, direcciones ajenas ni mensajes internos de excepción.
    """

    ESTADOS = [("EN_PROCESO", "En proceso"), ("SIN_CAMBIOS", "Sin cambios relevantes"),
               ("ENVIADO", "Aceptado por correo"), ("FALLIDO", "Fallido")]
    evento = models.ForeignKey(EventoNotificacionTasa, on_delete=models.PROTECT, related_name="resultados")
    destinatario_id = models.CharField(max_length=255)
    estado = models.CharField(max_length=11, choices=ESTADOS, default="EN_PROCESO")
    cambios = models.JSONField(default=list)
    error = models.CharField(max_length=100, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["evento", "destinatario_id"], name="notificacion_evento_usuario_unica"),
            models.CheckConstraint(condition=Q(estado__in=["EN_PROCESO", "SIN_CAMBIOS", "ENVIADO", "FALLIDO"]),
                                   name="notificacion_resultado_estado_valido"),
        ]
