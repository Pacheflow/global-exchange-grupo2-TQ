# Generated manually for HU-17.
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("monedas", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ConsultaProveedorTasas",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fuente", models.CharField(max_length=100)),
                ("fecha_hora_fuente", models.DateTimeField()),
                ("recibida_en", models.DateTimeField(auto_now_add=True)),
                ("respuesta", models.JSONField()),
                ("moneda_base", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="consultas_tasas", to="monedas.moneda")),
            ],
            options={
                "verbose_name": "consulta válida al proveedor de tasas",
                "verbose_name_plural": "consultas válidas al proveedor de tasas",
                "ordering": ("-recibida_en",),
            },
        ),
        migrations.CreateModel(
            name="TasaReferencia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valor", models.DecimalField(decimal_places=10, max_digits=24, validators=[django.core.validators.MinValueValidator(Decimal("0.0000000001"))])),
                ("fuente", models.CharField(max_length=100)),
                ("fecha_hora_fuente", models.DateTimeField()),
                ("vigente_hasta", models.DateTimeField()),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                ("consulta", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasas", to="tasas.consultaproveedortasas")),
                ("moneda_base", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasas_referencia_base", to="monedas.moneda")),
                ("moneda_cotizada", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasas_referencia_cotizada", to="monedas.moneda")),
            ],
            options={"ordering": ("moneda_base__codigo", "moneda_cotizada__codigo")},
        ),
        migrations.AddConstraint(
            model_name="tasareferencia",
            constraint=models.UniqueConstraint(fields=("moneda_base", "moneda_cotizada"), name="tasa_referencia_par_unico"),
        ),
        migrations.AddConstraint(
            model_name="tasareferencia",
            constraint=models.CheckConstraint(condition=~models.Q(moneda_base=models.F("moneda_cotizada")), name="tasa_referencia_monedas_distintas"),
        ),
        migrations.AddConstraint(
            model_name="tasareferencia",
            constraint=models.CheckConstraint(condition=models.Q(valor__gt=0), name="tasa_referencia_valor_positivo"),
        ),
    ]
