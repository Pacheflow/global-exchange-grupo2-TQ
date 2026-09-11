from django.db import IntegrityError, transaction
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse

from .forms import ClienteForm
from unittest.mock import patch
import json
import time

from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import CategoriaCliente, Cliente, UsuarioCliente


def autenticar_con_roles(
    test_case,
    roles,
    *,
    sub="admin-id",
    incluir_kc_user=True,
):
    session = test_case.client.session
    if incluir_kc_user:
        session["kc_user"] = {"sub": sub, "preferred_username": "usuario"}
    else:
        session.pop("kc_user", None)
    session[SESSION_AUTENTICADO] = True
    session[SESSION_USUARIO] = {"sub": sub, "username": "usuario"}
    session[SESSION_ROLES] = roles
    session[SESSION_EXPIRA_EN] = int(time.time()) + 600
    session.save()


def autenticar_admin(test_case):
    autenticar_con_roles(test_case, ["ADMINISTRADOR"])


class ClienteModelTest(TestCase):

    def test_crear_categoria_cliente(self):
        categoria = CategoriaCliente.objects.create(
            nombre="Categoria Prueba",
            descripcion="Categoría utilizada para pruebas"
        )

        self.assertEqual(
            categoria.nombre,
            "Categoria Prueba"
        )

    def test_crear_cliente(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Prueba",
            tipo_persona="FISICA",
            documento="123456"
        )

        self.assertEqual(
            cliente.nombre_razon_social,
            "Cliente Prueba"
        )

    def test_estado_activo_por_defecto(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Activo",
            tipo_persona="FISICA",
            documento="111111"
        )

        self.assertEqual(
            cliente.estado,
            "ACTIVO"
        )

    def test_dar_de_baja_cliente(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Baja",
            tipo_persona="FISICA",
            documento="222222"
        )

        cliente.dar_de_baja()

        self.assertEqual(
            cliente.estado,
            "INACTIVO"
        )

    def test_documento_no_se_puede_repetir(self):
        Cliente.objects.create(
            nombre_razon_social="Primer Cliente",
            tipo_persona="FISICA",
            documento="333333"
        )

        form = ClienteForm(data={
            "nombre_razon_social": "Segundo Cliente",
            "tipo_persona": "FISICA",
            "documento": "333333"
        })

        self.assertFalse(
            form.is_valid()
        )

    def test_documento_puede_ser_alfanumerico(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Extranjero",
            tipo_persona="FISICA",
            documento="AB123456"
        )

        self.assertEqual(
            cliente.documento,
            "AB123456"
        )

    def test_documento_puede_contener_guion(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Empresa Prueba",
            tipo_persona="JURIDICA",
            documento="80012345-6"
        )

        self.assertEqual(
            cliente.documento,
            "80012345-6"
        )

    def test_nombre_es_obligatorio(self):
        form = ClienteForm(data={
            "nombre_razon_social": "",
            "tipo_persona": "FISICA",
            "documento": "555555"
        })

        self.assertFalse(
            form.is_valid()
        )

    def test_documento_es_obligatorio(self):
        form = ClienteForm(data={
            "nombre_razon_social": "Cliente Sin Documento",
            "tipo_persona": "FISICA",
            "documento": ""
        })

        self.assertFalse(
            form.is_valid()
        )

    def test_tipo_persona_invalido(self):
        form = ClienteForm(data={
            "nombre_razon_social": "Cliente Prueba",
            "tipo_persona": "OTRO",
            "documento": "666666"
        })

        self.assertFalse(
            form.is_valid()
        )


