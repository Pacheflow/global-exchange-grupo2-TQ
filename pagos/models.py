"""Evidencia persistida del pago; el modelo no inicia cobros."""

import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware


class EventoStripe(models.Model):
    """Registro histórico inerte: conserva la tabla y FK de la migración ya aplicada.

    No existe recepción, procesamiento ni recuperación periódica de eventos.
    """
    identificador = models.CharField(max_length=255, unique=True)
    pago = models.ForeignKey("Pago", on_delete=models.PROTECT)
    resultado = models.JSONField()
    recibido_en = models.DateTimeField(auto_now_add=True)
    procesado_en = models.DateTimeField(null=True)


class Pago(models.Model):
    class Estado(models.TextChoices):
        EN_PROCESO = "EN_PROCESO", "En proceso"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        ERROR = "ERROR", "Error sin ejecución"
        INDETERMINADO = "INDETERMINADO", "Resultado indeterminado"

    class BaseImporte(models.TextChoices):
        ORIGEN = "ORIGEN", "Origen"
        DESTINO = "DESTINO", "Destino"

    CAMPOS_INMUTABLES = (
        "transaccion_id", "metodo_pago_id", "proveedor", "monto",
        "moneda_codigo", "base_importe", "huella_solicitud",
        "iniciado_por_keycloak_id",
    )
    CODIGOS_TRAZABILIDAD = frozenset({
        "RESERVADO", "APROBADO", "RECHAZADO", "ERROR_SIN_EJECUCION",
        "RESULTADO_DESCONOCIDO", "CONSULTADO", "REINTENTO",
    })
    MAX_EVENTOS_TRAZABILIDAD = 50
    MAX_BYTES_TRAZABILIDAD = 8192

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaccion = models.OneToOneField(
        "operaciones.Transaccion", on_delete=models.PROTECT, related_name="pago",
    )
    metodo_pago = models.ForeignKey(
        "metodos_pago.MetodoPago", on_delete=models.PROTECT, related_name="pagos",
    )
    proveedor = models.CharField(
        max_length=30,
        validators=[RegexValidator(r"\A[a-z][a-z0-9_-]*\Z", "Identificador técnico inválido.")],
    )
    monto = models.DecimalField(max_digits=18, decimal_places=6)
    moneda_codigo = models.CharField(max_length=10, editable=False)
    base_importe = models.CharField(max_length=7, choices=BaseImporte.choices)
    huella_solicitud = models.CharField(max_length=64, editable=False)
    estado = models.CharField(
        max_length=13, choices=Estado.choices, default=Estado.EN_PROCESO,
    )
    referencia_externa = models.CharField(max_length=255, null=True, blank=True)
    iniciado_por_keycloak_id = models.CharField(max_length=255, editable=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    aprobado_en = models.DateTimeField(null=True, blank=True)
    trazabilidad = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("-fecha_creacion",)
        constraints = [
            models.CheckConstraint(
                condition=Q(monto__gt=0) & Q(monto__lt=Decimal("1000000000000")),
                name="pago_monto_positivo",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["EN_PROCESO", "APROBADO", "RECHAZADO", "ERROR", "INDETERMINADO"]),
                name="pago_estado_valido",
            ),
            models.CheckConstraint(
                condition=Q(base_importe__in=["ORIGEN", "DESTINO"]),
                name="pago_base_importe_valida",
            ),
            models.CheckConstraint(
                condition=~Q(estado="APROBADO") | (
                    Q(referencia_externa__isnull=False)
                    & ~Q(referencia_externa="") & Q(aprobado_en__isnull=False)
                ),
                name="pago_aprobado_con_referencia_fecha",
            ),
            models.CheckConstraint(
                condition=Q(referencia_externa__isnull=True) | ~Q(referencia_externa=""),
                name="pago_referencia_no_vacia",
            ),
            models.UniqueConstraint(
                fields=["proveedor", "referencia_externa"],
                condition=Q(referencia_externa__isnull=False),
                name="pago_referencia_proveedor_unica",
            ),
        ]

    def calcular_huella(self):
        """SHA-256 de los identificadores y snapshots, sin secretos del proveedor."""
        try:
            valor = self._meta.get_field("monto").clean(self.monto, self)
            monto = format(valor, ".6f")
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError({"monto": "Importe inválido."}) from None
        datos = {
            "pago_id": str(self.pk), "transaccion_id": str(self.transaccion_id),
            "metodo_pago_id": str(self.metodo_pago_id), "proveedor": self.proveedor,
            "monto": monto, "moneda_codigo": self.moneda_codigo,
            "base_importe": self.base_importe,
            "iniciado_por_keycloak_id": self.iniciado_por_keycloak_id,
        }
        contenido = json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(contenido.encode("utf-8")).hexdigest()

    def _validar_trazabilidad(self):
        error = "Trazabilidad inválida: solo fecha, estado y código controlados."
        if not isinstance(self.trazabilidad, list) or len(self.trazabilidad) > self.MAX_EVENTOS_TRAZABILIDAD:
            raise ValidationError({"trazabilidad": error})
        for evento in self.trazabilidad:
            if not isinstance(evento, dict) or set(evento) != {"fecha", "estado", "codigo"}:
                raise ValidationError({"trazabilidad": error})
            if not all(isinstance(valor, str) for valor in evento.values()):
                raise ValidationError({"trazabilidad": error})
            try:
                fecha = parse_datetime(evento["fecha"])
            except ValueError:
                fecha = None
            if (
                fecha is None or not is_aware(fecha)
                or evento["estado"] not in self.Estado.values
                or evento["codigo"] not in self.CODIGOS_TRAZABILIDAD
            ):
                raise ValidationError({"trazabilidad": error})
        serializado = json.dumps(self.trazabilidad, ensure_ascii=False).encode("utf-8")
        if len(serializado) > self.MAX_BYTES_TRAZABILIDAD:
            raise ValidationError({"trazabilidad": "La trazabilidad supera 8192 bytes."})

    def clean(self):
        super().clean()
        self._validar_trazabilidad()
        errores = {}
        if not self.iniciado_por_keycloak_id or not self.iniciado_por_keycloak_id.strip():
            errores["iniciado_por_keycloak_id"] = "La identidad del iniciador es obligatoria."
        original = None
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values(*self.CAMPOS_INMUTABLES, "estado").first()
        if original:
            for campo in self.CAMPOS_INMUTABLES:
                if getattr(self, campo) != original[campo]:
                    nombre = campo.removesuffix("_id") if campo in ("transaccion_id", "metodo_pago_id") else campo
                    errores[nombre] = "El snapshot del pago es inmutable."
            if original["estado"] in (self.Estado.APROBADO, self.Estado.RECHAZADO) and self.estado != original["estado"]:
                errores["estado"] = "El estado terminal del pago no puede cambiar."
        elif not self._state.adding:
            errores["id"] = "No se puede cambiar la identidad de un pago persistido."
        elif self.transaccion_id:
            try:
                transaccion = self.transaccion
            except ObjectDoesNotExist:
                transaccion = None
            if transaccion:
                if transaccion.tipo != "COMPRA" or transaccion.estado != "PENDIENTE":
                    errores["transaccion"] = "Solo se crea un pago para una COMPRA PENDIENTE."
                if self.metodo_pago_id != transaccion.metodo_pago_id:
                    errores["metodo_pago"] = "El método debe coincidir con la transacción."
                if self.monto != transaccion.monto_origen:
                    errores["monto"] = "El importe debe coincidir con el monto de origen."
                if self.moneda_codigo != transaccion.moneda_origen.codigo:
                    errores["moneda_codigo"] = "La moneda debe coincidir con la moneda de origen."
                if self.base_importe != self.BaseImporte.ORIGEN:
                    errores["base_importe"] = "La COMPRA se paga sobre el importe de origen."
        if self.huella_solicitud != self.calcular_huella():
            errores["huella_solicitud"] = "La huella no coincide con los snapshots del pago."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        """Valida escrituras individuales; update/bulk/SQL no ejecutan este método."""
        self.monto = self._meta.get_field("monto").clean(self.monto, self)
        if self.referencia_externa is not None:
            self.referencia_externa = self.referencia_externa.strip() or None
        if self._state.adding and not self.huella_solicitud:
            self.huella_solicitud = self.calcular_huella()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Pago {self.pk} ({self.estado})"
