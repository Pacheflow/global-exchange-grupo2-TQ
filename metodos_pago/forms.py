from django import forms

from .models import MetodoPago


class MetodoPagoForm(forms.ModelForm):
    """
    Valida los datos utilizados para registrar o editar un método de pago.

    Las validaciones se ejecutan en Backend antes de persistir los datos,
    garantizando que el nombre sea válido y único dentro del catálogo global.
    """

    naturaleza = forms.ChoiceField(
        label="Tipo",
        choices=[
            ("", "Seleccioná un tipo"),
            (MetodoPago.Naturaleza.ELECTRONICO, "Electrónico"),
            (MetodoPago.Naturaleza.EFECTIVO, "Efectivo"),
        ],
        error_messages={"required": "Seleccioná el tipo del método de pago."},
    )

    class Meta:
        model = MetodoPago
        fields = [
            "nombre",
            "naturaleza",
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

    def clean_naturaleza(self):
        """Una clasificación con referencias históricas no puede redefinirse."""
        naturaleza = self.cleaned_data["naturaleza"]
        if (self.instance.pk
            and self.instance.naturaleza not in {MetodoPago.Naturaleza.SIN_CLASIFICAR, naturaleza}
            and self.instance.tiene_referencias()):
            raise forms.ValidationError("No se puede cambiar el tipo de un método con operaciones o pagos.")
        return naturaleza

    def clean_descripcion(self):
        """Normaliza la descripción opcional antes de persistirla."""
        return self.cleaned_data.get("descripcion", "").strip()
