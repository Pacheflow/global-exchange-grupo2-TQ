from django import forms

from .models import Caja


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
