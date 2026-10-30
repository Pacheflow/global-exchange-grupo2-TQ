from django.db import models
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.db import transaction


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

    class Naturaleza(models.TextChoices):
        SIN_CLASIFICAR = "SIN_CLASIFICAR", "Sin clasificar"
        ELECTRONICO = "ELECTRONICO", "Electrónico (Stripe TEST)"
        EFECTIVO = "EFECTIVO", "Efectivo / metálico"

    naturaleza = models.CharField(max_length=14, choices=Naturaleza.choices, default=Naturaleza.SIN_CLASIFICAR)

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
            models.CheckConstraint(condition=models.Q(naturaleza__in=["SIN_CLASIFICAR", "ELECTRONICO", "EFECTIVO"]),
                                   name="metodo_pago_naturaleza_valida"),
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
        Una naturaleza ya clasificada no puede redefinirse con referencias;
        la primera clasificación explícita de registros heredados sí se admite.
        Los nuevos métodos activos y las activaciones exigen un tipo explícito;
        los registros heredados no se reclasifican ni deshabilitan automáticamente.
        """
        self.nombre = self.nombre.strip()
        self.descripcion = self.descripcion.strip()

        with transaction.atomic():
            anterior = None
            if self.pk:
                anterior = type(self).objects.select_for_update().filter(pk=self.pk).first()
                cambia_naturaleza = kwargs.get("update_fields") is None or "naturaleza" in kwargs["update_fields"]
                if (anterior and cambia_naturaleza and anterior.naturaleza != self.naturaleza
                    and anterior.naturaleza != self.Naturaleza.SIN_CLASIFICAR
                    and self.tiene_referencias()):
                    raise ValidationError("No se puede cambiar la naturaleza de un método con operaciones o pagos.")
            campos = kwargs.get("update_fields")
            naturaleza_guardada = (
                anterior.naturaleza if anterior and campos is not None and "naturaleza" not in campos
                else self.naturaleza
            )
            activo_guardado = (
                anterior.activo if anterior and campos is not None and "activo" not in campos
                else self.activo
            )
            if naturaleza_guardada not in self.Naturaleza.values:
                raise ValidationError({"naturaleza": "El tipo del método no es válido."})
            if (activo_guardado and naturaleza_guardada == self.Naturaleza.SIN_CLASIFICAR
                and (anterior is None or not anterior.activo
                     or anterior.naturaleza != self.Naturaleza.SIN_CLASIFICAR)):
                raise ValidationError({
                    "naturaleza": "Seleccioná Electrónico o Efectivo antes de activar el método de pago."
                })
            super().save(*args, **kwargs)

    def tiene_referencias(self):
        """Incluye operaciones, pagos y métodos anteriores conservados por HU-27."""
        return (self.transacciones.exists() or self.pagos.exists()
                or self.cambios_salientes.exists() or self.cambios_entrantes.exists())

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
