from django import forms

from monedas.models import Moneda

from .models import Caja, MovimientoCaja


class CajaForm(forms.ModelForm):
    """Valida datos configurables; la identidad procede de la sesión."""

    class Meta:
        model = Caja
        fields = ["codigo", "nombre", "estado"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "ge-input"}),
            "nombre": forms.TextInput(attrs={"class": "ge-input"}),
            "estado": forms.Select(attrs={"class": "ge-input"}),
        }

    def clean_codigo(self):
        """Normaliza el identificador y rechaza duplicados antes de guardar."""
        codigo = self.cleaned_data["codigo"].strip().upper()
        if Caja.objects.filter(codigo__iexact=codigo).exists():
            raise forms.ValidationError("Ya existe una caja con ese código.", code="duplicate")
        return codigo


class EstadoCajaForm(forms.Form):
    """Acepta exclusivamente los estados de habilitación del catálogo."""

    estado = forms.ChoiceField(choices=Caja.ESTADOS)


class AperturaCajaForm(forms.Form):
    """Captura un importe por par firmado, sin completar campos ausentes.

    La confirmación reutiliza los mismos campos; el servicio vuelve a validar
    el catálogo y cada importe dentro de la transacción.
    """

    catalogo = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, pares, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pares = pares
        for moneda_id, codigo in pares:
            self.fields[f"monto_{moneda_id}"] = forms.CharField(
                label=f"Saldo inicial {codigo}",
                widget=forms.TextInput(attrs={"class": "ge-input", "inputmode": "decimal", "autocomplete": "off"}),
            )

    def clean(self):
        """Valida decimales exactos y rechaza monedas adicionales o campos repetidos."""
        from .services import validar_importe_inicial

        datos = super().clean()
        permitidos = {f"monto_{par[0]}" for par in self.pares}
        for clave in self.data:
            if clave.startswith("monto_") and clave not in permitidos:
                raise forms.ValidationError("Se incluyó una moneda que no pertenece al catálogo mostrado.")
        for campo in permitidos:
            if hasattr(self.data, "getlist") and len(self.data.getlist(campo)) > 1:
                self.add_error(campo, "No se permite repetir monedas.")
            elif campo in datos:
                try:
                    datos[campo] = validar_importe_inicial(datos[campo])
                except forms.ValidationError as error:
                    self.add_error(campo, error)
        return datos

    def saldos(self):
        """Devuelve los importes validados como lista explícita para el servicio."""
        return [{"moneda_id": moneda_id, "monto": self.cleaned_data[f"monto_{moneda_id}"]} for moneda_id, _ in self.pares]


class MovimientoCajaForm(forms.Form):
    """Captura un movimiento manual limitado a las monedas de la apertura."""

    tipo = forms.ChoiceField(choices=MovimientoCaja.TIPOS, widget=forms.Select(attrs={"class": "ge-input"}))
    moneda = forms.ModelChoiceField(queryset=Moneda.objects.none(), widget=forms.Select(attrs={"class": "ge-input"}))
    monto = forms.CharField(widget=forms.TextInput(attrs={"class": "ge-input", "inputmode": "decimal", "autocomplete": "off"}))
    motivo = forms.CharField(max_length=255, widget=forms.Textarea(attrs={"class": "ge-input", "rows": 3}))

    def __init__(self, periodo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        moneda_ids = periodo.saldos_iniciales.values_list("moneda_id", flat=True)
        self.fields["moneda"].queryset = Moneda.objects.filter(id__in=moneda_ids).order_by("codigo")

    def clean_monto(self):
        """Valida el monto con la misma regla exacta utilizada por el servicio."""
        from .services import validar_monto_movimiento

        return validar_monto_movimiento(self.cleaned_data["monto"])

    def clean_motivo(self):
        """Exige un motivo explícito para preservar la trazabilidad manual."""
        motivo = self.cleaned_data["motivo"].strip()
        if not motivo:
            raise forms.ValidationError("El motivo es obligatorio.")
        return motivo
class ArqueoCajaForm(forms.Form):
    """Captura el saldo físico de cada moneda para realizar el arqueo."""

    observacion = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "ge-input",
                "rows": 3,
                "placeholder": "Observación si existe una diferencia",
            }
        ),
    )

    def __init__(self, saldos, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saldos = list(saldos)

        for saldo in self.saldos:
            self.fields[f"monto_{saldo.moneda.id}"] = forms.CharField(
                label=f"Saldo físico {saldo.moneda.codigo}",
                widget=forms.TextInput(
                    attrs={
                        "class": "ge-input",
                        "inputmode": "decimal",
                        "autocomplete": "off",
                    }
                ),
            )

    def clean(self):
        """Valida que todos los saldos físicos sean números no negativos."""
        from .services import validar_importe_inicial

        datos = super().clean()

        for saldo in self.saldos:
            campo = f"monto_{saldo.moneda.id}"

            if campo in datos:
                try:
                    datos[campo] = validar_importe_inicial(datos[campo])
                except forms.ValidationError as error:
                    self.add_error(campo, error)

        return datos

    def saldos_fisicos(self):
        """Devuelve los saldos físicos validados para el servicio de arqueo."""
        return [
            {
                "moneda_id": saldo.moneda.id,
                "monto": self.cleaned_data[f"monto_{saldo.moneda.id}"],
            }
            for saldo in self.saldos
        ]
