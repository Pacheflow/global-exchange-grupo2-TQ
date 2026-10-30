from collections import Counter
from django.core.validators import RegexValidator
from django.db import migrations, models
import re


def separar_ruc_dv(apps, schema_editor):
    Cliente = apps.get_model("clientes", "Cliente")
    clientes = Cliente.objects.using(schema_editor.connection.alias)
    candidates = list(clientes.filter(tipo_persona="JURIDICA").values_list("documento", flat=True))
    bases = Counter(match[1] for documento in candidates
                    if (match := re.fullmatch(r"([0-9]+)-([0-9])", documento)))
    for cliente in clientes.filter(tipo_persona="JURIDICA").iterator():
        match = re.fullmatch(r"([0-9]+)-([0-9])", cliente.documento)
        if match and bases[match[1]] == 1 and not clientes.filter(documento=match[1]).exists():
            clientes.filter(pk=cliente.pk).update(documento=match[1], dv=match[2])


class Migration(migrations.Migration):
    dependencies = [("clientes", "0006_cliente_correo_facturacion")]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="dv",
            field=models.CharField(blank=True, max_length=1, validators=[
                RegexValidator(r"\A[0-9]\Z", "El DV debe ser un dígito del 0 al 9.")
            ]),
        ),
        # Sin reconstrucción inversa: no hay forma de distinguir registros creados
        # después de la separación. El número base se conserva al revertir el campo.
        migrations.RunPython(separar_ruc_dv, migrations.RunPython.noop),
    ]
