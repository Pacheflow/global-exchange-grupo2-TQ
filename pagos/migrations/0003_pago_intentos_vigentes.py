"""Conserva UUID, snapshots y trazabilidad de todos los pagos existentes."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pagos", "0002_eventostripe")]
    operations = [
        migrations.AddField(model_name="pago", name="vigente", field=models.BooleanField(default=True, editable=False)),
        migrations.AlterField(model_name="pago", name="transaccion", field=models.ForeignKey(
            on_delete=django.db.models.deletion.PROTECT, related_name="intentos_pago", to="operaciones.transaccion")),
        migrations.AddConstraint(model_name="pago", constraint=models.UniqueConstraint(
            fields=("transaccion",), condition=models.Q(vigente=True), name="pago_vigente_unico_por_transaccion")),
        migrations.AddConstraint(model_name="pago", constraint=models.CheckConstraint(
            condition=(models.Q(vigente=True) | models.Q(estado="RECHAZADO")
                       | models.Q(estado="ERROR", referencia_externa__isnull=True)),
            name="pago_archivado_sin_ejecucion")),
    ]
