from django.db import models


from clientes.models import Cliente
class MetodoPagoQuerySet(models.QuerySet):
    """Consultas reutilizables para los métodos de pago."""

    def activos(self):
        """Devuelve únicamente los métodos disponibles para nuevas operaciones."""
        return self.filter(estado="ACTIVO")


class MetodoPago(models.Model):
    """
    Representa un método de pago configurado para un cliente.

    La entidad permite registrar y administrar los métodos de pago
    disponibles para el cliente sin realizar procesamiento real
    de pagos.
    """

    TIPOS_METODO = [
        ("EFECTIVO", "Efectivo"),
        ("TARJETA", "Tarjeta"),
        ("TRANSFERENCIA", "Transferencia"),
        ("OTRO", "Otro"),
    ]

    ESTADOS_METODO = [
        ("ACTIVO", "Activo"),
        ("INACTIVO", "Inactivo"),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="metodos_pago",
    )

    nombre = models.CharField(
        max_length=100,
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPOS_METODO,
    )

    estado = models.CharField(
        max_length=10,
        choices=ESTADOS_METODO,
        default="ACTIVO",
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
                fields=("cliente", "nombre"),
                name="cliente_metodo_pago_nombre_unico",
            ),
        ]

    def save(self, *args, **kwargs):
        """
        Normaliza el nombre antes de guardar el método de pago.

        Se eliminan espacios innecesarios al inicio y al final para
        evitar duplicados causados únicamente por diferencias de formato.
        """
        self.nombre = self.nombre.strip()

        super().save(*args, **kwargs)

    def __str__(self):
        """Devuelve una representación legible del método de pago."""
        return f"{self.nombre} - {self.cliente}"

    def activar(self):
        """Habilita el método de pago para nuevas operaciones."""
        self.estado = "ACTIVO"
        self.save(update_fields=["estado", "fecha_actualizacion"])

    def desactivar(self):
        """
        Deshabilita el método de pago sin eliminar sus datos.

        La información se conserva para mantener el historial
        de configuración del cliente.
        """
        self.estado = "INACTIVO"
        self.save(update_fields=["estado", "fecha_actualizacion"])
