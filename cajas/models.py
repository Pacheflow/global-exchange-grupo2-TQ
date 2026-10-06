from django.db import models
from django.db.models import Q
from django.db.models.functions import Upper


class CajaQuerySet(models.QuerySet):
    """Consultas compartidas del catálogo de cajas."""

    def habilitadas(self):
        """Devuelve las cajas habilitadas; no indica que estén abiertas."""
        return self.filter(estado="HABILITADA")


class Caja(models.Model):
    """Configuración de una caja, independiente de sus períodos operativos."""

    ESTADOS = [("HABILITADA", "Habilitada"), ("DESHABILITADA", "Deshabilitada")]
    codigo = models.CharField(max_length=30)
    nombre = models.CharField(max_length=100)
    estado = models.CharField(max_length=13, choices=ESTADOS, default="HABILITADA")
    creado_por_keycloak_id = models.CharField(max_length=255, editable=False)
    creado_por_username = models.CharField(max_length=150, blank=True, editable=False)
    actualizado_por_keycloak_id = models.CharField(max_length=255, editable=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    objects = CajaQuerySet.as_manager()

    class Meta:
        ordering = ("codigo",)
        constraints = [
            models.UniqueConstraint(Upper("codigo"), name="caja_codigo_unico"),
            models.CheckConstraint(condition=~Q(codigo=""), name="caja_codigo_no_vacio"),
            models.CheckConstraint(condition=~Q(nombre=""), name="caja_nombre_no_vacio"),
            models.CheckConstraint(condition=Q(estado__in=["HABILITADA", "DESHABILITADA"]), name="caja_estado_valido"),
        ]

    def save(self, *args, **kwargs):
        """Normaliza código y nombre sin aceptar datos de identidad del formulario."""
        self.codigo = self.codigo.strip().upper()
        self.nombre = self.nombre.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        """Identifica la caja mediante su código y nombre."""
        return f"{self.codigo} - {self.nombre}"


class PeriodoCaja(models.Model):
    """Período operativo con responsable externo y apertura registrada por el servidor.

    CERRADO reserva el contrato para una HU posterior; aquí no se implementa cierre.
    """

    ESTADOS = [("ABIERTO", "Abierto"), ("CERRADO", "Cerrado")]
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="periodos")
    estado = models.CharField(max_length=7, choices=ESTADOS, default="ABIERTO")
    responsable_keycloak_id = models.CharField(max_length=255, editable=False)
    responsable_username = models.CharField(max_length=150, blank=True, editable=False)
    fecha_apertura = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fecha_apertura",)
        constraints = [
            models.UniqueConstraint(
                fields=["caja"], condition=Q(estado="ABIERTO"),
                name="caja_unico_periodo_abierto",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["ABIERTO", "CERRADO"]),
                name="periodo_caja_estado_valido",
            ),
        ]

    def __str__(self):
        """Identifica el período sin confundirlo con la habilitación de la caja."""
        return f"{self.caja.codigo} - período {self.pk} ({self.estado})"


class SaldoInicialCaja(models.Model):
    """Importe histórico por moneda de una apertura; no representa saldo actual."""

    periodo = models.ForeignKey(PeriodoCaja, on_delete=models.PROTECT, related_name="saldos_iniciales")
    moneda = models.ForeignKey("monedas.Moneda", on_delete=models.PROTECT, related_name="saldos_iniciales_caja")
    monto = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        ordering = ("moneda__codigo",)
        constraints = [
            models.UniqueConstraint(fields=["periodo", "moneda"], name="saldo_inicial_periodo_moneda_unico"),
            models.CheckConstraint(condition=Q(monto__gte=0), name="saldo_inicial_no_negativo"),
        ]

    def __str__(self):
        """Devuelve el importe inicial completo y su moneda."""
        return f"{self.monto} {self.moneda.codigo} - período {self.periodo_id}"
