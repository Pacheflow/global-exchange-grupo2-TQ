import importlib
import json
from types import SimpleNamespace

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from .forms import ClienteForm
from .models import Cliente, UsuarioCliente
from .tests import autenticar_admin, autenticar_con_roles


class DatosFiscalesClienteTests(TestCase):
    def setUp(self):
        autenticar_admin(self)
        self.payload = {
            "nombre_razon_social": "Empresa de prueba",
            "tipo_persona": "JURIDICA", "documento": "80012345", "dv": "0",
            "correo_facturacion": "contacto@example.com",
        }

    def post_api(self, payload, cliente=None):
        url = reverse("clientes_api:editar_cliente", args=[cliente.pk]) if cliente else reverse("clientes_api:crear_cliente")
        return self.client.post(url, json.dumps(payload), content_type="application/json")

    def crear(self, **overrides):
        return Cliente.objects.create(**(self.payload | overrides))

    def test_api_alta_separa_ruc_dv_cero_y_devuelve_correo(self):
        response = self.post_api(self.payload)
        self.assertEqual(response.status_code, 201)
        cliente = Cliente.objects.get()
        self.assertEqual((cliente.documento, cliente.ruc, cliente.dv), ("80012345", "80012345", "0"))
        self.assertEqual(response.json()["cliente"]["correo_facturacion"], "contacto@example.com")
        self.assertEqual(response.json()["cliente"]["dv"], "0")
        self.assertEqual(response.json()["cliente"]["ruc"], "80012345")

    def test_alta_juridica_rechaza_ruc_no_ascii_concatenado_y_largo(self):
        for documento in ("ABC-1", "80012345-0", "１２３", "1" * 31):
            with self.subTest(documento=documento):
                response = self.post_api(self.payload | {"documento": documento})
                self.assertEqual(response.status_code, 400)
                self.assertIn("documento", response.json()["detalles"])
        self.assertFalse(Cliente.objects.exists())

    def test_alta_juridica_exige_dv_un_digito_ascii(self):
        for dv in ("", "12", "x", "０", "1-", "1\n2"):
            with self.subTest(dv=dv):
                response = self.post_api(self.payload | {"dv": dv})
                self.assertEqual(response.status_code, 400)
                self.assertIn("dv", response.json()["detalles"])
        payload = self.payload.copy()
        payload.pop("dv")
        self.assertEqual(self.post_api(payload).status_code, 400)

    def test_modelo_dv_rechaza_no_ascii(self):
        field = Cliente._meta.get_field("dv")
        self.assertEqual(field.clean("0", None), "0")
        for dv in ("x", "９", "12"):
            with self.subTest(dv=dv), self.assertRaises(ValidationError):
                field.clean(dv, None)

    def test_fisica_acepta_pasaporte_sin_ruc_dv_ni_correo(self):
        response = self.post_api({"nombre_razon_social": "Persona", "tipo_persona": "FISICA", "documento": "PA-123"})
        self.assertEqual(response.status_code, 201)
        cliente = Cliente.objects.get()
        self.assertEqual((cliente.ruc, cliente.dv, cliente.correo_facturacion), ("", "", ""))

    def test_correo_invalido_es_error_inline_y_no_persiste(self):
        for correo in ("texto", "nombre@", "@example.com"):
            with self.subTest(correo=correo):
                response = self.post_api(self.payload | {"correo_facturacion": correo})
                self.assertEqual(response.status_code, 400)
                self.assertIn("correo_facturacion", response.json()["detalles"])
        self.assertFalse(Cliente.objects.exists())

    def test_edicion_persiste_email_y_datos_fiscales_separados(self):
        cliente = self.crear()
        response = self.post_api(self.payload | {"documento": "80012346", "dv": "5", "correo_facturacion": "nuevo@example.org"}, cliente)
        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual((cliente.documento, cliente.dv, cliente.correo_facturacion), ("80012346", "5", "nuevo@example.org"))

    def test_edicion_omite_claves_nuevas_preserva_dv_y_correo(self):
        cliente = self.crear()
        payload = {"nombre_razon_social": "Nombre nuevo", "tipo_persona": "JURIDICA", "documento": cliente.documento}
        self.assertEqual(self.post_api(payload, cliente).status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual((cliente.dv, cliente.correo_facturacion), ("0", "contacto@example.com"))
        form = ClienteForm(payload, instance=cliente)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["correo_facturacion"], "contacto@example.com")

    def test_vacio_explicito_limpia_correo_pero_dv_completo_no_puede_borrarse(self):
        cliente = self.crear()
        self.assertEqual(self.post_api(self.payload | {"correo_facturacion": ""}, cliente).status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual(cliente.correo_facturacion, "")
        response = self.post_api(self.payload | {"dv": ""}, cliente)
        self.assertEqual(response.status_code, 400)
        cliente.refresh_from_db()
        self.assertEqual(cliente.dv, "0")

    def test_legacy_alfanumerico_y_dv_ausente_permiten_editar_nombre(self):
        for documento in ("CLI-ANTIGUO", "80098765"):
            with self.subTest(documento=documento):
                cliente = self.crear(documento=documento, dv="")
                response = self.post_api(self.payload | {"nombre_razon_social": "Nombre actualizado", "documento": documento, "dv": ""}, cliente)
                self.assertEqual(response.status_code, 200)
                cliente.refresh_from_db()
                self.assertEqual((cliente.documento, cliente.dv), (documento, ""))

    def test_legacy_no_relaja_cambios_fiscales_ni_altas(self):
        cliente = self.crear(documento="HISTORICO", dv="")
        for cambios in ({"documento": "OTRO"}, {"dv": "3"}, {"documento": "80054321"}):
            payload = self.payload | {"documento": "HISTORICO", "dv": ""} | cambios
            with self.subTest(cambios=cambios):
                self.assertEqual(self.post_api(payload, cliente).status_code, 400)
        self.assertEqual(self.post_api(self.payload | {"documento": "HISTORICO2", "dv": ""}).status_code, 400)
        self.assertEqual(self.post_api(self.payload | {"documento": "80054321", "dv": "0"}, cliente).status_code, 200)

    def test_cambio_a_fisica_descarta_dv_anterior(self):
        cliente = self.crear()
        response = self.post_api(self.payload | {"tipo_persona": "FISICA", "documento": "PAS-10"}, cliente)
        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual((cliente.dv, cliente.ruc), ("", ""))

    def test_duplicado_no_escribe_y_expone_error_de_campo(self):
        self.crear()
        response = self.post_api(self.payload | {"dv": "2"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("documento", response.json()["detalles"])
        self.assertEqual(Cliente.objects.count(), 1)

    def test_formulario_clasico_alta_edicion_y_errores_de_correo(self):
        response = self.client.get(reverse("registrar_cliente"))
        self.assertContains(response, 'type="email"')
        self.assertContains(response, 'name="dv"')
        self.assertContains(response, "Correo electrónico")
        response = self.client.post(reverse("registrar_cliente"), self.payload)
        self.assertEqual(response.status_code, 302)
        cliente = Cliente.objects.get()
        response = self.client.get(reverse("editar_cliente", args=[cliente.pk]))
        self.assertContains(response, 'value="contacto@example.com"')
        self.assertContains(response, '>RUC</label>')
        response = self.client.post(reverse("editar_cliente", args=[cliente.pk]), self.payload | {"correo_facturacion": "incorrecto"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("correo_facturacion", response.context["form"].errors)
        cliente.refresh_from_db()
        self.assertEqual(cliente.correo_facturacion, "contacto@example.com")

    def test_listado_muestra_correo_y_edicion_precargada_escapada(self):
        cliente = self.crear(nombre_razon_social='Empresa "A"')
        response = self.client.get(reverse("consultar_clientes"))
        self.assertContains(response, "contacto@example.com")
        self.assertContains(response, 'data-dv="0"')
        self.assertContains(response, 'data-correo="contacto@example.com"')
        self.assertContains(response, 'data-nombre="Empresa &quot;A&quot;"')
        self.assertContains(response, '80012345-0')
        self.assertEqual(cliente.documento, "80012345")

    def test_no_admin_no_modifica_fiscal_y_no_ve_correo_ajeno(self):
        cliente = self.crear()
        propio = self.crear(documento="80055555", correo_facturacion="propio@example.org")
        UsuarioCliente.objects.create(cliente=propio, keycloak_user_id="usuario", username="usuario")
        autenticar_con_roles(self, ["USUARIO"], sub="usuario")
        self.assertEqual(self.post_api(self.payload).status_code, 403)
        self.assertEqual(self.post_api(self.payload, cliente).status_code, 403)
        response = self.client.get(reverse("consultar_clientes"))
        self.assertContains(response, "propio@example.org")
        self.assertNotContains(response, "contacto@example.com")
        cliente.refresh_from_db()
        self.assertEqual(cliente.correo_facturacion, "contacto@example.com")

    def test_api_rechaza_json_no_objeto(self):
        for payload in ([], "texto", 1, None):
            with self.subTest(payload=payload):
                self.assertEqual(self.post_api(payload).status_code, 400)


class MigracionSepararRucDvTests(TestCase):
    """Ejecuta la conversión real sobre datos, sin alterar el esquema de otras suites."""

    def migrar(self):
        migration = importlib.import_module("clientes.migrations.0007_cliente_dv")
        migration.separar_ruc_dv(apps, SimpleNamespace(connection=connection))

    def crear(self, documento, tipo="JURIDICA"):
        return Cliente.objects.create(nombre_razon_social="Histórico", tipo_persona=tipo, documento=documento)

    def test_separa_solo_juridicas_numericas_y_es_idempotente(self):
        juridica = self.crear("80001000-0")
        fisica = self.crear("12345-6", "FISICA")
        alpha = self.crear("EMP-1")
        self.migrar()
        self.migrar()
        juridica.refresh_from_db()
        fisica.refresh_from_db()
        alpha.refresh_from_db()
        self.assertEqual((juridica.documento, juridica.dv), ("80001000", "0"))
        self.assertEqual((fisica.documento, fisica.dv), ("12345-6", ""))
        self.assertEqual((alpha.documento, alpha.dv), ("EMP-1", ""))

    def test_preserva_colision_con_documento_principal(self):
        base = self.crear("80002000", "FISICA")
        concatenado = self.crear("80002000-3")
        self.migrar()
        concatenado.refresh_from_db()
        base.refresh_from_db()
        self.assertEqual((concatenado.documento, concatenado.dv), ("80002000-3", ""))
        self.assertEqual(base.documento, "80002000")

    def test_preserva_todos_los_legacy_que_comparten_base(self):
        primero = self.crear("80003000-1")
        segundo = self.crear("80003000-2")
        self.migrar()
        primero.refresh_from_db()
        segundo.refresh_from_db()
        self.assertEqual((primero.documento, primero.dv), ("80003000-1", ""))
        self.assertEqual((segundo.documento, segundo.dv), ("80003000-2", ""))
        form = ClienteForm({"nombre_razon_social": "Nombre nuevo", "tipo_persona": "JURIDICA", "documento": primero.documento}, instance=primero)
        self.assertTrue(form.is_valid(), form.errors)
