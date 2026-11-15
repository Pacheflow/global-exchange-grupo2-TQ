"""Consulta administrativa de transacciones, sin acciones operativas."""

from datetime import datetime, time, timedelta

from django import forms
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from clientes.models import Cliente
from monedas.models import Moneda
from usuarios.decorators import requiere_roles_web

from .models import LiquidacionEfectivo, Transaccion


class FiltrosReporteTransaccionesForm(forms.Form):
    """Valida los filtros admitidos por el reporte administrativo."""

    fecha_desde = forms.DateField(
        required=False,
        input_formats=("%Y-%m-%d",),
        widget=forms.DateInput(attrs={"type": "date", "class": "ge-report-control"}),
        label="Fecha desde",
    )
    fecha_hasta = forms.DateField(
        required=False,
        input_formats=("%Y-%m-%d",),
        widget=forms.DateInput(attrs={"type": "date", "class": "ge-report-control"}),
        label="Fecha hasta",
    )
    cliente = forms.ModelChoiceField(
        required=False,
        queryset=Cliente.objects.order_by("nombre_razon_social", "pk"),
        empty_label="Todos los clientes",
        widget=forms.Select(attrs={"class": "ge-report-control"}),
        label="Cliente",
    )
    tipo = forms.ChoiceField(
        required=False,
        choices=(("", "Todos los tipos"), *Transaccion.TIPOS_TRANSACCION),
        widget=forms.Select(attrs={"class": "ge-report-control"}),
        label="Tipo de operación",
    )
    estado = forms.ChoiceField(
        required=False,
        choices=(("", "Todos los estados"), *Transaccion.ESTADOS_TRANSACCION),
        widget=forms.Select(attrs={"class": "ge-report-control"}),
        label="Estado",
    )
    naturaleza = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Todas las naturalezas"),
            ("EFECTIVO", "Efectivo"),
            ("ELECTRONICO", "Electrónico"),
            ("SIN_CLASIFICACION", "Sin clasificación histórica"),
        ),
        widget=forms.Select(attrs={"class": "ge-report-control"}),
        label="Naturaleza histórica",
    )
    moneda = forms.ModelChoiceField(
        required=False,
        queryset=Moneda.objects.order_by("codigo", "pk"),
        empty_label="Todas las monedas",
        widget=forms.Select(attrs={"class": "ge-report-control"}),
        label="Moneda",
    )

    def clean(self):
        """Rechaza rangos de fechas invertidos antes de consultar operaciones."""
        cleaned_data = super().clean()
        desde = cleaned_data.get("fecha_desde")
        hasta = cleaned_data.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            self.add_error("fecha_hasta", "La fecha hasta debe ser igual o posterior a fecha desde.")
        return cleaned_data


def _consulta_reporte(filtros):
    """Construye una consulta paginable basada solo en los campos persistidos."""
    transacciones = (
        Transaccion.objects.select_related(
            "cliente",
            "moneda_origen",
            "moneda_destino",
            "liquidacion_efectivo__periodo__caja",
        )
        .order_by("-fecha_creacion", "-pk")
    )

    desde = filtros.get("fecha_desde")
    hasta = filtros.get("fecha_hasta")
    zona = timezone.get_current_timezone()
    if desde:
        limite_desde = timezone.make_aware(datetime.combine(desde, time.min), zona)
        transacciones = transacciones.filter(fecha_creacion__gte=limite_desde)
    if hasta:
        try:
            dia_siguiente = hasta + timedelta(days=1)
        except OverflowError:
            dia_siguiente = None
        if dia_siguiente:
            limite_hasta_exclusivo = timezone.make_aware(
                datetime.combine(dia_siguiente, time.min), zona
            )
            transacciones = transacciones.filter(fecha_creacion__lt=limite_hasta_exclusivo)

    if filtros.get("cliente"):
        transacciones = transacciones.filter(cliente_id=filtros["cliente"].pk)
    if filtros.get("tipo"):
        transacciones = transacciones.filter(tipo=filtros["tipo"])
    if filtros.get("estado"):
        transacciones = transacciones.filter(estado=filtros["estado"])

    naturaleza = filtros.get("naturaleza")
    if naturaleza == "SIN_CLASIFICACION":
        transacciones = transacciones.filter(naturaleza_metodo="")
    elif naturaleza:
        transacciones = transacciones.filter(naturaleza_metodo=naturaleza)

    moneda = filtros.get("moneda")
    if moneda:
        transacciones = transacciones.filter(
            Q(moneda_origen_id=moneda.pk) | Q(moneda_destino_id=moneda.pk)
        ).distinct()
    return transacciones


