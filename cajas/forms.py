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
