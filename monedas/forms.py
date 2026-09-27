from django import forms

from .models import Moneda


class MonedaForm(forms.ModelForm):
    """Valida y normaliza los datos de una moneda antes de persistirlos."""

    class Meta:
        model = Moneda
        fields = [
            "codigo",
            "nombre",
            "simbolo",
            "estado",
        ]

    def clean_codigo(self):
        """Normaliza y valida el código.

        Convierte el código a mayúsculas y elimina espacios externos, y
        verifica que no exista otra moneda con el mismo código.
        """
        codigo = self.cleaned_data["codigo"].strip().upper()

        if not codigo:
            raise forms.ValidationError(
                "El código de la moneda es obligatorio."
            )

        queryset = Moneda.objects.filter(codigo=codigo)

        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError(
                "Ya existe una moneda con ese código.",
                code="duplicate",
            )

        return codigo

    def clean_nombre(self):
        """Elimina los espacios externos del nombre y exige que no quede vacío."""
        nombre = self.cleaned_data["nombre"].strip()

        if not nombre:
            raise forms.ValidationError(
                "El nombre de la moneda es obligatorio."
            )

        return nombre

    def clean_simbolo(self):
        """Elimina los espacios externos del símbolo y exige que no quede vacío."""
        simbolo = self.cleaned_data["simbolo"].strip()

        if not simbolo:
            raise forms.ValidationError(
                "El símbolo de la moneda es obligatorio."
            )

        return simbolo