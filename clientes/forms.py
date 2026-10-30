import re

from django import forms
from .models import Cliente, UsuarioCliente


class ClienteForm(forms.ModelForm):
    """Formulario utilizado para registrar clientes en Global Exchange."""

    class Meta:
        model = Cliente

        fields = [
            "nombre_razon_social",
            "tipo_persona",
            "documento",
            "dv",
            "correo_facturacion",
        ]

        labels = {
            "nombre_razon_social": "Nombre o razón social",
            "tipo_persona": "Tipo de persona",
            "documento": "Cédula o pasaporte",
            "dv": "DV",
            "correo_facturacion": "Correo electrónico",
        }

        widgets = {
            "dv": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": "1", "pattern": "[0-9]"}),
            "correo_facturacion": forms.EmailInput(attrs={"autocomplete": "email"}),
        }
        help_texts = {
            "dv": "Dígito verificador del RUC, separado del número principal.",
            "correo_facturacion": "Opcional. Las facturas se consultan en la web.",
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        incoming = args[0] if args else kwargs.get("data")
        if instance is not None and instance.pk and incoming is not None:
            # Clientes API antiguos no enviaban estos campos; omitir no es borrar.
            incoming = incoming.copy()
            for field in ("dv", "correo_facturacion"):
                if field not in incoming:
                    incoming[field] = getattr(instance, field)
            if args:
                args = (incoming,) + args[1:]
            else:
                kwargs["data"] = incoming
        super().__init__(*args, **kwargs)
        # Guardar antes de que ModelForm actualice la instancia durante la validación.
        self._fiscal_original = (
            self.instance.tipo_persona, self.instance.documento, self.instance.dv
        ) if self.instance.pk else None
        tipo = self.data.get("tipo_persona") if self.is_bound else self.instance.tipo_persona
        if tipo == "JURIDICA":
            self.fields["documento"].label = "RUC"

    def clean(self):
        data = super().clean()
        tipo = data.get("tipo_persona")
        documento = data.get("documento", "")
        dv = data.get("dv", "")
        if tipo == "FISICA":
            # Un cambio de tipo no debe arrastrar el DV jurídico anterior.
            data["dv"] = ""
            return data
        if tipo != "JURIDICA":
            return data
        original = self._fiscal_original
        legacy_unchanged = (
            original is not None
            and original[0] == "JURIDICA"
            and (not re.fullmatch(r"[0-9]+", original[1]) or not original[2])
            and (tipo, documento, dv) == original
        )
        if not legacy_unchanged:
            if documento and not re.fullmatch(r"[0-9]+", documento):
                self.add_error("documento", "El RUC debe contener solo números, sin guion ni DV.")
            if not dv:
                self.add_error("dv", "Ingresá el dígito verificador del RUC.")
        return data


class SegmentacionClienteForm(forms.ModelForm):
    """Formulario utilizado para asignar una categoría a un cliente."""

    class Meta:
        model = Cliente

        fields = [
            "categoria",
        ]

        labels = {
            "categoria": "Categoría del cliente",
        }


class AsignacionUsuarioClienteForm(forms.Form):
    """Formulario para asignar un usuario de Keycloak con su permiso a un cliente.

    Recibe como parámetro ``usuarios``, la lista de usuarios de Keycloak
    disponibles para poblar el selector.
    """

    usuario = forms.ChoiceField(label="Usuario de Keycloak")
    rol_en_cliente = forms.ChoiceField(
        label="Permiso dentro del cliente",
        choices=UsuarioCliente.ROLES,
    )

    def __init__(self, *args, usuarios=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["usuario"].choices = [
            (user["id"], user["label"]) for user in usuarios
        ]
