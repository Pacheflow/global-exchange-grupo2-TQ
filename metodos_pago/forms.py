from django import forms

from .models import MetodoPago


class MetodoPagoForm(forms.ModelForm):
    """
    Valida los datos utilizados para registrar o editar un método de pago.

    Las validaciones se ejecutan en Backend antes de persistir los datos,
    garantizando que el nombre sea válido y único dentro del catálogo global.
    """

    class Meta:
        model = MetodoPago
        fields = [
            "nombre",
            "descripcion",
            "activo",
        ]

    def clean_nombre(self):
        """
        Normaliza el nombre y evita duplicados globales sin distinguir mayúsculas.

        Durante una edición se excluye la instancia actual para permitir
        guardar el método sin considerarlo un duplicado de sí mismo.
        """
        nombre = self.cleaned_data.get("nombre", "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre del método de pago es obligatorio.")

        duplicado = MetodoPago.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise forms.ValidationError(
                "Ya existe un método de pago con ese nombre.",
                code="duplicate",
            )
        return nombre

    def clean_descripcion(self):
        """Normaliza la descripción opcional antes de persistirla."""
        return self.cleaned_data.get("descripcion", "").strip()
