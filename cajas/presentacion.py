"""Indicadores informativos de UI. El servicio revalida al confirmar bajo lock."""
from .models import CierreCaja


def contexto_acciones_periodo(periodo):
    """Consulta requisitos de cierre sin bloquear, reservar ni escribir.

    cerrar_caja no expone un helper de elegibilidad reutilizable. Esta lectura
    conserva sus condiciones; no reemplaza su autorización ni su validación.
    """
    motivo = ""
    if periodo.estado != "ABIERTO":
        motivo = "El período está cerrado."
    else:
        arqueo = periodo.arqueos.order_by("-fecha_arqueo", "-id").first()
        if arqueo is None:
            motivo = "Realizá primero un arqueo válido."
        elif periodo.movimientos.filter(fecha_registro__gt=arqueo.fecha_arqueo).exists():
            motivo = "Existen movimientos posteriores al último arqueo. Volvé a realizar el arqueo antes de cerrar."
        elif CierreCaja.objects.filter(periodo=periodo).exists():
            motivo = "Este período ya fue cerrado."
    return {"puede_cerrar": not motivo, "motivo_no_cierre": motivo}
