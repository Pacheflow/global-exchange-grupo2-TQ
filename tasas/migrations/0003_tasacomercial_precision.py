from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tasas", "0002_tasacomercial")]

    operations = [
        migrations.AlterField(
            model_name="tasacomercial",
            name="compra",
            field=models.DecimalField(decimal_places=10, max_digits=24),
        ),
        migrations.AlterField(
            model_name="tasacomercial",
            name="venta",
            field=models.DecimalField(decimal_places=10, max_digits=24),
        ),
    ]
