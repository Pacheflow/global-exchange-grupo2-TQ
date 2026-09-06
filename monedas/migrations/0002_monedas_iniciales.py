from django.db import migrations


MONEDAS_INICIALES = (
    ("USD", "Dólar estadounidense", "$"),
    ("PYG", "Guaraní paraguayo", "₲"),
    ("BRL", "Real brasileño", "R$"),
    ("EUR", "Euro", "€"),
    ("ARS", "Peso argentino", "$"),
)


def cargar_monedas_iniciales(apps, schema_editor):
    """Crea el catálogo mínimo sin duplicar ni sobrescribir monedas existentes."""

    moneda_model = apps.get_model("monedas", "Moneda")
    for codigo, nombre, simbolo in MONEDAS_INICIALES:
        moneda_model.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "simbolo": simbolo,
                "estado": "ACTIVA",
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("monedas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar_monedas_iniciales, migrations.RunPython.noop),
    ]
