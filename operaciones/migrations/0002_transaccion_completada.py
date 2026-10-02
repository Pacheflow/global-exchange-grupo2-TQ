from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("operaciones", "0001_initial"),
        ("tasas", "0003_tasacomercial_precision"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaccion",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("COMPLETADA", "Completada"),
                    ("CANCELADA", "Cancelada"),
                ],
                default="PENDIENTE",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="transaccion",
            name="tasa_aplicada",
            field=models.DecimalField(decimal_places=10, max_digits=24),
        ),
        migrations.RemoveConstraint(
            model_name="transaccion",
            name="transaccion_pendiente_sin_cancelacion",
        ),
        migrations.AddConstraint(
            model_name="transaccion",
            constraint=models.CheckConstraint(
                condition=(
                    Q(estado="CANCELADA")
                    | (
                        Q(cancelado_por_keycloak_id__isnull=True)
                        & Q(cancelado_por_username__isnull=True)
                        & Q(cancelado_en__isnull=True)
                        & Q(motivo_cancelacion__isnull=True)
                    )
                ),
                name="transaccion_no_cancelada_sin_cancelacion",
            ),
        ),
    ]
