import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clientes", "0003_usuariocliente"),
        ("metodos_pago", "0002_catalogo_global"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="metodo_pago_preferido",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="clientes_preferentes",
                to="metodos_pago.metodopago",
            ),
        ),
    ]
