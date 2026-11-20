"""Etiquetas y distribución para Chart.js; importes exactos como strings."""
from decimal import Decimal, ROUND_HALF_UP, localcontext

MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")


def presentar_graficos(reporte, *, divisa):
    """Reutiliza agregaciones financieras sin recalcular comisiones/conversiones."""
    evolucion = []
    for p in reporte["periodos"]:
        anio, mes, dia = map(int, p["inicio"].split("-"))
        etiqueta = f"{MESES[mes - 1]} {anio}" if reporte["agrupacion"] == "mes" else f"{dia:02d}/{mes:02d}/{anio}"
        evolucion.append(dict(periodo=p["inicio"], etiqueta=etiqueta, desde=p["desde"], hasta=p["hasta"],
                               ganancia_pyg=p["ganancia"], excluidas=p["operaciones_sin_conversion"]))
    if divisa:
        total = reporte["totales"]
        categorias = [dict(categoria="Compra", cantidad=total["compras"]),
                      dict(categoria="Venta", cantidad=total["ventas"])]
        denominador = Decimal(total["operaciones"])
        modo = "tipo"
    else:
        categorias = [dict(categoria=d["divisa"], ganancia_pyg=d["ganancia"])
                      for d in reporte["distribucion"] if Decimal(d["ganancia"]) > 0]
        denominador = sum((Decimal(d["ganancia_pyg"]) for d in categorias), Decimal(0))
        modo = "divisa"
    with localcontext() as ctx:
        ctx.prec = 64
        for categoria in categorias:
            valor = Decimal(categoria.get("ganancia_pyg", categoria.get("cantidad", 0)))
            categoria["porcentaje"] = format((valor / denominador * 100 if denominador else Decimal(0))
                                            .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    return evolucion, dict(modo=modo, titulo="Compras vs Ventas" if divisa else "Ganancia por divisa (%)",
                            categorias=categorias)
