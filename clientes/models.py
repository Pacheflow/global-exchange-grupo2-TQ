from django.db import models


class CategoriaCliente(models.Model):
    """Representa una categoría comercial asignable a los clientes."""

    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return self.nombre


class Cliente(models.Model):
    """Representa un cliente de Global Exchange.

    Guarda información como tipo de persona, documento,
    estado y categoría comercial.
    """

    TIPOS_PERSONA = [
        ('FISICA', 'Persona Física'),
        ('JURIDICA', 'Persona Jurídica'),
    ]

    ESTADOS_CLIENTE = [
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    ]

    nombre_razon_social = models.CharField(max_length=150)

    tipo_persona = models.CharField(
        max_length=10,
        choices=TIPOS_PERSONA
    )

    documento = models.CharField(
        max_length=30,
        unique=True
    )

    estado = models.CharField(
        max_length=10,
        choices=ESTADOS_CLIENTE,
        default='ACTIVO'
    )

    categoria = models.ForeignKey(
        CategoriaCliente,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    metodo_pago_preferido = models.ForeignKey(
        "metodos_pago.MetodoPago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clientes_preferentes",
    )

    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre_razon_social

    def activar(self):
        """Cambia el estado del cliente a ACTIVO."""
        self.estado = 'ACTIVO'
        self.save()

    def dar_de_baja(self):
        """Cambia el estado del cliente a INACTIVO sin eliminarlo."""
        self.estado = 'INACTIVO'
        self.save()


class UsuarioCliente(models.Model):
    """Asociación persistente entre una identidad Keycloak y un cliente."""

    ROLES = [
        ("RESPONSABLE", "Responsable"),
        ("OPERADOR", "Operador"),
        ("CONSULTA", "Solo consulta"),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="usuarios_asignados",
    )
    keycloak_user_id = models.CharField(max_length=64)
    username = models.CharField(max_length=150)
    rol_en_cliente = models.CharField(max_length=20, choices=ROLES, default="OPERADOR")
    activo = models.BooleanField(default=True)
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("cliente", "keycloak_user_id"),
                name="cliente_usuario_keycloak_unico",
            )
        ]
        ordering = ("username",)

    def __str__(self):
        return f"{self.username} · {self.cliente}"
