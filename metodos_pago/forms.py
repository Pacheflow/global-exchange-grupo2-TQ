from django import forms

from .models import MetodoPago


class MetodoPagoForm(forms.ModelForm):
    """
    Valida los datos utilizados para registrar o editar un método de pago.

    Las validaciones se ejecutan en Backend antes de persistir los datos,
    garantizando que el nombre sea válido y que no existan métodos de pago
    duplicados para un mismo cliente.
    """

    class Meta:
        model = MetodoPago
        fields = [
            "cliente",
            "nombre",
            "tipo",
            "estado",
        ]

    def clean_nombre(self):
        """
        Normaliza el nombre y valida que no esté vacío.

        Los espacios al inicio y al final se eliminan para evitar que dos
        métodos aparentemente iguales sean tratados como diferentes.
        """
        nombre = self.cleaned_data.get("nombre", "").strip()

        if not nombre:
            raise forms.ValidationError("El nombre del método de pago es obligatorio.")

        return nombre

    def clean(self):
        """
        Valida que no exista otro método con el mismo nombre para el cliente.

        Durante una edición se excluye la instancia actual para permitir
        guardar el método sin considerarlo un duplicado de sí mismo.
        """
        cleaned_data = super().clean()

        cliente = cleaned_data.get("cliente")
        nombre = cleaned_data.get("nombre")

        if cliente and nombre:
            duplicado = MetodoPago.objects.filter(
                cliente=cliente,
                nombre__iexact=nombre,
            )

            if self.instance.pk:
                duplicado = duplicado.exclude(pk=self.instance.pk)

            if duplicado.exists():
                raise forms.ValidationError(
                    "El cliente ya tiene un método de pago con ese nombre."
                )

        return cleaned_data
