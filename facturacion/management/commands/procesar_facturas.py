"""Procesador invocable por scheduler; recupera eventos y prepara comprobantes para la web."""
from django.core.management.base import BaseCommand, CommandError
from fondos.models import OperacionCompletada
from facturacion.models import Factura
from facturacion.services.facturas import preparar_factura, emitir_factura


class Command(BaseCommand):
    help = "Prepara y procesa facturas pendientes; requiere contrato fiscal configurado para emitir."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=100)

    def handle(self, *args, **options):
        limite = options["limite"]
        if limite < 1:
            raise CommandError("El límite debe ser positivo.")
        eventos = OperacionCompletada.objects.filter(operacion__estado="COMPLETADA", operacion__factura__isnull=True).order_by("pk")[:limite]
        for evento in eventos:
            preparar_factura(evento.operacion_id)
        ids = list(Factura.objects.filter(estado="PENDIENTE").order_by("pk").values_list("pk", flat=True)[:limite])
        for pk in ids:
            emitir_factura(pk)
        self.stdout.write(f"Procesadas {len(ids)} facturas pendientes para consulta en la web.")
