"""Clasificación explícita por identificadores revisados; nunca infiere nombres."""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from metodos_pago.models import MetodoPago


class Command(BaseCommand):
    help = "Muestra el plan de clasificación ID=NATURALEZA; solo escribe con --aplicar."

    def add_arguments(self, parser):
        """Cada asignación es explícita y la escritura requiere una opción independiente."""
        parser.add_argument("--asignacion", action="append", required=True)
        parser.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **options):
        """Valida todo el plan; aplica atómicamente sin cambiar activo ni snapshots históricos."""
        plan = {}
        try:
            for dato in options["asignacion"]:
                identidad, naturaleza = dato.split("=", 1)
                identidad = int(identidad)
                if identidad <= 0 or identidad in plan or naturaleza not in {"ELECTRONICO", "EFECTIVO"}:
                    raise ValueError
                plan[identidad] = naturaleza
        except (ValueError, TypeError):
            raise CommandError("Usá asignaciones únicas ID=ELECTRONICO o ID=EFECTIVO.") from None
        try:
            with transaction.atomic():
                metodos = list(MetodoPago.objects.select_for_update().filter(pk__in=plan).order_by("pk"))
                if len(metodos) != len(plan):
                    raise CommandError("El plan contiene métodos inexistentes.")
                for metodo in metodos:
                    if (metodo.naturaleza not in {MetodoPago.Naturaleza.SIN_CLASIFICAR, plan[metodo.pk]}
                        and metodo.tiene_referencias()):
                        raise CommandError("El plan redefine un método con referencias históricas.")
                    self.stdout.write(f"{metodo.pk}: {metodo.nombre} | {metodo.naturaleza} -> {plan[metodo.pk]} | activo={metodo.activo}")
                if options["aplicar"]:
                    for metodo in metodos:
                        metodo.naturaleza = plan[metodo.pk]
                        metodo.save(update_fields=["naturaleza", "fecha_actualizacion"])
                self.stdout.write("Clasificación aplicada." if options["aplicar"] else "Solo revisión: no se modificaron datos.")
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from None
