from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="IntentoEmisionFacturaSegura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("clave_idempotencia", models.CharField(editable=False, max_length=255, unique=True)),
                ("huella_documento", models.CharField(editable=False, max_length=64)),
                ("estado", models.CharField(choices=[
                    ("EN_PROCESO", "En proceso"), ("GENERADA", "Generada por el proveedor"),
                    ("INDETERMINADA", "Resultado indeterminado"), ("ERROR", "Error confirmado sin resultado"),
                ], default="EN_PROCESO", max_length=14)),
                ("cdc", models.CharField(blank=True, editable=False, max_length=64, null=True, unique=True)),
                ("operacion_id", models.CharField(blank=True, editable=False, max_length=255)),
                ("codigo_proveedor", models.IntegerField(blank=True, editable=False, null=True)),
                ("descripcion_proveedor", models.TextField(blank=True, editable=False)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("-creado_en", "-id"),
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(estado__in=["EN_PROCESO", "GENERADA", "INDETERMINADA", "ERROR"]),
                        name="factura_segura_intento_estado_valido",
                    ),
                    models.CheckConstraint(
                        condition=~Q(estado="GENERADA") | (Q(cdc__isnull=False) & ~Q(cdc="")),
                        name="factura_segura_generada_con_cdc",
                    ),
                ],
            },
        ),
    ]
