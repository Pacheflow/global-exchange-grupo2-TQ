import json
import time
from decimal import Decimal
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


class ComisionesCategoriasApiTests(TestCase):
    """Pruebas de la configuración persistente de comisiones."""

    def setUp(self):
        autenticar_admin(self)
        self.url = reverse("clientes_api:comisiones_categorias")
        self.minorista = CategoriaCliente.objects.get(nombre="Minorista")
        self.corporativo = CategoriaCliente.objects.get(nombre="Corporativo")
        self.vip = CategoriaCliente.objects.get(nombre="VIP")

    def test_administrador_actualiza_comisiones(self):
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "comisiones": [
                        {"id": self.minorista.id, "porcentaje_comision": "8.25"},
                        {"id": self.corporativo.id, "porcentaje_comision": "6.25"},
                        {"id": self.vip.id, "porcentaje_comision": "4.50"},
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.minorista.refresh_from_db()
        self.corporativo.refresh_from_db()
        self.vip.refresh_from_db()
        self.assertEqual(self.minorista.porcentaje_comision, Decimal("8.25"))
        self.assertEqual(self.corporativo.porcentaje_comision, Decimal("6.25"))
        self.assertEqual(self.vip.porcentaje_comision, Decimal("4.50"))

    def test_comision_fuera_de_rango_rechaza_todo_el_lote(self):
        original = self.minorista.porcentaje_comision

        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "comisiones": [
                        {"id": self.minorista.id, "porcentaje_comision": "101"},
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.minorista.refresh_from_db()
        self.assertEqual(self.minorista.porcentaje_comision, original)

    def test_usuario_no_administrador_no_puede_configurar_comisiones(self):
        autenticar_con_roles(self, ["USUARIO"], sub="usuario-basico")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)


class ClientesApiEsencialesTests(TestCase):
    """Pruebas esenciales del registro, edición y baja lógica de clientes."""

    def setUp(self):
        autenticar_admin(self)

    def test_administrador_crea_cliente_activo(self):
        """Comprueba que un administrador pueda registrar un cliente válido.

        Se espera que el cliente se cree en estado ACTIVO.
        """
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
        """Comprueba que no se permita crear un cliente con datos obligatorios inválidos.

        Se espera que la solicitud sea rechazada y no se guarde ningún cliente.
        """
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
        """Comprueba que el documento de un cliente sea único.

        Se espera que la creación con un documento ya registrado sea rechazada con conflicto (409).
        """
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
        """Comprueba que únicamente los administradores puedan crear clientes.

        Se espera que un usuario sin rol de administrador reciba acceso denegado (403).

        Requisito relacionado: RNF-02.
        """
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
        """Comprueba que un administrador pueda editar los datos de un cliente.

        Se espera que los cambios se persistan correctamente.
        """
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
        """Comprueba que la edición no permita asignar a un cliente el documento de otro.

        Se espera que el cambio sea rechazado y se conserve el documento original.
        """
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
        """Comprueba que dar de baja a un cliente lo desactive sin eliminar su registro.

        Se espera que el cliente quede INACTIVO y, si estaba seleccionado, se limpie
        el contexto de trabajo de la sesión.
        """
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
    """Pruebas de consulta de clientes asignados y de su segmentación comercial."""

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Principal",
            tipo_persona="FISICA",
            documento="CONSULTA-001",
        )

    def test_usuario_no_administrador_solo_consulta_clientes_asignados(self):
        """Comprueba que un usuario sin rol de administrador solo consulte sus clientes asignados.

        Se espera que los clientes ajenos no aparezcan en el listado.

        Requisito relacionado: RF-05.
        """
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

    def test_analista_no_puede_consultar_ni_seleccionar_clientes(self):
        """El modo analista queda limitado a funciones relacionadas con tasas."""

        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-analista-clientes",
            username="analista.clientes",
        )
        autenticar_con_roles(
            self,
            ["ANALISTA_CAMBIARIO"],
            sub="kc-analista-clientes",
        )

        consulta = self.client.get(reverse("consultar_clientes"))
        seleccion = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(consulta.status_code, 403)
        self.assertEqual(seleccion.status_code, 403)
        self.assertNotIn("selected_client", self.client.session)

    def test_administrador_segmenta_cliente(self):
        """Comprueba que un administrador pueda asignar una categoría comercial a un cliente.

        Se espera que la segmentación quede guardada.

        Requisito relacionado: RF-24.
        """
        categoria = CategoriaCliente.objects.get(nombre="Corporativo")

        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": categoria.id},
        )

        self.assertEqual(response.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.categoria, categoria)

    def test_no_administrador_no_puede_segmentar_cliente(self):
        """Comprueba que solo los administradores puedan segmentar clientes.

        Se espera que un usuario sin ese rol reciba acceso denegado (403).

        Requisito relacionado: RNF-02.
        """
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
        """Comprueba que un cliente dado de baja no pueda seleccionarse como contexto.

        Se espera que la selección sea rechazada (404) y no quede cliente activo en la sesión.

        Requisito relacionado: RF-05.
        """
        self.cliente.dar_de_baja()

        response = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("selected_client", self.client.session)