class RegistrarClienteViewTest(TestCase):

    def setUp(self):
        autenticar_admin(self)

    def test_mostrar_formulario_registro(self):
        response = self.client.get(
            reverse("registrar_cliente")
        )

        self.assertEqual(
            response.status_code,
            200
        )

        self.assertTemplateUsed(
            response,
            "clientes/registrar.html"
        )

    def test_registrar_cliente(self):
        response = self.client.post(
            reverse("registrar_cliente"),
            {
                "nombre_razon_social": "Cliente Nuevo",
                "tipo_persona": "FISICA",
                "documento": "444444"
            }
        )

        self.assertEqual(
            response.status_code,
            302
        )

        self.assertTrue(
            Cliente.objects.filter(
                documento="444444"
            ).exists()
        )

    def test_rechaza_usuario_sin_rol_administrador(self):
        autenticar_con_roles(self, ["USUARIO"], sub="usuario-basico")

        response = self.client.get(reverse("registrar_cliente"))

        self.assertEqual(response.status_code, 403)

    def test_no_registra_cliente_con_datos_invalidos(self):
        response = self.client.post(
            reverse("registrar_cliente"),
            {
                "nombre_razon_social": "",
                "tipo_persona": "INVALIDO",
                "documento": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Cliente.objects.exists())


class ConsultarClienteViewTest(TestCase):

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Consulta",
            tipo_persona="FISICA",
            documento="CONSULTA-001"
        )

    def test_consultar_clientes(self):
        response = self.client.get(
            reverse("consultar_clientes")
        )

        self.assertEqual(
            response.status_code,
            200
        )

        self.assertContains(
            response,
            "Cliente Consulta"
        )

    def test_buscar_cliente_por_nombre(self):
        response = self.client.get(
            reverse("consultar_clientes"),
            {
                "buscar": "Consulta"
            }
        )

        self.assertContains(
            response,
            "Cliente Consulta"
        )

    def test_consulta_sin_resultados(self):
        response = self.client.get(
            reverse("consultar_clientes"),
            {
                "buscar": "NoExiste"
            }
        )

        self.assertContains(
            response,
            "No se encontraron clientes."
        )

    def test_no_administrador_solo_ve_clientes_asignados(self):
        otro_cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Ajeno",
            tipo_persona="JURIDICA",
            documento="AJENO-001",
        )
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-cajero-1",
            username="cajero",
        )
        autenticar_con_roles(self, ["CAJERO"], sub="kc-cajero-1")

        response = self.client.get(reverse("consultar_clientes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.cliente.nombre_razon_social)
        self.assertNotContains(response, otro_cliente.nombre_razon_social)

    def test_no_administrador_sin_asignaciones_no_ve_clientes(self):
        autenticar_con_roles(self, ["USUARIO"], sub="kc-sin-asignacion")

        response = self.client.get(reverse("consultar_clientes"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            self.cliente.nombre_razon_social,
            status_code=200,
        )
        self.assertContains(response, "No tenés clientes asociados disponibles.")

    def test_sesion_no_administradora_sin_sub_se_rechaza(self):
        autenticar_con_roles(
            self,
            ["CAJERO"],
            sub="kc-oidc-valido",
            incluir_kc_user=False,
        )

        response = self.client.get(reverse("consultar_clientes"))

        self.assertEqual(response.status_code, 403)
        self.assertNotContains(
            response,
            self.cliente.nombre_razon_social,
            status_code=403,
        )


class EditarClienteViewTest(TestCase):

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Original",
            tipo_persona="FISICA",
            documento="EDITAR-001"
        )

    def test_editar_cliente(self):
        response = self.client.post(
            reverse(
                "editar_cliente",
                args=[self.cliente.id]
            ),
            {
                "nombre_razon_social": "Cliente Editado",
                "tipo_persona": "JURIDICA",
                "documento": "EDITAR-001"
            }
        )

        self.assertEqual(
            response.status_code,
            302
        )

        self.cliente.refresh_from_db()

        self.assertEqual(
            self.cliente.nombre_razon_social,
            "Cliente Editado"
        )

        self.assertEqual(
            self.cliente.tipo_persona,
            "JURIDICA"
        )

    def test_no_permite_documento_duplicado_al_editar(self):
        Cliente.objects.create(
            nombre_razon_social="Otro Cliente",
            tipo_persona="FISICA",
            documento="DOCUMENTO-OTRO"
        )

        response = self.client.post(
            reverse(
                "editar_cliente",
                args=[self.cliente.id]
            ),
            {
                "nombre_razon_social": "Cliente Modificado",
                "tipo_persona": "FISICA",
                "documento": "DOCUMENTO-OTRO"
            }
        )

        self.assertEqual(
            response.status_code,
            200
        )

        self.cliente.refresh_from_db()

        self.assertEqual(
            self.cliente.documento,
            "EDITAR-001"
        )

    def test_cliente_inexistente_devuelve_404(self):
        response = self.client.get(reverse("editar_cliente", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_datos_invalidos_no_modifican_cliente(self):
        response = self.client.post(
            reverse("editar_cliente", args=[self.cliente.id]),
            {
                "nombre_razon_social": "",
                "tipo_persona": "INVALIDO",
                "documento": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre_razon_social, "Cliente Original")
        self.assertEqual(self.cliente.documento, "EDITAR-001")


class DarDeBajaClienteViewTest(TestCase):

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Baja Vista",
            tipo_persona="FISICA",
            documento="BAJA-001"
        )

    def test_dar_de_baja_cliente(self):
        response = self.client.post(
            reverse(
                "dar_de_baja_cliente",
                args=[self.cliente.id]
            )
        )

        self.assertEqual(
            response.status_code,
            302
        )

        self.cliente.refresh_from_db()

        self.assertEqual(
            self.cliente.estado,
            "INACTIVO"
        )

        self.assertTrue(
            Cliente.objects.filter(
                id=self.cliente.id
            ).exists()
        )

    def test_cliente_inexistente_devuelve_404(self):
        response = self.client.post(
            reverse("dar_de_baja_cliente", args=[999999])
        )

        self.assertEqual(response.status_code, 404)

    def test_baja_repetida_es_idempotente(self):
        url = reverse("dar_de_baja_cliente", args=[self.cliente.id])

        primera_respuesta = self.client.post(url)
        segunda_respuesta = self.client.post(url)

        self.assertEqual(primera_respuesta.status_code, 302)
        self.assertEqual(segunda_respuesta.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado, "INACTIVO")
        self.assertTrue(Cliente.objects.filter(id=self.cliente.id).exists())


class SegmentarClienteViewTest(TestCase):

    def setUp(self):
        autenticar_admin(self)
        self.categoria, _ = CategoriaCliente.objects.get_or_create(
            nombre="VIP",
            defaults={
                "descripcion": "Cliente VIP"
            }
        )

        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Segmentado",
            tipo_persona="FISICA",
            documento="SEGMENTAR-001"
        )

    def test_segmentar_cliente(self):
        response = self.client.post(
            reverse(
                "segmentar_cliente",
                args=[self.cliente.id]
            ),
            {
                "categoria": self.categoria.id
            }
        )

        self.assertEqual(
            response.status_code,
            302
        )

        self.cliente.refresh_from_db()

        self.assertEqual(
            self.cliente.categoria,
            self.categoria
        )

    def test_cambiar_categoria_cliente(self):
        otra_categoria = CategoriaCliente.objects.create(
            nombre="Corporativo Prueba"
        )

        self.cliente.categoria = self.categoria
        self.cliente.save()

        self.client.post(
            reverse(
                "segmentar_cliente",
                args=[self.cliente.id]
            ),
            {
                "categoria": otra_categoria.id
            }
        )

        self.cliente.refresh_from_db()

        self.assertEqual(
            self.cliente.categoria,
            otra_categoria
        )

    def test_cliente_inexistente_devuelve_404(self):
        response = self.client.get(reverse("segmentar_cliente", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_categoria_inexistente_no_modifica_cliente(self):
        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": 999999},
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.categoria)

    def test_analista_asociado_no_puede_segmentar_cliente(self):
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-analista-1",
            username="analista",
        )
        autenticar_con_roles(
            self,
            ["ANALISTA_CAMBIARIO"],
            sub="kc-analista-1",
        )

        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": self.categoria.id},
        )

        self.assertEqual(response.status_code, 403)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.categoria)

    def test_analista_no_asociado_no_puede_segmentar_cliente_ajeno(self):
        cliente_permitido = Cliente.objects.create(
            nombre_razon_social="Cliente Permitido",
            tipo_persona="FISICA",
            documento="PERMITIDO-001",
        )
        UsuarioCliente.objects.create(
            cliente=cliente_permitido,
            keycloak_user_id="kc-analista-idor",
            username="analista",
        )
        autenticar_con_roles(
            self,
            ["ANALISTA_CAMBIARIO"],
            sub="kc-analista-idor",
        )

        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": self.categoria.id},
        )

        self.assertEqual(response.status_code, 403)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.categoria)

    def test_analista_con_asociacion_inactiva_no_puede_segmentar_cliente(self):
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-analista-inactivo",
            username="analista-inactivo",
            activo=False,
        )
        autenticar_con_roles(
            self,
            ["ANALISTA_CAMBIARIO"],
            sub="kc-analista-inactivo",
        )

        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": self.categoria.id},
        )

        self.assertEqual(response.status_code, 403)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.categoria)


