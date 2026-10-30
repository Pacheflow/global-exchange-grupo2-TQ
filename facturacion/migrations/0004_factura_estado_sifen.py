from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0003_rangonumeracionfiscal_numerofiscalasignado"),
    ]

    operations = [
        migrations.AddField(
            model_name="factura",
            name="estado_sifen",
            field=models.CharField(blank=True, editable=False, max_length=40),
        ),
        migrations.AddField(
            model_name="factura",
            name="descripcion_sifen",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="factura",
            name="error_sifen",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="factura",
            name="fecha_sifen",
            field=models.CharField(blank=True, editable=False, max_length=40),
        ),
        migrations.AddField(
            model_name="factura",
            name="consultada_sifen_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