def _naturaleza_historica(transaccion):
    """Presenta la clasificación guardada sin consultar el catálogo actual."""
    return {
        "EFECTIVO": "Efectivo",
        "ELECTRONICO": "Electrónico",
    }.get(transaccion.naturaleza_metodo, "Sin clasificación histórica")


def _metodo_historico(transaccion):
    """Devuelve el nombre guardado en la operación, sin sustituirlo por el actual."""
    return (
        transaccion.metodo_pago_nombre.strip()
        or "Sin registro histórico"
    )


def _actor_explicito(transaccion):
    """Muestra el actor de la liquidación o creación sin revelar IDs técnicos."""
    try:
        liquidacion = transaccion.liquidacion_efectivo
    except LiquidacionEfectivo.DoesNotExist:
        liquidacion = None
    if liquidacion:
        if liquidacion.confirmado_por_username:
            return f"Cajero: {liquidacion.confirmado_por_username}"
        if liquidacion.confirmado_por_keycloak_id:
            return "Cajero: identidad registrada"
    if transaccion.creado_por_username:
        return transaccion.creado_por_username
    if transaccion.creado_por_keycloak_id:
        return "Identidad registrada"
    return "Sin registro de usuario"


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def reporte_administrativo_transacciones(request):
    """Muestra el reporte global administrativo con filtros GET y paginación."""
    formulario = FiltrosReporteTransaccionesForm(request.GET)
    filtros_validos = formulario.is_valid()
    queryset = (
        _consulta_reporte(formulario.cleaned_data)
        if filtros_validos
        else Transaccion.objects.none()
    )
    paginador = Paginator(queryset, 25)
    pagina = paginador.get_page(request.GET.get("page", 1))
    for transaccion in pagina.object_list:
        transaccion.reporte_naturaleza = _naturaleza_historica(transaccion)
        transaccion.reporte_metodo = _metodo_historico(transaccion)
        transaccion.reporte_actor = _actor_explicito(transaccion)

    parametros = request.GET.copy()
    parametros.pop("page", None)
    querystring = parametros.urlencode()
    return render(
        request,
        "frontend/reporte_transacciones.html",
        {
            "formulario": formulario,
            "filtros_validos": filtros_validos,
            "pagina": pagina,
            "total_resultados": paginador.count,
            "querystring": querystring,
        },
    )


@requiere_roles_web("ADMINISTRADOR")
@require_GET
def detalle_reporte_transaccion(request, transaccion_id):
    """Presenta una transacción para consulta sin acceder a pagos ni mutarla."""
    transaccion = get_object_or_404(
        Transaccion.objects.select_related(
            "cliente",
            "moneda_origen",
            "moneda_destino",
            "liquidacion_efectivo__periodo__caja",
        ),
        pk=transaccion_id,
    )
    try:
        liquidacion = transaccion.liquidacion_efectivo
    except LiquidacionEfectivo.DoesNotExist:
        liquidacion = None
    return render(
        request,
        "frontend/reporte_transaccion_detalle.html",
        {
            "transaccion": transaccion,
            "naturaleza": _naturaleza_historica(transaccion),
            "metodo": _metodo_historico(transaccion),
            "actor": _actor_explicito(transaccion),
            "liquidacion": liquidacion,
        },
    )