class SeleccionarClienteViewTest(TestCase):

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Operativo",
            tipo_persona="JURIDICA",
            documento="OPERAR-001",
        )

    def test_seleccionar_cliente_activo_guarda_contexto_en_sesion(self):
        response = self.client.post(
            reverse("seleccionar_cliente", args=[self.cliente.id])
        )

        self.assertRedirects(
            response,
            reverse("usuarios:dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session["selected_client"],
            {"id": self.cliente.id, "name": "Cliente Operativo"},
        )

    def test_cliente_inactivo_no_puede_seleccionarse(self):
        self.cliente.dar_de_baja()

        response = self.client.post(
            reverse("seleccionar_cliente", args=[self.cliente.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_dejar_de_seleccionar_elimina_contexto_de_sesion(self):
        session = self.client.session
        session["selected_client"] = {
            "id": self.cliente.id,
            "name": self.cliente.nombre_razon_social,
        }
        session.save()

        response = self.client.post(reverse("deseleccionar_cliente"))

        self.assertRedirects(
            response,
            reverse("consultar_clientes"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("selected_client", self.client.session)


class AsignacionUsuarioClienteTest(TestCase):

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Empresa Asignable",
            tipo_persona="JURIDICA",
            documento="ASIGNAR-001",
        )

    @patch("clientes.views.admin_request")
    def test_asignar_usuario_keycloak_a_cliente(self, admin_request):
        admin_request.return_value = [{
            "id": "kc-user-1",
            "username": "operador",
            "firstName": "Ana",
            "lastName": "Operadora",
        }]

        response = self.client.post(
            reverse("asignaciones_cliente", args=[self.cliente.id]),
            {"usuario": "kc-user-1", "rol_en_cliente": "OPERADOR"},
        )

        self.assertRedirects(
            response,
            reverse("asignaciones_cliente", args=[self.cliente.id]),
            fetch_redirect_response=False,
        )
        self.assertTrue(UsuarioCliente.objects.filter(
            cliente=self.cliente,
            keycloak_user_id="kc-user-1",
            rol_en_cliente="OPERADOR",
        ).exists())

    def test_usuario_autenticado_no_selecciona_cliente_sin_asignacion(self):
        session = self.client.session
        session["kc_user"] = {"sub": "kc-user-2", "preferred_username": "otro"}
        session[SESSION_USUARIO] = {"sub": "kc-user-2", "username": "otro"}
        session[SESSION_ROLES] = ["CAJERO"]
        session.save()

        response = self.client.post(reverse("seleccionar_cliente", args=[self.cliente.id]))

        self.assertEqual(response.status_code, 404)

    def test_usuario_sin_rol_administrador_no_abre_asignaciones(self):
        session = self.client.session
        session["roles"] = ["CAJERO"]
        session.save()

        response = self.client.get(
            reverse("asignaciones_cliente", args=[self.cliente.id])
        )

        self.assertEqual(response.status_code, 403)

    def test_no_permite_asignacion_duplicada(self):
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-user-unico",
            username="unico",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UsuarioCliente.objects.create(
                    cliente=self.cliente,
                    keycloak_user_id="kc-user-unico",
                    username="duplicado",
                )

    def test_relacion_admite_varios_clientes_y_varios_usuarios(self):
        segundo_cliente = Cliente.objects.create(
            nombre_razon_social="Segunda Empresa",
            tipo_persona="JURIDICA",
            documento="ASIGNAR-002",
        )
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-user-a",
            username="usuario-a",
        )
        UsuarioCliente.objects.create(
            cliente=segundo_cliente,
            keycloak_user_id="kc-user-a",
            username="usuario-a",
        )
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-user-b",
            username="usuario-b",
        )

        self.assertEqual(
            UsuarioCliente.objects.filter(keycloak_user_id="kc-user-a").count(),
            2,
        )
        self.assertEqual(self.cliente.usuarios_asignados.count(), 2)

    def test_fk_elimina_asignaciones_si_se_elimina_fisicamente_cliente(self):
        asignacion = UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-user-fk",
            username="usuario-fk",
        )

        self.cliente.delete()

        self.assertFalse(UsuarioCliente.objects.filter(id=asignacion.id).exists())


class SeguridadYMetodosClientesTest(TestCase):

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Métodos",
            tipo_persona="FISICA",
            documento="METODOS-001",
        )
        self.asignacion = UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-metodos",
            username="usuario-metodos",
        )

    def test_anonimo_es_redirigido_al_login(self):
        anonimo = DjangoClient()
        urls = [
            reverse("inicio_clientes"),
            reverse("registrar_cliente"),
            reverse("consultar_clientes"),
            reverse("editar_cliente", args=[self.cliente.id]),
            reverse("dar_de_baja_cliente", args=[self.cliente.id]),
            reverse("segmentar_cliente", args=[self.cliente.id]),
            reverse("asignaciones_cliente", args=[self.cliente.id]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = anonimo.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("usuarios:login"))

    def test_formularios_rechazan_metodos_no_soportados(self):
        urls = [
            reverse("registrar_cliente"),
            reverse("editar_cliente", args=[self.cliente.id]),
            reverse("dar_de_baja_cliente", args=[self.cliente.id]),
            reverse("segmentar_cliente", args=[self.cliente.id]),
            reverse("asignaciones_cliente", args=[self.cliente.id]),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.put(url).status_code, 405)

    def test_operaciones_mutables_requieren_post(self):
        urls = [
            reverse("seleccionar_cliente", args=[self.cliente.id]),
            reverse("deseleccionar_cliente"),
            reverse(
                "quitar_asignacion_cliente",
                args=[self.cliente.id, self.asignacion.id],
            ),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

        self.assertTrue(
            UsuarioCliente.objects.filter(id=self.asignacion.id).exists()
        )


class ClientesFrontendApiTest(TestCase):
    """Pruebas de los endpoints JSON utilizados por la interfaz Frontend."""

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente API",
            tipo_persona="FISICA",
            documento="API-001",
        )

    def test_crear_cliente(self):
        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data=json.dumps({
                "nombre_razon_social": "Cliente Nuevo API",
                "tipo_persona": "JURIDICA",
                "documento": "API-002",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Cliente.objects.filter(documento="API-002").exists()
        )
        self.assertEqual(
            response.json()["cliente"]["estado"],
            "ACTIVO",
        )

    def test_crear_cliente_con_documento_duplicado(self):
        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data=json.dumps({
                "nombre_razon_social": "Duplicado",
                "tipo_persona": "FISICA",
                "documento": "API-001",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            Cliente.objects.filter(nombre_razon_social="Duplicado").count(),
            0,
        )

    def test_crear_cliente_con_datos_invalidos(self):
        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data=json.dumps({
                "nombre_razon_social": "",
                "tipo_persona": "INVALIDO",
                "documento": "",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_crear_cliente_con_cuerpo_invalido(self):
        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data="no es json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_crear_cliente_requiere_administrador(self):
        autenticar_con_roles(self, ["USUARIO"], sub="usuario-basico")

        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data=json.dumps({
                "nombre_razon_social": "Sin Permiso",
                "tipo_persona": "FISICA",
                "documento": "API-003",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Cliente.objects.filter(documento="API-003").exists())

    def test_editar_cliente(self):
        response = self.client.post(
            reverse("clientes_api:editar_cliente", args=[self.cliente.id]),
            data=json.dumps({
                "nombre_razon_social": "Cliente API Editado",
                "tipo_persona": "JURIDICA",
                "documento": "API-004",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre_razon_social, "Cliente API Editado")
        self.assertEqual(self.cliente.tipo_persona, "JURIDICA")
        self.assertEqual(self.cliente.documento, "API-004")

    def test_editar_cliente_inexistente(self):
        response = self.client.post(
            reverse("clientes_api:editar_cliente", args=[999999]),
            data=json.dumps({
                "nombre_razon_social": "No Existe",
                "tipo_persona": "FISICA",
                "documento": "API-005",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_dar_de_baja_cliente(self):
        response = self.client.post(
            reverse("clientes_api:dar_de_baja_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado, "INACTIVO")
        self.assertTrue(Cliente.objects.filter(id=self.cliente.id).exists())

    def test_dar_de_baja_cliente_inexistente(self):
        response = self.client.post(
            reverse("clientes_api:dar_de_baja_cliente", args=[999999]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_dar_de_baja_cliente_deselecciona_si_era_el_activo(self):
        session = self.client.session
        session["selected_client"] = {
            "id": self.cliente.id,
            "name": self.cliente.nombre_razon_social,
        }
        session.save()

        response = self.client.post(
            reverse("clientes_api:dar_de_baja_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("selected_client", self.client.session)

    def test_seleccionar_cliente_activo(self):
        response = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session["selected_client"],
            {"id": self.cliente.id, "name": "Cliente API"},
        )

    def test_seleccionar_cliente_inactivo(self):
        self.cliente.dar_de_baja()

        response = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("selected_client", self.client.session)

    def test_no_administrador_selecciona_solo_cliente_asignado(self):
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-api-1",
            username="api-cajero",
        )
        autenticar_con_roles(self, ["CAJERO"], sub="kc-api-1")
        cliente_no_asignado = Cliente.objects.create(
            nombre_razon_social="Cliente Ajeno API",
            tipo_persona="JURIDICA",
            documento="API-006",
        )

        response_ok = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        response_sin_acceso = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[cliente_no_asignado.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response_ok.status_code, 200)
        self.assertEqual(
            self.client.session["selected_client"]["id"],
            self.cliente.id,
        )
        self.assertEqual(response_sin_acceso.status_code, 404)
        self.assertEqual(
            self.client.session["selected_client"]["id"],
            self.cliente.id,
        )

    def test_api_mutaciones_rechazan_get(self):
        urls = [
            reverse("clientes_api:crear_cliente"),
            reverse("clientes_api:editar_cliente", args=[self.cliente.id]),
            reverse("clientes_api:dar_de_baja_cliente", args=[self.cliente.id]),
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
