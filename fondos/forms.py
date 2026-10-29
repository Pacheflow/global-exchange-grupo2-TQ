from uuid import uuid4
from django import forms
from monedas.models import Moneda
from .services import importe_positivo


class CargaForm(forms.Form):
    moneda = forms.ModelChoiceField(queryset=Moneda.objects.none())
    importe = forms.CharField(max_length=40)
    motivo = forms.CharField(max_length=255)
    clave = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    def __init__(self, *args, **kwargs):
        """Muestra únicamente monedas activas sin cambiar el catálogo."""
        super().__init__(*args, **kwargs)
        self.fields["moneda"].queryset = Moneda.objects.filter(estado="ACTIVA").order_by("codigo")

    def clean_importe(self):
        """Valida precisión antes de cualquier escritura, sin redondeo implícito."""
        return importe_positivo(self.cleaned_data["importe"])
