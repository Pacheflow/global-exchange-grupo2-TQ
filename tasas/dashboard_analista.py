"""Lectura de mercado para el analista: sin importes ni identidades de operaciones."""
import logging
from collections import Counter
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from monedas.models import Moneda
from operaciones.finanzas import operaciones_completadas
from usuarios.dashboard import PERIODOS, divisas_dashboard, validar_filtros
from usuarios.decorators import requiere_rol
from .historico import consultar_registros
from .models import TasaComercial
from .simulador import simular_conversion


def numero(valor):
    texto = format(valor, "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def consultar_dashboard_analista(filtros):
    """Histórico comercial observado en el intervalo y fotografía vigente separada."""
    activas = {m.codigo: m for m in Moneda.objects.filter(estado="ACTIVA").order_by("codigo")}
    codigos = [c for c in activas if c != "PYG" and (not filtros["divisa"] or c == filtros["divisa"])]
    pyg = activas.get("PYG")
    desde, hasta = (date.fromisoformat(filtros[k]) for k in ("desde", "hasta"))
    ahora = timezone.now()
    referencias = {}
    for codigo in ("USD", "EUR"):
        referencia = None
        if pyg and codigo in activas:
            try:
                resultado = simular_conversion(activas[codigo].pk, pyg.pk, "1")
                referencia = dict(valor=numero(resultado.tasa), fecha=resultado.fecha_hora.isoformat())
            except ValidationError:
                pass
        referencias[codigo] = referencia

    vigentes = list(TasaComercial.objects.filter(
        vigente=True, moneda_origen__codigo__in=codigos,
        moneda_destino=pyg,
    ).select_related("moneda_origen").order_by("moneda_origen__codigo", "-fecha_registro", "-pk")) if pyg else []
    mercado, variaciones, series = [], [], {}
    for codigo in codigos:
        registros = list(consultar_registros(dict(moneda_origen_id=activas[codigo],
            moneda_destino_id=pyg, desde=desde, hasta=hasta))) if pyg else []
        variacion = None
        if len(registros) >= 2 and registros[0].compra > 0:
            inicial, final = registros[0], registros[-1]
            variacion = dict(divisa=codigo, par=f"{codigo}/PYG",
                porcentaje=numero((final.compra - inicial.compra) / inicial.compra * 100),
                absoluta=numero(final.compra - inicial.compra),
                inicial=numero(inicial.compra), final=numero(final.compra),
                desde=inicial.fecha_registro.isoformat(), hasta=final.fecha_registro.isoformat())
        variaciones.append(dict(divisa=codigo, par=f"{codigo}/PYG", variacion=variacion))
        # Última versión real de cada día + primer extremo real: como máximo 367 puntos.
        por_dia = {}
        for row in registros:
            por_dia[timezone.localtime(row.fecha_registro).date()] = row
        puntos = list(por_dia.values())
        if registros and puntos[0].pk != registros[0].pk:
            puntos.insert(0, registros[0])
        series[codigo] = [dict(fecha=r.fecha_registro.isoformat(), compra=numero(r.compra), venta=numero(r.venta)) for r in puntos]
        vigente = next((r for r in vigentes if r.moneda_origen.codigo == codigo), None)
        if vigente:
            mercado.append(dict(divisa=codigo, par=f"{codigo}/PYG",
                compra=numero(vigente.compra), venta=numero(vigente.venta),
                spread=numero(vigente.venta - vigente.compra),
                variacion=variacion, fecha=vigente.fecha_registro.isoformat()))

    conteos, tipos = Counter(), Counter()
    operaciones = operaciones_completadas(desde=desde, hasta=hasta, divisa=filtros["divisa"] or None)
    total_operaciones = 0
    for origen, destino, tipo in operaciones.values_list("moneda_origen__codigo", "moneda_destino__codigo", "tipo").iterator():
        total_operaciones += 1
        tipos[tipo] += 1
        for codigo in {origen, destino}.intersection(codigos):
            conteos[codigo] += 1
    especifica = bool(filtros["divisa"])
    categorias = [("Compra", tipos["COMPRA"]), ("Venta", tipos["VENTA"])] if especifica else sorted(conteos.items())
    total = sum(cantidad for _, cantidad in categorias)
    distribucion = dict(modo="tipo" if especifica else "divisa", total=total,
        categorias=[dict(nombre=nombre, cantidad=cantidad, porcentaje=numero(Decimal(cantidad) * 100 / total) if total else "0")
                    for nombre, cantidad in categorias if cantidad])
    mayor = max((v["variacion"] for v in variaciones if v["variacion"]),
                key=lambda v: abs(Decimal(v["porcentaje"])), default=None)
    mas_operada = sorted(conteos.items(), key=lambda item: (-item[1], item[0]))
    fechas = [r.fecha_registro for r in vigentes]
    grafico = filtros["divisa"] or ("USD" if "USD" in codigos else next(iter(codigos), ""))
    return dict(version=1, filtros=filtros, referencias=referencias,
        resumen=dict(mayor_variacion=mayor,
            divisa_mas_operada=dict(divisa=mas_operada[0][0], operaciones=mas_operada[0][1]) if mas_operada else None,
            tasas_vigentes=len(vigentes), ultima_actualizacion=max(fechas).isoformat() if fechas else None,
            operaciones=total_operaciones, compras=tipos["COMPRA"], ventas=tipos["VENTA"]),
        evolucion=dict(divisa=grafico, par=f"{grafico}/PYG" if grafico else "", puntos=series.get(grafico, [])),
        variaciones=variaciones, distribucion=distribucion, mercado=mercado,
        generado_en=ahora.isoformat(), criterio_variacion="compra_comercial", fecha_operaciones="fecha_creacion")


@never_cache
@requiere_rol("ANALISTA_CAMBIARIO")
@require_GET
def dashboard_analista_api(request):
    try:
        filtros = validar_filtros(request.GET, divisas=divisas_dashboard())
        return JsonResponse(consultar_dashboard_analista(filtros))
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    except DatabaseError:
        logging.getLogger(__name__).error("DASHBOARD_ANALISTA_LECTURA_FALLIDA")
        return JsonResponse({"error": "No se pudieron cargar los datos de mercado. Intentá nuevamente."}, status=503)
