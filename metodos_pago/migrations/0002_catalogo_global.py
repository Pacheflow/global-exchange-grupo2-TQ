from django.db import migrations, models
from django.db.models.functions import Lower


def consolidar_catalogo_global(apps, schema_editor):
    """
    Convierte asignaciones por cliente en métodos globales sin duplicar nombres.

    Conserva el registro más antiguo de cada nombre normalizado y lo mantiene
    activo cuando al menos una asignación anterior estaba activa. Los campos
    ``cliente`` y ``tipo`` se eliminan después de esta consolidación.
    """
    metodo_pago = apps.get_model("metodos_pago", "MetodoPago")
    registros = list(metodo_pago.objects.order_by("id"))

    if any(not registro.nombre.strip() for registro in registros):
        raise RuntimeError(
            "No se puede migrar el catálogo: existe un método de pago sin nombre."
        )

    canonicos = {}
    for registro in registros:
        nombre = registro.nombre.strip()
        clave = nombre.casefold()
        canonico = canonicos.get(clave)
        if canonico is None:
            registro.nombre = nombre
            registro.activo = registro.estado == "ACTIVO"
            registro.save(update_fields=["nombre", "activo"])
            canonicos[clave] = registro
            continue

        if registro.estado == "ACTIVO" and not canonico.activo:
            canonico.activo = True
            canonico.save(update_fields=["activo"])
        registro.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("metodos_pago", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="metodopago",
            name="cliente_metodo_pago_nombre_unico",
        ),
        migrations.AddField(
            model_name="metodopago",
            name="descripcion",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="metodopago",
            name="activo",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(
            consolidar_catalogo_global,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="metodopago",
            name="cliente",
        ),
        migrations.RemoveField(
            model_name="metodopago",
            name="tipo",
        ),
        migrations.RemoveField(
            model_name="metodopago",
            name="estado",
        ),
        migrations.AddConstraint(
            model_name="metodopago",
            constraint=models.UniqueConstraint(
                Lower("nombre"),
                name="metodo_pago_nombre_global_unico",
            ),
        ),
    ]
