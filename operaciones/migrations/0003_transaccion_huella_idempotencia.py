from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operaciones", "0002_transaccion_completada"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaccion",
            name="huella_idempotencia",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=64,
                null=True,
            ),
        ),
    ]
