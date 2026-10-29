from django import forms
from clientes.models import Cliente


class CorreoFacturacionForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["correo_facturacion"]
        labels = {"correo_facturacion": "Correo para recibir las facturas"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["correo_facturacion"].required = True
