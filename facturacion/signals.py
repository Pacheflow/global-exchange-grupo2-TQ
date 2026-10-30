"""Preparación posterior al commit, común a operaciones online y presenciales."""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from fondos.models import OperacionCompletada
from .services.facturas import preparar_despues_de_commit


@receiver(post_save, sender=OperacionCompletada, dispatch_uid="facturacion.operacion_completada")
def operacion_completada(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        transaction.on_commit(lambda: preparar_despues_de_commit(instance.operacion_id), robust=True)
