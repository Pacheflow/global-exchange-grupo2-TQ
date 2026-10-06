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