class AsignacionClientesTests(TestCase):
    """Pruebas de asignación de usuarios de Keycloak a clientes."""

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Empresa Asignable",
            tipo_persona="JURIDICA",
            documento="ASIGNAR-001",
        )

    @patch("clientes.views.admin_request")
    def test_administrador_asigna_identidad_keycloak_a_cliente(self, admin_request):
        """Comprueba que un administrador pueda asignar un usuario de Keycloak a un cliente.

        Se espera que la asignación quede registrada con su rol de cliente.

        Requisito relacionado: RF-04.
        """
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
        """Comprueba que la relación entre usuarios y clientes sea de muchos a muchos.

        Se espera que un usuario pueda estar asociado a varios clientes y viceversa.

        Requisito relacionado: RF-04.
        """
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
        """Comprueba que no se permita asignar dos veces el mismo usuario a un cliente.

        Se espera que la base de datos rechace la duplicación con IntegrityError.
        """
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
        """Comprueba que únicamente los administradores puedan gestionar asignaciones.

        Se espera que un usuario sin ese rol reciba acceso denegado (403).

        Requisito relacionado: RNF-02.
        """
        autenticar_con_roles(self, ["CAJERO"], sub="kc-cajero")

        response = self.client.get(
            reverse("asignaciones_cliente", args=[self.cliente.id])
        )

        self.assertEqual(response.status_code, 403)


class ContextoClienteTests(TestCase):
    """Pruebas de selección, cambio y deselección del cliente de trabajo."""

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
        """Comprueba que el usuario pueda cambiar de cliente activo y deseleccionarlo.

        Se espera que la selección actualice el contexto de trabajo y que la
        deselección lo elimine de la sesión.

        Requisito relacionado: RF-06.
        """
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
        """Comprueba que un usuario solo pueda seleccionar los clientes que le fueron asignados.

        Se espera que la selección de un cliente ajeno sea rechazada (404) y se
        conserve el contexto actual.

        Requisito relacionado: RF-05.
        """
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
    """Pruebas de selección del método de pago preferido de un cliente.

    Requisito relacionado: RF-26.
    """

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
        """Comprueba que varios clientes puedan tener el mismo método de pago preferido.

        Se espera que un método pueda asociarse a más de un cliente.
        """
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
        """Comprueba que un usuario con acceso al cliente pueda establecer su método preferido.

        Se espera que la preferencia quede guardada.
        """
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
        """Comprueba que un usuario pueda cambiar el método de pago preferido de su cliente.

        Se espera que la nueva preferencia reemplace a la anterior.
        """
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
        """Comprueba que la consulta de preferencias ofrezca únicamente métodos activos.

        Se espera que la preferencia actual se informe aun si quedó inactiva y que
        los métodos inactivos no estén disponibles para elegir.
        """
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
        """Comprueba que no se permita seleccionar un método de pago inactivo como preferido.

        Se espera que la solicitud sea rechazada y el cliente conserve su preferencia previa.
        """
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
        """Comprueba que no se permita seleccionar un método de pago inexistente.

        Se espera que la solicitud sea rechazada (404) y el cliente quede sin preferencia.
        """
        response = self.client.post(
            self.url,
            data=json.dumps({"metodo_pago_id": 999999}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.metodo_pago_preferido)

    def test_usuario_sin_acceso_no_puede_modificar_preferencia(self):
        """Comprueba que un usuario sin acceso a un cliente no pueda modificar su preferencia.

        Se espera que la solicitud sea rechazada (403) y no se modifique el cliente.

        Requisito relacionado: RNF-02.
        """
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
        """Comprueba que una preferencia no se elimine cuando el método queda inactivo.

        Se espera que la preferencia se conserve y que la interfaz informe que el
        método ya no está disponible, permitiendo elegir otro.
        """
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
