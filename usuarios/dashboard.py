"""Contrato único de métricas administrativas filtradas, sin fórmulas financieras."""
import re
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda
from operaciones import finanzas
from .graficos import presentar_graficos

PERIODOS = {
    "hoy": "Hoy", "semana": "Esta semana", "mes": "Este mes",
    "3meses": "Últimos 3 meses", "6meses": "Últimos 6 meses",
    "12meses": "Últimos 12 meses", "personalizado": "Personalizado",
}


def divisas_dashboard():
    """Catálogo vivo: solo divisas activas distintas de la moneda base PYG."""
    return list(Moneda.objects.filter(estado="ACTIVA").exclude(codigo="PYG")
                .order_by("codigo").values("codigo", "nombre"))


def validar_filtros(parametros, *, divisas, hoy=None):
    """Fechas inclusivas locales; máximo 366 días; rechaza filtros ambiguos."""
    hoy = hoy or timezone.localdate()
    if set(parametros) - {"periodo", "divisa", "desde", "hasta"}:
        raise ValidationError("Parámetro desconocido.")
    if any(len(parametros.getlist(k)) != 1 for k in parametros):
        raise ValidationError("No se permiten parámetros duplicados.")
    periodo = parametros.get("periodo", "personalizado" if "desde" in parametros or "hasta" in parametros else "mes")
    if periodo not in PERIODOS:
        raise ValidationError("Período inválido.")
    divisa = parametros.get("divisa", "")
    if divisa and divisa not in {m["codigo"] for m in divisas}:
        raise ValidationError("Seleccioná una divisa activa del catálogo o Todas.")
    if periodo == "personalizado":
        try:
            valores = [parametros.get(c, "") for c in ("desde", "hasta")]
            if not all(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v) for v in valores):
                raise ValueError
            desde, hasta = map(date.fromisoformat, valores)
        except ValueError:
            raise ValidationError("Completá ambas fechas válidas en formato YYYY-MM-DD.")
    else:
        if parametros.get("desde") or parametros.get("hasta"):
            raise ValidationError("Las fechas desde/hasta requieren el período Personalizado.")
        hasta = hoy
        if periodo == "hoy":
            desde = hoy
        elif periodo == "semana":
            desde = hoy - timedelta(days=hoy.weekday())
        else:
            desde = hoy.replace(day=1)
        if periodo in {"3meses", "6meses", "12meses"}:
            for _ in range(int(periodo.removesuffix("meses")) - 1):
                desde = (desde - timedelta(days=1)).replace(day=1)
    if desde > hasta or hasta == date.max or (hasta - desde).days >= finanzas.MAX_DIAS:
        raise ValidationError("El período debe estar ordenado y abarcar como máximo 366 días.")
    agrupacion = "mes" if periodo in {"3meses", "6meses", "12meses"} or (hasta - desde).days >= 62 else "dia"
    return dict(periodo=periodo, etiqueta=PERIODOS[periodo], divisa=divisa,
                desde=desde.isoformat(), hasta=hasta.isoformat(), agrupacion=agrupacion,
                zona_horaria=str(timezone.get_current_timezone()))


def consultar_dashboard_administrativo(filtros):
    """Una selección compartida para métricas, gráficos y cinco últimas completadas."""
    seleccion = dict(desde=date.fromisoformat(filtros["desde"]),
                     hasta=date.fromisoformat(filtros["hasta"]), divisa=filtros["divisa"] or None)
    reporte = finanzas.reporte_financiero(**seleccion, agrupacion=filtros["agrupacion"], incluir_distribucion=True)
    total = reporte["totales"]
    resumen = dict(ganancia_pyg=total["ganancia"], volumen_pyg=total["volumen"],
                   operaciones=total["operaciones"], compras=total["compras"], ventas=total["ventas"],
                   excluidas=total["operaciones_sin_conversion"], moneda="PYG")
    evolucion, distribucion = presentar_graficos(reporte, divisa=filtros["divisa"])
    recientes = finanzas.operaciones_completadas(**seleccion).select_related(
        "cliente", "moneda_origen", "moneda_destino").order_by("-fecha_creacion", "-pk")[:5]
    actividad = [dict(id=op.pk, fecha=timezone.localtime(op.fecha_creacion).strftime("%d/%m/%Y %H:%M"),
                      cliente=op.cliente.nombre_razon_social, tipo=op.get_tipo_display(), estado=op.get_estado_display(),
                      origen=str(op.monto_origen), divisa_origen=op.moneda_origen.codigo,
                      destino=str(op.monto_destino), divisa_destino=op.moneda_destino.codigo,
                      detalle=reverse("operaciones_web:detalle_reporte_transaccion", args=[op.pk])) for op in recientes]
    return dict(version=1, filtros=filtros, resumen=resumen, evolucion=evolucion,
                distribucion=distribucion, actividad_reciente=actividad,
                advertencias=reporte["advertencias"], fecha_imputacion="fecha_creacion")
