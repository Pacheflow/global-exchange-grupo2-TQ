from django.db import models
from django.db.models.functions import Lower


class MetodoPagoQuerySet(models.QuerySet):
    """Consultas reutilizables para el catálogo global de métodos de pago."""

    def activos(self):
        """Devuelve únicamente los métodos disponibles para nuevas operaciones."""
        return self.filter(activo=True)


class MetodoPago(models.Model):
    """
    Representa una opción del catálogo global de métodos de pago.

    El catálogo no pertenece a clientes ni procesa pagos. Una operación futura
    podrá seleccionar uno de sus registros activos en el momento de operar.
    """

    nombre = models.CharField(
        max_length=100,
    )

    descripcion = models.TextField(
        blank=True,
    )

    activo = models.BooleanField(
        default=True,
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True,
    )

    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
    )

    objects = MetodoPagoQuerySet.as_manager()

    class Meta:
        ordering = ("nombre",)
        constraints = [
            models.UniqueConstraint(
                Lower("nombre"),
                name="metodo_pago_nombre_global_unico",
            ),
        ]

    def save(self, *args, **kwargs):
        """
        Normaliza el nombre antes de guardar el método de pago.

        Se eliminan espacios innecesarios al inicio y al final para
        evitar duplicados causados únicamente por diferencias de formato.
        """
        self.nombre = self.nombre.strip()
        self.descripcion = self.descripcion.strip()

        super().save(*args, **kwargs)

    def __str__(self):
        """Devuelve una representación legible del método de pago."""
        return self.nombre

    def activar(self):
        """Habilita el método de pago para nuevas operaciones."""
        self.activo = True
        self.save(update_fields=["activo", "fecha_actualizacion"])

    def desactivar(self):
        """
        Deshabilita el método de pago sin eliminar sus datos.

        La información se conserva para la trazabilidad de futuras operaciones.
        """
        self.activo = False
        self.save(update_fields=["activo", "fecha_actualizacion"])
