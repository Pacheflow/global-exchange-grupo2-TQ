import json
import time
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from metodos_pago.models import MetodoPago
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import CategoriaCliente, Cliente, UsuarioCliente


def autenticar_con_roles(test_case, roles, *, sub="admin-id"):
    session = test_case.client.session
    session["kc_user"] = {"sub": sub, "preferred_username": "usuario"}
    session[SESSION_AUTENTICADO] = True
    session[SESSION_USUARIO] = {"sub": sub, "username": "usuario"}
    session[SESSION_ROLES] = roles
    session[SESSION_EXPIRA_EN] = int(time.time()) + 600
    session.save()


def autenticar_admin(test_case):
    autenticar_con_roles(test_case, ["ADMINISTRADOR"])


class ClientesApiEsencialesTests(TestCase):
    def setUp(self):
        autenticar_admin(self)

    def test_administrador_crea_cliente_activo(self):
        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data=json.dumps({
                "nombre_razon_social": "Cliente Nuevo",
                "tipo_persona": "JURIDICA",
                "documento": "CLI-001",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        cliente = Cliente.objects.get(documento="CLI-001")
        self.assertEqual(cliente.estado, "ACTIVO")

    def test_creacion_rechaza_datos_obligatorios_invalidos(self):
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
        self.assertFalse(Cliente.objects.exists())

    def test_creacion_rechaza_documento_duplicado(self):
        Cliente.objects.create(
            nombre_razon_social="Cliente Existente",
            tipo_persona="FISICA",
            documento="DOC-001",
        )

        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data=json.dumps({
                "nombre_razon_social": "Cliente Duplicado",
                "tipo_persona": "JURIDICA",
                "documento": "DOC-001",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(
            Cliente.objects.filter(nombre_razon_social="Cliente Duplicado").exists()
        )

    def test_usuario_no_administrador_no_puede_crear_cliente(self):
        autenticar_con_roles(self, ["USUARIO"], sub="usuario-basico")

        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data=json.dumps({
                "nombre_razon_social": "Cliente Sin Permiso",
                "tipo_persona": "FISICA",
                "documento": "SIN-PERMISO-001",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Cliente.objects.filter(documento="SIN-PERMISO-001").exists())

    def test_administrador_edita_cliente(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Original",
            tipo_persona="FISICA",
            documento="EDIT-001",
        )

        response = self.client.post(
            reverse("clientes_api:editar_cliente", args=[cliente.id]),
            data=json.dumps({
                "nombre_razon_social": "Cliente Editado",
                "tipo_persona": "JURIDICA",
                "documento": "EDIT-002",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre_razon_social, "Cliente Editado")
        self.assertEqual(cliente.tipo_persona, "JURIDICA")
        self.assertEqual(cliente.documento, "EDIT-002")

    def test_edicion_rechaza_documento_existente(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Editable",
            tipo_persona="FISICA",
            documento="EDIT-UNICO-001",
        )
        Cliente.objects.create(
            nombre_razon_social="Otro Cliente",
            tipo_persona="JURIDICA",
            documento="EDIT-UNICO-002",
        )

        response = self.client.post(
            reverse("clientes_api:editar_cliente", args=[cliente.id]),
            data=json.dumps({
                "nombre_razon_social": "Cambio Rechazado",
                "tipo_persona": "FISICA",
                "documento": "EDIT-UNICO-002",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        cliente.refresh_from_db()
        self.assertEqual(cliente.documento, "EDIT-UNICO-001")

    def test_baja_logica_conserva_cliente_y_limpia_contexto(self):
        cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Activo",
            tipo_persona="FISICA",
            documento="BAJA-001",
        )
        session = self.client.session
        session["selected_client"] = {
            "id": cliente.id,
            "name": cliente.nombre_razon_social,
        }
        session.save()

        response = self.client.post(
            reverse("clientes_api:dar_de_baja_cliente", args=[cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual(cliente.estado, "INACTIVO")
        self.assertTrue(Cliente.objects.filter(id=cliente.id).exists())
        self.assertNotIn("selected_client", self.client.session)


class ConsultaYSegmentacionClientesTests(TestCase):
    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Principal",
            tipo_persona="FISICA",
            documento="CONSULTA-001",
        )

    def test_usuario_no_administrador_solo_consulta_clientes_asignados(self):
        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente Ajeno",
            tipo_persona="JURIDICA",
            documento="CONSULTA-002",
        )
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-consulta",
            username="consulta",
        )
        autenticar_con_roles(self, ["CAJERO"], sub="kc-consulta")

        response = self.client.get(reverse("consultar_clientes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.cliente.nombre_razon_social)
        self.assertNotContains(response, cliente_ajeno.nombre_razon_social)

    def test_administrador_segmenta_cliente(self):
        categoria = CategoriaCliente.objects.get(nombre="Corporativo")

        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": categoria.id},
        )

        self.assertEqual(response.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.categoria, categoria)

    def test_no_administrador_no_puede_segmentar_cliente(self):
        categoria = CategoriaCliente.objects.create(nombre="Preferencial")
        autenticar_con_roles(self, ["ANALISTA_CAMBIARIO"], sub="kc-analista")

        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": categoria.id},
        )

        self.assertEqual(response.status_code, 403)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.categoria)

    def test_cliente_inactivo_no_puede_seleccionarse(self):
        self.cliente.dar_de_baja()

        response = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("selected_client", self.client.session)


class AsignacionClientesTests(TestCase):
    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Empresa Asignable",
            tipo_persona="JURIDICA",
            documento="ASIGNAR-001",
        )

    @patch("clientes.views.admin_request")
    def test_administrador_asigna_identidad_keycloak_a_cliente(self, admin_request):
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

        self.assertEqual(response.status_code, 302)
        self.assertTrue(UsuarioCliente.objects.filter(
            cliente=self.cliente,
            keycloak_user_id="kc-user-1",
            rol_en_cliente="OPERADOR",
        ).exists())

    def test_asociacion_admite_muchos_a_muchos(self):
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

    def test_no_permite_asignacion_duplicada(self):
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-user-unico",
            username="usuario-original",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UsuarioCliente.objects.create(
                    cliente=self.cliente,
                    keycloak_user_id="kc-user-unico",
                    username="usuario-duplicado",
                )

    def test_usuario_no_administrador_no_puede_gestionar_asignaciones(self):
        autenticar_con_roles(self, ["CAJERO"], sub="kc-cajero")

        response = self.client.get(
            reverse("asignaciones_cliente", args=[self.cliente.id])
        )

        self.assertEqual(response.status_code, 403)


class ContextoClienteTests(TestCase):
    def setUp(self):
        autenticar_admin(self)
        self.primer_cliente = Cliente.objects.create(
            nombre_razon_social="Primer Cliente",
            tipo_persona="FISICA",
            documento="CONTEXTO-001",
        )
        self.segundo_cliente = Cliente.objects.create(
            nombre_razon_social="Segundo Cliente",
            tipo_persona="JURIDICA",
            documento="CONTEXTO-002",
        )

    def test_cambiar_y_deseleccionar_cliente_actualiza_contexto(self):
        primera_seleccion = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.primer_cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(primera_seleccion.status_code, 200)
        self.assertEqual(
            self.client.session["selected_client"]["id"],
            self.primer_cliente.id,
        )

        segunda_seleccion = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.segundo_cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(segunda_seleccion.status_code, 200)
        self.assertEqual(
            self.client.session["selected_client"]["id"],
            self.segundo_cliente.id,
        )

        deseleccion = self.client.post(reverse("deseleccionar_cliente"))
        self.assertEqual(deseleccion.status_code, 302)
        self.assertNotIn("selected_client", self.client.session)

    def test_usuario_solo_selecciona_cliente_asignado(self):
        UsuarioCliente.objects.create(
            cliente=self.primer_cliente,
            keycloak_user_id="kc-operador",
            username="operador",
        )
        autenticar_con_roles(self, ["CAJERO"], sub="kc-operador")

        response_permitida = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.primer_cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response_permitida.status_code, 200)
        self.assertEqual(
            self.client.session["selected_client"]["id"],
            self.primer_cliente.id,
        )

        response_ajena = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.segundo_cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response_ajena.status_code, 404)
        self.assertEqual(
            self.client.session["selected_client"]["id"],
            self.primer_cliente.id,
        )


class MetodoPagoPreferidoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente con preferencia",
            tipo_persona="JURIDICA",
            documento="PREFERENCIA-001",
        )
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-preferencia",
            username="usuario.preferencia",
        )
        autenticar_con_roles(self, ["USUARIO"], sub="kc-preferencia")
        self.url = reverse(
            "clientes_api:actualizar_metodo_pago_preferido",
            args=[self.cliente.id],
        )

    def test_varios_clientes_pueden_preferir_el_mismo_metodo(self):
        metodo = MetodoPago.objects.create(nombre="Transferencia bancaria")
        segundo_cliente = Cliente.objects.create(
            nombre_razon_social="Segundo cliente",
            tipo_persona="FISICA",
            documento="PREFERENCIA-002",
            metodo_pago_preferido=metodo,
        )
        self.cliente.metodo_pago_preferido = metodo
        self.cliente.save(update_fields=["metodo_pago_preferido"])

        self.assertEqual(metodo.clientes_preferentes.count(), 2)
        self.assertEqual(segundo_cliente.metodo_pago_preferido, metodo)

    def test_usuario_autorizado_establece_metodo_activo(self):
        metodo = MetodoPago.objects.create(nombre="Efectivo")

        response = self.client.post(
            self.url,
            data=json.dumps({"metodo_pago_id": metodo.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.metodo_pago_preferido, metodo)

    def test_usuario_autorizado_cambia_metodo_activo(self):
        anterior = MetodoPago.objects.create(nombre="Efectivo")
        nuevo = MetodoPago.objects.create(nombre="Tarjeta")
        self.cliente.metodo_pago_preferido = anterior
        self.cliente.save(update_fields=["metodo_pago_preferido"])

        response = self.client.post(
            self.url,
            data=json.dumps({"metodo_pago_id": nuevo.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.metodo_pago_preferido, nuevo)

    def test_consulta_ofrece_solo_metodos_activos(self):
        activo = MetodoPago.objects.create(nombre="Efectivo")
        inactivo = MetodoPago.objects.create(nombre="Cheque", activo=False)
        self.cliente.metodo_pago_preferido = inactivo
        self.cliente.save(update_fields=["metodo_pago_preferido"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metodo_pago_preferido"]["id"], inactivo.id)
        self.assertFalse(response.json()["metodo_pago_preferido"]["activo"])
        self.assertEqual(response.json()["metodos_disponibles"][0]["id"], activo.id)
        self.assertEqual(len(response.json()["metodos_disponibles"]), 1)

    def test_metodo_inactivo_no_puede_seleccionarse(self):
        metodo = MetodoPago.objects.create(nombre="Cheque", activo=False)

        response = self.client.post(
            self.url,
            data=json.dumps({"metodo_pago_id": metodo.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.metodo_pago_preferido)

    def test_metodo_inexistente_es_rechazado(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"metodo_pago_id": 999999}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.metodo_pago_preferido)

    def test_usuario_sin_acceso_no_puede_modificar_preferencia(self):
        metodo = MetodoPago.objects.create(nombre="Efectivo")
        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente ajeno",
            tipo_persona="JURIDICA",
            documento="PREFERENCIA-AJENA",
        )
        url_ajena = reverse(
            "clientes_api:actualizar_metodo_pago_preferido",
            args=[cliente_ajeno.id],
        )

        response = self.client.post(
            url_ajena,
            data=json.dumps({"metodo_pago_id": metodo.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        cliente_ajeno.refresh_from_db()
        self.assertIsNone(cliente_ajeno.metodo_pago_preferido)

    def test_preferencia_permanece_y_la_interfaz_informa_si_queda_inactiva(self):
        metodo = MetodoPago.objects.create(nombre="Transferencia bancaria")
        self.cliente.metodo_pago_preferido = metodo
        self.cliente.save(update_fields=["metodo_pago_preferido"])
        metodo.desactivar()
        session = self.client.session
        session["selected_client"] = {
            "id": self.cliente.id,
            "name": self.cliente.nombre_razon_social,
        }
        session.save()

        response = self.client.get(reverse("consultar_clientes"))

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.metodo_pago_preferido, metodo)
        self.assertContains(response, "Transferencia bancaria")
        self.assertContains(response, "Inactivo")
        self.assertContains(response, "Este método ya no está disponible")
