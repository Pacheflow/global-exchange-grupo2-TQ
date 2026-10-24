from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("metodos_pago", "0002_catalogo_global")]
    operations = [
        migrations.AddField(model_name="metodopago", name="naturaleza",
            field=models.CharField(max_length=14, default="SIN_CLASIFICAR", choices=[
                ("SIN_CLASIFICAR", "Sin clasificar"), ("ELECTRONICO", "Electrónico (Stripe TEST)"),
                ("EFECTIVO", "Efectivo / metálico")])),
        migrations.AddConstraint(model_name="metodopago", constraint=models.CheckConstraint(
            condition=models.Q(naturaleza__in=["SIN_CLASIFICAR", "ELECTRONICO", "EFECTIVO"]),
            name="metodo_pago_naturaleza_valida")),
    ]
