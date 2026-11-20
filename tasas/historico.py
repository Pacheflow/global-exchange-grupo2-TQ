"""Consulta pública del histórico comercial, sin datos de auditoría."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django import forms
from django.core.paginator import Paginator
from django.http import JsonResponse, QueryDict
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from monedas.models import Moneda
from .models import TasaComercial


class FiltroHistoricoForm(forms.Form):
    moneda_origen_id = forms.ModelChoiceField(queryset=Moneda.objects.none(), label="Moneda de origen")
    moneda_destino_id = forms.ModelChoiceField(queryset=Moneda.objects.none(), label="Moneda de destino")
    desde = forms.DateField(required=False, label="Desde", input_formats=["%Y-%m-%d"],
                            widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    hasta = forms.DateField(required=False, label="Hasta", input_formats=["%Y-%m-%d"],
                            widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Una moneda desactivada conserva su historia y puede seguir consultándose.
        for name in ("moneda_origen_id", "moneda_destino_id"):
            self.fields[name].queryset = Moneda.objects.order_by("codigo")
        for field in self.fields.values():
            field.widget.attrs["class"] = "ge-input"

    def clean(self):
        data = super().clean()
        if data.get("moneda_origen_id") and data.get("moneda_origen_id") == data.get("moneda_destino_id"):
            self.add_error("moneda_destino_id", "Seleccioná dos monedas distintas.")
        desde, hasta = data.get("desde"), data.get("hasta")
        if desde and hasta and desde > hasta:
            self.add_error("hasta", "La fecha final debe ser igual o posterior a la inicial.")
        if hasta and hasta.year == 9999:
            self.add_error("hasta", "La fecha final está fuera del rango admitido.")
        return data


def consultar_registros(data):
    """Incluye todas las versiones del par; fechas inclusivas en la zona del proyecto."""
    tasas = TasaComercial.objects.filter(
        moneda_origen=data["moneda_origen_id"], moneda_destino=data["moneda_destino_id"],
    ).order_by("fecha_registro", "pk")
    if data.get("desde"):
        inicio = timezone.make_aware(datetime.combine(data["desde"], time.min))
        tasas = tasas.filter(fecha_registro__gte=inicio)
    if data.get("hasta"):
        fin = timezone.make_aware(datetime.combine(data["hasta"] + timedelta(days=1), time.min))
        tasas = tasas.filter(fecha_registro__lt=fin)
    return tasas


def _numero(value):
    texto = format(value, "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def construir_grafico(registros):
    """Proyecta registros reales en un SVG temporal; no interpola registros ni rellena huecos."""
    if not registros:
        return None
    valores = [getattr(row, key) for row in registros for key in ("compra", "venta")]
    minimo, maximo = min(valores), max(valores)
    margen = (maximo - minimo) / 10 or abs(maximo) / 10 or Decimal("1")
    inferior, superior = minimo - margen, maximo + margen
    inicio, fin = registros[0].fecha_registro, registros[-1].fecha_registro
    duracion = (fin - inicio).total_seconds()
    puntos = []
    for row in registros:
        x = 540 if not duracion else 100 + 880 * (row.fecha_registro - inicio).total_seconds() / duracion
        punto = {"x": f"{x:.2f}", "fecha": timezone.localtime(row.fecha_registro).strftime("%d/%m/%Y %H:%M:%S"),
                 "compra": _numero(row.compra), "venta": _numero(row.venta)}
        for key in ("compra", "venta"):
            punto["y_" + key] = f"{260 - float((getattr(row, key) - inferior) / (superior - inferior)) * 230:.2f}"
        puntos.append(punto)
    ejes = []
    for i in range(5):
        valor = inferior + (superior - inferior) * Decimal(i) / 4
        exacto = _numero(valor)
        ejes.append({"y": f"{260 - i * 57.5:.2f}", "valor": exacto if len(exacto) <= 12 else f"{valor:.6g}"})
    fechas = [{"x": "540", "valor": timezone.localtime(inicio).strftime("%d/%m/%Y %H:%M")}]
    if duracion:
        fechas = [{"x": "100", "valor": timezone.localtime(inicio).strftime("%d/%m/%Y %H:%M")},
                  {"x": "980", "valor": timezone.localtime(fin).strftime("%d/%m/%Y %H:%M")}]
    return {"puntos": puntos, "ejes": ejes, "fechas": fechas,
            "compra": " ".join(p["x"] + "," + p["y_compra"] for p in puntos),
            "venta": " ".join(p["x"] + "," + p["y_venta"] for p in puntos)}


@require_GET
def historico_api(request):
    """API pública de solo lectura: nunca incluye usuarios ni metadatos internos."""
    form = FiltroHistoricoForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errores": form.errors.get_json_data()}, status=400)
    data = form.cleaned_data
    registros = consultar_registros(data)
    return JsonResponse({
        "par": f'{data["moneda_origen_id"].codigo}/{data["moneda_destino_id"].codigo}',
        "zona_horaria": timezone.get_current_timezone_name(),
        "registros": [{"fecha": row.fecha_registro.isoformat(),
                       "compra": str(row.compra), "venta": str(row.venta)} for row in registros],
    })


@require_GET
def historico_web(request):
    """Filtros, gráfico y tabla accesibles también sin iniciar sesión."""
    datos = request.GET
    if not any(key in datos for key in ("moneda_origen_id", "moneda_destino_id", "desde", "hasta")):
        par = TasaComercial.objects.order_by("moneda_origen__codigo", "moneda_destino__codigo").values(
            "moneda_origen_id", "moneda_destino_id").first()
        if not par:
            monedas = list(Moneda.objects.order_by("codigo").values_list("pk", flat=True)[:2])
            par = dict(zip(("moneda_origen_id", "moneda_destino_id"), monedas))
        datos = {**par, "desde": timezone.localdate() - timedelta(days=30), "hasta": timezone.localdate()}
    form = FiltroHistoricoForm(datos)
    registros = []
    par = ""
    valido = form.is_valid()
    if valido:
        registros = list(consultar_registros(form.cleaned_data))
        par = f'{form.cleaned_data["moneda_origen_id"].codigo}/{form.cleaned_data["moneda_destino_id"].codigo}'
    pagina = Paginator(registros, 25).get_page(request.GET.get("page"))
    parametros = QueryDict(mutable=True)
    parametros.update(datos)
    parametros.pop("page", None)
    return render(request, "frontend/tasas_historico.html", {
        "form": form, "par": par, "grafico": construir_grafico(registros), "pagina": pagina,
        "parametros": parametros.urlencode(), "total": len(registros),
        "zona_horaria": timezone.get_current_timezone_name(),
        "hay_monedas": Moneda.objects.count() >= 2,
    }, status=400 if request.GET and not valido else 200)
