"""Fondos internos simulados: no representan saldos bancarios ni de Stripe."""
from django.db import models
from django.db.models import Q


class Fondo(models.Model):
    moneda = models.OneToOneField("monedas.Moneda", on_delete=models.PROTECT)


class MovimientoFondo(models.Model):
    """Asiento inmutable; el saldo se deriva sin permitir su edición directa."""
    fondo = models.ForeignKey(Fondo, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=7, choices=[("INGRESO", "Ingreso"), ("EGRESO", "Egreso")])
    monto = models.DecimalField(max_digits=18, decimal_places=6)
    operacion = models.ForeignKey("operaciones.Transaccion", null=True, blank=True, on_delete=models.PROTECT)
    clave = models.CharField(max_length=255, unique=True)
    motivo = models.CharField(max_length=255)
    referencia = models.CharField(max_length=255, blank=True)
    responsable = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fecha", "-pk")
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="fondo_movimiento_positivo"),
            models.CheckConstraint(condition=Q(tipo__in=["INGRESO", "EGRESO"]), name="fondo_tipo_valido"),
            models.UniqueConstraint(fields=["operacion", "tipo"], name="fondo_efecto_operacion_unico"),
        ]

    def save(self, *args, **kwargs):
        """Impide reescribir un movimiento ya registrado."""
        if not self._state.adding:
            raise ValueError("Los movimientos de Fondos son inmutables.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Conserva la evidencia financiera original."""
        raise ValueError("Los movimientos de Fondos no se eliminan.")


class ReservaFondo(models.Model):
    operacion = models.OneToOneField("operaciones.Transaccion", on_delete=models.PROTECT)
    fondo = models.ForeignKey(Fondo, on_delete=models.PROTECT, related_name="reservas")
    monto = models.DecimalField(max_digits=18, decimal_places=6)
    estado = models.CharField(max_length=10, default="ACTIVA", choices=[
        ("ACTIVA", "Activa"), ("CONSUMIDA", "Consumida"), ("LIBERADA", "Liberada")])
    fecha = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="fondo_reserva_positiva"),
            models.CheckConstraint(condition=Q(estado__in=["ACTIVA", "CONSUMIDA", "LIBERADA"]), name="fondo_reserva_estado_valido"),
        ]


class FinalizacionOnline(models.Model):
    """Evidencia única; VENTA acredita recepción simulada, COMPRA un Pago validado."""
    operacion = models.OneToOneField("operaciones.Transaccion", on_delete=models.PROTECT)
    fuente = models.CharField(max_length=20, choices=[("STRIPE_TEST", "Stripe TEST"), ("VENTA_SIMULADA", "Venta simulada")])
    referencia = models.CharField(max_length=255, unique=True)
    monto_recibido = models.DecimalField(max_digits=18, decimal_places=6)
    moneda_codigo = models.CharField(max_length=10)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(monto_recibido__gt=0), name="finalizacion_recibido_positivo"),
            models.CheckConstraint(condition=Q(fuente__in=["STRIPE_TEST", "VENTA_SIMULADA"]), name="finalizacion_fuente_valida"),
        ]


class OperacionCompletada(models.Model):
    """Punto persistido y deduplicado para futura facturación; no emite facturas."""
    operacion = models.OneToOneField("operaciones.Transaccion", on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
