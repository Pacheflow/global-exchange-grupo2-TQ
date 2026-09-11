from django.db import models


class MonedaQuerySet(models.QuerySet):
    """Consultas reutilizables para el catálogo de monedas."""

    def activas(self):
        """Devuelve únicamente las monedas disponibles para nuevas operaciones."""
        return self.filter(estado="ACTIVA")


class Moneda(models.Model):
    """
    Representa una moneda disponible para operaciones
    de Global Exchange.
    """

    ESTADOS_MONEDA = [
        ("ACTIVA", "Activa"),
        ("INACTIVA", "Inactiva"),
    ]

    codigo = models.CharField(
        max_length=10,
        unique=True,
    )

    nombre = models.CharField(
        max_length=100,
    )

    simbolo = models.CharField(
        max_length=10,
    )

    estado = models.CharField(
        max_length=10,
        choices=ESTADOS_MONEDA,
        default="ACTIVA",
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    fecha_actualizacion = models.DateTimeField(
        auto_now=True
    )

    objects = MonedaQuerySet.as_manager()

    class Meta:
        ordering = ("codigo",)

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.strip().upper()
        self.nombre = self.nombre.strip()
        self.simbolo = self.simbolo.strip()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def activar(self):
        """Habilita nuevamente una moneda."""
        self.estado = "ACTIVA"
        self.save()

    def desactivar(self):
        """Deshabilita una moneda sin eliminarla."""
        self.estado = "INACTIVA"
        self.save()