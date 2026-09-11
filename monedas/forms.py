from django import forms

from .models import Moneda


class MonedaForm(forms.ModelForm):
    """
    Valida y normaliza los datos de una moneda antes de persistirlos.
    """

    class Meta:
        model = Moneda
        fields = [
            "codigo",
            "nombre",
            "simbolo",
            "estado",
        ]

    def clean_codigo(self):
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
        nombre = self.cleaned_data["nombre"].strip()

        if not nombre:
            raise forms.ValidationError(
                "El nombre de la moneda es obligatorio."
            )

        return nombre

    def clean_simbolo(self):
        simbolo = self.cleaned_data["simbolo"].strip()

        if not simbolo:
            raise forms.ValidationError(
                "El símbolo de la moneda es obligatorio."
            )

        return simbolo