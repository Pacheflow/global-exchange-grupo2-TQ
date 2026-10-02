from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
from django.db.models import Q


def configurar_comisiones_iniciales(apps, schema_editor):
    CategoriaCliente = apps.get_model("clientes", "CategoriaCliente")
    porcentajes = {
        "MINORISTA": Decimal("10.00"),
        "CORPORATIVO": Decimal("7.00"),
        "VIP": Decimal("5.00"),
    }
    for nombre, porcentaje in porcentajes.items():
        CategoriaCliente.objects.filter(nombre__iexact=nombre).update(
            porcentaje_comision=porcentaje
        )


class Migration(migrations.Migration):
    dependencies = [("clientes", "0004_cliente_metodo_pago_preferido")]

    operations = [
        migrations.AddField(
            model_name="categoriacliente",
            name="porcentaje_comision",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=5,
                validators=[
                    MinValueValidator(Decimal("0.00")),
                    MaxValueValidator(Decimal("100.00")),
                ],
            ),
        ),
        migrations.RunPython(configurar_comisiones_iniciales, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="categoriacliente",
            constraint=models.CheckConstraint(
                condition=Q(
                    porcentaje_comision__gte=0,
                    porcentaje_comision__lte=100,
                ),
                name="categoria_comision_entre_0_y_100",
            ),
        ),
    ]
