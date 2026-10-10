from django import forms


class UmbralNotificacionForm(forms.Form):
    """Captura el porcentaje explícito; el servicio valida finitud, positividad y capacidad."""

    umbral_porcentaje = forms.CharField(label="Variación mínima (%)", max_length=100)
