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
    """Configura la sesión de pruebas con roles Keycloak y usuario OIDC.

    Puebla ``request.session`` con las claves usadas por los decorators
    de la app (``kc_user``, roles, ``sub`` y usuario de la sesión) y
    guarda la sesión del cliente de pruebas.

    Args:
        test_case: Instancia de la clase de test que invoca el helper
            (aporta ``self.client.session``).
        roles (list[str]): Roles de negocio que se guardan en la sesión.
        sub (str): Identificador Keycloak (``sub``) del usuario.
        incluir_kc_user (bool): Si es ``True`` agrega ``kc_user`` a la
            sesión; si es ``False`` lo elimina para simular una sesión
            sin identidad Keycloak.
    """
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
    """Autentica al cliente de pruebas como administrador.

    Invoca ``autenticar_con_roles`` con el rol ``ADMINISTRADOR``,
    configurando la sesión del cliente de pruebas a través del helper.

    Args:
        test_case: Instancia de la clase de test que llama al helper.
    """
    autenticar_con_roles(test_case, ["ADMINISTRADOR"])


class ClienteModelTest(TestCase):
    """Pruebas del modelo ``Cliente`` y su formulario ``ClienteForm``.

    Verifica la creación de categorías y clientes, el estado ``ACTIVO``
    por defecto, la baja lógica y las validaciones del formulario:
    obligatoriedad de nombre y documento, unicidad del documento y tipos
    de persona admitidos.
    """

    def test_crear_categoria_cliente(self):
        """Verifica la creación de una categoría de cliente.

        Escenario: se crea ``CategoriaCliente`` con nombre
        "Categoria Prueba" y descripción.
        Resultado esperado: ``categoria.nombre`` coincide con el valor
        enviado.
        """
        categoria = CategoriaCliente.objects.create(
            nombre="Categoria Prueba",
            descripcion="Categoría utilizada para pruebas"
        )

        self.assertEqual(
            categoria.nombre,
            "Categoria Prueba"
        )

    def test_crear_cliente(self):
        """Verifica la creación de un cliente.

        Escenario: ``Cliente.objects.create`` con nombre "Cliente
        Prueba", tipo FISICA y documento "123456".
        Resultado esperado: ``cliente.nombre_razon_social`` coincide con
        el valor enviado.
        """
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
        """Verifica que el estado por defecto del cliente es ``ACTIVO``.

        Escenario: se crea un cliente sin especificar estado.
        Resultado esperado: ``cliente.estado == "ACTIVO"``.
        """
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
        """Verifica la baja lógica de un cliente.

        Escenario: se crea un cliente y se invoca ``dar_de_baja()``.
        Resultado esperado: ``cliente.estado == "INACTIVO"``.
        """
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
        """Verifica que el documento no puede repetirse a nivel de form.

        Escenario: ya existe "Primer Cliente" FISICA con documento
        "333333"; el ``ClienteForm`` intenta registrar a "Segundo
        Cliente" con el mismo documento.
        Resultado esperado: ``form.is_valid()`` es ``False``.
        """
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
        """Verifica que el documento admite caracteres alfanuméricos.

        Escenario: ``Cliente`` con documento "AB123456".
        Resultado esperado: ``cliente.documento == "AB123456"``.
        """
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
        """Verifica que el documento admite guiones.

        Escenario: ``Cliente`` con documento "80012345-6".
        Resultado esperado: ``cliente.documento == "80012345-6"``.
        """
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
        """Verifica que el nombre/razón social es obligatorio.

        Escenario: ``ClienteForm`` sin ``nombre_razon_social``.
        Resultado esperado: ``form.is_valid()`` es ``False``.
        """
        form = ClienteForm(data={
            "nombre_razon_social": "",
            "tipo_persona": "FISICA",
            "documento": "555555"
        })

        self.assertFalse(
            form.is_valid()
        )

    def test_documento_es_obligatorio(self):
        """Verifica que el documento es obligatorio.

        Escenario: ``ClienteForm`` sin ``documento``.
        Resultado esperado: ``form.is_valid()`` es ``False``.
        """
        form = ClienteForm(data={
            "nombre_razon_social": "Cliente Sin Documento",
            "tipo_persona": "FISICA",
            "documento": ""
        })

        self.assertFalse(
            form.is_valid()
        )

    def test_tipo_persona_invalido(self):
        """Verifica el rechazo de un tipo de persona inválido.

        Escenario: ``ClienteForm`` con ``tipo_persona`` no soportado.
        Resultado esperado: ``form.is_valid()`` es ``False``.
        """
        form = ClienteForm(data={
            "nombre_razon_social": "Cliente Prueba",
            "tipo_persona": "OTRO",
            "documento": "666666"
        })

        self.assertFalse(
            form.is_valid()
        )


class RegistrarClienteViewTest(TestCase):
    """Pruebas de la vista de registro de clientes.

    Verifica el render del formulario ``clientes/registrar.html``, el
    registro por POST, el rechazo de usuarios sin rol administrador y la
    no-creación de clientes con datos inválidos.
    """

    def setUp(self):
        autenticar_admin(self)

    def test_mostrar_formulario_registro(self):
        """Verifica el render del formulario de registro (GET).

        Resultado esperado: status 200 y el template
        ``clientes/registrar.html``.
        """
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
        """Verifica el registro de un cliente por POST.

        Escenario: se envía "Cliente Nuevo", FISICA y documento "444444".
        Resultado esperado: redirección (302) y que exista un ``Cliente``
        con ese documento (``Cliente.objects.filter(...).exists()``).
        """
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
        """Verifica que un usuario sin rol administrador es rechazado.

        Escenario: sesión autenticada con rol "USUARIO" y GET a
        ``registrar_cliente``.
        Resultado esperado: status 403.
        """
        autenticar_con_roles(self, ["USUARIO"], sub="usuario-basico")

        response = self.client.get(reverse("registrar_cliente"))

        self.assertEqual(response.status_code, 403)

    def test_no_registra_cliente_con_datos_invalidos(self):
        """Verifica que datos inválidos no registran al cliente.

        Escenario: POST con nombre vacío, tipo "INVALIDO" y documento
        vacío; espera re-render sin redirección.
        Resultado esperado: status 200 y que no exista ningún ``Cliente``
        en la base de datos (``Cliente.objects.exists()`` es ``False``).
        """
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
    """Pruebas de la vista de consulta de clientes.

    Verifica la consulta con todos los clientes, la búsqueda por texto
    (por nombre), el mensaje de "sin resultados", el filtrado por
    asignaciones para no administradores y el rechazo de sesiones sin
    identidad Keycloak.
    """

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Consulta",
            tipo_persona="FISICA",
            documento="CONSULTA-001"
        )

    def test_consultar_clientes(self):
        """Verifica el listado de clientes.

        Escenario: sesión administradora y GET a
        ``consultar_clientes``.
        Resultado esperado: status 200 y que la respuesta contenga el
        nombre "Cliente Consulta" (``assertContains``).
        """
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
        """Verifica la búsqueda de clientes por nombre.

        Escenario: GET a ``consultar_clientes`` con ``buscar`` =
        "Consulta".
        Resultado esperado: la respuesta contiene "Cliente Consulta"
        (``assertContains``).
        """
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
        """Verifica el mensaje cuando la búsqueda no tiene resultados.

        Escenario: GET a ``consultar_clientes`` con ``buscar`` =
        "NoExiste".
        Resultado esperado: la respuesta contiene el texto "No se
        encontraron clientes." (``assertContains``).
        """
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
        """Verifica que un no administrativo solo ve sus asignados.

        Escenario: existe "Cliente Ajeno" (sin asignación); se asigna
        ``self.cliente`` al usuario ``cajero`` vía ``UsuarioCliente`` y
        se autentica con rol "CAJERO" y ``sub`` "kc-cajero-1".
        Resultado esperado: status 200, la respuesta contiene al cliente
        asignado y NO contiene a "Cliente Ajeno" (``assertContains`` y
        ``assertNotContains``).
        """
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
        """Verifica que sin asignaciones no se ven clientes.

        Escenario: sesión autenticada con rol "USUARIO" y ``sub``
        "kc-sin-asignacion" (sin ``UsuarioCliente`` asociado); GET a
        ``consultar_clientes``.
        Resultado esperado: status 200, no contiene al cliente creado en
        ``setUp`` y muestra el mensaje "No tenés clientes asociados
        disponibles.".
        """
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
        """Verifica el rechazo de una sesión sin identidad Keycloak.

        Escenario: sesión autenticada con rol "CAJERO" y ``sub``
        "kc-oidc-valido" pero sin ``kc_user`` (``incluir_kc_user``
        ``False``); GET a ``consultar_clientes``.
        Resultado esperado: status 403 y que la respuesta NO contenga al
        cliente creado en ``setUp`` (``assertNotContains``).
        """
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
    """Pruebas de la vista de edición de clientes.

    Verifica que un administrador puede editar nombre, tipo de persona y
    documento; la unicidad del documento al editar (se rechaza un
    documento que ya pertenezca a otro cliente), el 404 para clientes
    inexistentes y que datos inválidos no modifican al cliente.
    """

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Original",
            tipo_persona="FISICA",
            documento="EDITAR-001"
        )

    def test_editar_cliente(self):
        """Verifica la edición de un cliente existente.

        Escenario: POST a ``editar_cliente`` con el id de
        ``self.cliente`` y los valores "Cliente Editado", "JURIDICA" y
        documento "EDITAR-001".
        Resultado esperado: redirección (302) y, tras
        ``refresh_from_db()``, los nuevos valores en
        ``nombre_razon_social`` y ``tipo_persona``.
        """
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
        """Verifica que no se permite duplicar documento al editar.

        Escenario: ya existe "Otro Cliente" con documento
        "DOCUMENTO-OTRO"; POST a ``editar_cliente`` intenta asignar ese
        mismo documento a ``self.cliente``.
        Resultado esperado: status 200 (re-render, sin redirección) y
        que ``self.cliente.documento`` siga siendo "EDITAR-001" tras
        ``refresh_from_db()``.
        """
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
        """Verifica que editar un cliente inexistente devuelve 404.

        Escenario: GET a ``editar_cliente`` con id ``999999``.
        Resultado esperado: ``response.status_code`` es 404.
        """
        response = self.client.get(reverse("editar_cliente", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_datos_invalidos_no_modifican_cliente(self):
        """Verifica que datos inválidos no modifican al cliente.

        Escenario: POST a ``editar_cliente`` con nombre vacío, tipo
        "INVALIDO" y documento vacío; espera re-render sin
        redirección.
        Resultado esperado: status 200 y que tras ``refresh_from_db()``
        el cliente conserve nombre "Cliente Original" y documento
        "EDITAR-001".
        """
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
    """Pruebas de la vista de baja lógica de clientes.

    Verifica la baja de un cliente existente (estado ``INACTIVO``), el
    404 para un cliente inexistente y la idempotencia de la baja
    repetida: el cliente se conserva en la base de datos tras la
    segunda ejecución.
    """

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Baja Vista",
            tipo_persona="FISICA",
            documento="BAJA-001"
        )

    def test_dar_de_baja_cliente(self):
        """Verifica la baja lógica de un cliente existente.

        Escenario: POST a ``dar_de_baja_cliente`` con el id del cliente
        creado en ``setUp`` (estado ACTIVO).
        Resultado esperado: redirección (302) y, tras
        ``refresh_from_db()``, ``estado == "INACTIVO"`` (el registro
        sigue existiendo en ``Cliente.objects``).
        """
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
        """Verifica el 404 al intentar dar de baja un cliente inexistente.

        Escenario: POST a ``dar_de_baja_cliente`` con id ``999999``.
        Resultado esperado: ``response.status_code == 404``.
        """
        response = self.client.post(
            reverse("dar_de_baja_cliente", args=[999999])
        )

        self.assertEqual(response.status_code, 404)

    def test_baja_repetida_es_idempotente(self):
        """Verifica que la baja repetida es idempotente.

        Escenario: dos POST consecutivos a ``dar_de_baja_cliente`` con
        el id del cliente.
        Resultado esperado: ambos devuelven 302 y, tras
        ``refresh_from_db()``, ``estado == "INACTIVO"``; el registro
        sigue existiendo en ``Cliente.objects``
        (``filter(id=...).exists()`` es ``True``).
        """
        url = reverse("dar_de_baja_cliente", args=[self.cliente.id])

        primera_respuesta = self.client.post(url)
        segunda_respuesta = self.client.post(url)

        self.assertEqual(primera_respuesta.status_code, 302)
        self.assertEqual(segunda_respuesta.status_code, 302)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado, "INACTIVO")
        self.assertTrue(Cliente.objects.filter(id=self.cliente.id).exists())


class SegmentarClienteViewTest(TestCase):
    """Pruebas de la vista de segmentación de clientes.

    Verifica la segmentación (asignación de categoría), el cambio de
    categoría, el 404 para clientes inexistentes, el no-modificar al
    cliente con una categoría inexistente y las restricciones por rol/asociación:
    un analista no administrador no puede segmentar, tampoco si la
    asociación al cliente es ajena o está inactiva.
    """

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
        """Verifica la segmentación de un cliente con una categoría.

        Escenario: POST a ``segmentar_cliente`` con el id de
        ``self.cliente`` y ``{"categoria": self.categoria.id}``.
        Resultado esperado: redirección (302) y que tras
        ``refresh_from_db()`` ``self.cliente.categoria == self.categoria``.
        """
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
        """Verifica el cambio de categoría de un cliente ya segmentado.

        Escenario: ``self.cliente`` con categoría ``VIP``; POST a
        ``segmentar_cliente`` con ``otra_categoria`` "Corporativo
        Prueba".
        Resultado esperado: tras ``refresh_from_db()``
        ``self.cliente.categoria == otra_categoria``.
        """
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
        """Verifica que segmentar un cliente inexistente devuelve 404.

        Escenario: GET a ``segmentar_cliente`` con id ``999999``.
        Resultado esperado: ``response.status_code == 404``.
        """
        response = self.client.get(reverse("segmentar_cliente", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_categoria_inexistente_no_modifica_cliente(self):
        """Verifica que una categoría inexistente no modifica al cliente.

        Escenario: POST a ``segmentar_cliente`` con
        ``{"categoria": 999999}``.
        Resultado esperado: status 200 y ``self.cliente.categoria``
        sigue siendo ``None`` tras ``refresh_from_db()``.
        """
        response = self.client.post(
            reverse("segmentar_cliente", args=[self.cliente.id]),
            {"categoria": 999999},
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.categoria)

    def test_analista_asociado_no_puede_segmentar_cliente(self):
        """Verifica que un analista asociado sin rol admin no segmenta.

        Escenario: ``UsuarioCliente`` asociando a ``self.cliente`` con
        ``kc-analista-1``; sesión autenticada con rol
        ``ANALISTA_CAMBIARIO`` y ``sub`` ``kc-analista-1``; POST a
        ``segmentar_cliente``.
        Resultado esperado: status 403 y que ``self.cliente.categoria``
        siga siendo ``None``.
        """
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
        """Verifica que un analista no puede segmentar un cliente ajeno.

        Escenario: ``cliente_permitido`` está asociado al analista
        (``UsuarioCliente``), pero ``self.cliente`` NO; sesión
        autenticada con ``ANALISTA_CAMBIARIO`` y ``sub``
        ``kc-analista-idor``; POST a ``segmentar_cliente`` con
        ``self.cliente.id``.
        Resultado esperado: status 403 y que ``self.cliente.categoria``
        siga siendo ``None`` (no se toca el cliente ajeno).
        """
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
        """Verifica que una asociación inactiva no permite segmentar.

        Escenario: ``UsuarioCliente`` con ``activo=False``
        (``kc-analista-inactivo``) asociado a ``self.cliente``; sesión
        con rol ``ANALISTA_CAMBIARIO`` y ``sub`` ``kc-analista-inactivo``;
        POST a ``segmentar_cliente``.
        Resultado esperado: status 403 y que ``self.cliente.categoria``
        siga siendo ``None``.
        """
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
    """Pruebas de la selección de un cliente activo como contexto.

    Verifica que POST a ``seleccionar_cliente`` guarda el cliente
    activo en ``session["selected_client"]`` (con ``id`` y ``name``)
    y redirige al dashboard de usuarios; que un cliente inactivo no
    es seleccionable (404) y que ``deseleccionar_cliente`` elimina el
    contexto de la sesión.
    """

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Operativo",
            tipo_persona="JURIDICA",
            documento="OPERAR-001",
        )

    def test_seleccionar_cliente_activo_guarda_contexto_en_sesion(self):
        """Verifica que seleccionar un cliente activo guarda contexto.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``
        ("Cliente Operativo", JURIDICA, "OPERAR-001"); POST a
        ``seleccionar_cliente`` con su id.
        Resultado esperado: ``assertRedirects`` al
        ``usuarios:dashboard`` (sin seguir redirecciones) y que
        ``session["selected_client"]`` sea el dict
        ``{"id": self.cliente.id, "name": "Cliente Operativo"}``.
        """
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
        """Verifica que un cliente inactivo no es seleccionable.

        Escenario: se invoca ``self.cliente.dar_de_baja()`` y luego POST
        a ``seleccionar_cliente`` con su id.
        Resultado esperado: ``response.status_code == 404``.
        """
        self.cliente.dar_de_baja()

        response = self.client.post(
            reverse("seleccionar_cliente", args=[self.cliente.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_dejar_de_seleccionar_elimina_contexto_de_sesion(self):
        """Verifica que deseleccionar elimina el contexto de la sesión.

        Escenario: ``setUp`` autentica admin; se precarga
        ``session["selected_client"]`` con el dict del cliente y se
        guarda; POST a ``deseleccionar_cliente``.
        Resultado esperado: ``assertRedirects`` a ``consultar_clientes``
        (sin seguir redirecciones) y ``session["selected_client"]`` ya
        NO está presente (``assertNotIn``).
        """
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
    """Pruebas de la asignación de usuarios Keycloak a un cliente.

    Verifica que asignar un usuario de Keycloak a un cliente crea la
    relación ``UsuarioCliente`` (con ``keycloak_user_id`` y ``rol_en_cliente``)
    y redirige de vuelta a ``asignaciones_cliente``; que un usuario sin rol
    ADMINISTRADOR no abre asignaciones (403) ni selecciona el cliente (404);
    que no se permite una asignación duplicada del mismo ``keycloak_user_id``
    (``IntegrityError``); que la relación admite varios clientes y varios
    usuarios por cliente, y que eliminar físicamente el cliente arrastra sus
    asignaciones por FK (``on_delete``).
    """

    def setUp(self):
        autenticar_admin(self)
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Empresa Asignable",
            tipo_persona="JURIDICA",
            documento="ASIGNAR-001",
        )

    @patch("clientes.views.admin_request")
    def test_asignar_usuario_keycloak_a_cliente(self, admin_request):
        """Verifica que se asigna un usuario de Keycloak a un cliente.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``
        ("Empresa Asignable", JURIDICA, "ASIGNAR-001"); ``admin_request``
        parcheado para devolver el usuario Keycloak ``kc-user-1``
        ("operador"/"Ana Operadora"); POST a ``asignaciones_cliente`` con
        ``{"usuario": "kc-user-1", "rol_en_cliente": "OPERADOR"}``.
        Resultado esperado: ``assertRedirects`` a ``asignaciones_cliente``
        (sin seguir la redirección) y que exista un ``UsuarioCliente`` con
        ``cliente=self.cliente``, ``keycloak_user_id="kc-user-1"`` y
        ``rol_en_cliente="OPERADOR"``.
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
        """Verifica que un usuario sin asignación no selecciona el cliente.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; se
        sustituye el contexto de sesión por ``kc_user`` ``kc-user-2``,
        ``SESSION_USUARIO`` correspondiente y roles ``["CAJERO"]``; POST a
        ``seleccionar_cliente`` con el id de ``self.cliente``.
        Resultado esperado: ``assertEqual(response.status_code, 404)`` —
        el cliente no queda seleccionado al no corresponder la asignación.
        """
        session = self.client.session
        session["kc_user"] = {"sub": "kc-user-2", "preferred_username": "otro"}
        session[SESSION_USUARIO] = {"sub": "kc-user-2", "username": "otro"}
        session[SESSION_ROLES] = ["CAJERO"]
        session.save()

        response = self.client.post(reverse("seleccionar_cliente", args=[self.cliente.id]))

        self.assertEqual(response.status_code, 404)

    def test_usuario_sin_rol_administrador_no_abre_asignaciones(self):
        """Verifica que sin rol ADMINISTRADOR no se abren asignaciones.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; se
        reemplazan los roles de la sesión por ``["CAJERO"]``; GET a
        ``asignaciones_cliente`` con el id de ``self.cliente``.
        Resultado esperado: ``assertEqual(response.status_code, 403)`` —
        el acceso a la vista de asignaciones está restringido.
        """
        session = self.client.session
        session["roles"] = ["CAJERO"]
        session.save()

        response = self.client.get(
            reverse("asignaciones_cliente", args=[self.cliente.id])
        )

        self.assertEqual(response.status_code, 403)

    def test_no_permite_asignacion_duplicada(self):
        """Verifica que no se permite asignar el mismo usuario dos veces.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; se crea
        un ``UsuarioCliente`` con ``keycloak_user_id="kc-user-unico"``; se
        intenta crear otro ``UsuarioCliente`` con el mismo
        ``keycloak_user_id`` (usuario duplicado) dentro de
        ``transaction.atomic()``.
        Resultado esperado: se lanza ``IntegrityError`` (capturado con
        ``assertRaises``) — la restricción de unicidad del usuario Keycloak
        impide la asignación duplicada.
        """
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
        """Verifica que un usuario puede asignarse a varios clientes.

        Escenario: ``setUp`` crea ``self.cliente``; se crea ``Segunda Empresa``
        (JURIDICA, "ASIGNAR-002"); se registran ``UsuarioCliente`` de
        ``kc-user-a`` para ambos clientes y de ``kc-user-b`` para
        ``self.cliente``.
        Resultado esperado: existen 2 asignaciones con
        ``keycloak_user_id="kc-user-a"`` (``assertEqual(... .count(), 2)``) y
        ``self.cliente.usuarios_asignados.count()`` es 2 (varios usuarios por
        cliente y varios clientes por usuario).
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

    def test_fk_elimina_asignaciones_si_se_elimina_fisicamente_cliente(self):
        """Verifica que eliminar el cliente elimina sus asignaciones (FK).

        Escenario: ``setUp`` crea ``self.cliente``; se crea una asignación
        ``UsuarioCliente`` (``kc-user-fk``/``usuario-fk``) para el cliente y se
        invoca ``self.cliente.delete()``.
        Resultado esperado: la asignación ya no existe en
        ``UsuarioCliente`` (``assertFalse(... exists())``) — el borrado en
        cascada por FK elimina la relación al eliminarse el cliente.
        """
        asignacion = UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="kc-user-fk",
            username="usuario-fk",
        )

        self.cliente.delete()

        self.assertFalse(UsuarioCliente.objects.filter(id=asignacion.id).exists())


class SeguridadYMetodosClientesTest(TestCase):
    """Pruebas de seguridad y de métodos HTTP de las vistas de clientes.

    Cubre que un usuario anónimo es redirigido al login en las siete rutas
    de clientes (inicio, registrar, consultar, editar, dar de baja,
    segmentar y asignaciones); que las vistas de formulario/acción rechazan
    con 405 el método PUT no soportado; y que las operaciones mutables
    (seleccionar, deseleccionar y quitar asignación) rechazan con 405 el
    método GET, conservando la asignación existente ``self.asignacion``.
    """

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
        """Verifica que un usuario anónimo es redirigido al login.

        Escenario: se crea un ``Client()`` sin autenticar (``anonimo``) y se
        recorren las URLs de clientes (inicio, registrar, consultar, editar,
        dar de baja, segmentar y asignaciones, estas últimas con
        ``self.cliente.id``/``self.cliente.id``).
        Resultado esperado: para cada URL, ``response.status_code == 302`` y
        ``response.url == reverse("usuarios:login")`` — el acceso requiere
        autenticación.
        """
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
        """Verifica que las vistas de formulario rechazan PUT (405).

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; se
        recorren las URLs de registrar, editar, dar de baja, segmentar y
        asignaciones (con ``self.cliente.id``).
        Resultado esperado: ``self.client.put(url).status_code == 405`` para
        cada una — el método PUT no está soportado en estas rutas
        (``assertEqual`` en cada ``subTest``).
        """
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
        """Verifica que las operaciones mutables rechazan GET (405).

        Escenario: ``setUp`` autentica admin, crea ``self.cliente`` y
        ``self.asignacion``; se recorren las URLs ``seleccionar_cliente``,
        ``deseleccionar_cliente`` y ``quitar_asignacion_cliente``.
        Resultado esperado: ``self.client.get(url).status_code == 405`` por
        cada URL (``subTest``) — solo admiten POST; además, tras el GET,
        ``self.asignacion`` sigue existiendo en ``UsuarioCliente``
        (``assertTrue(... .exists())``) — ninguna operación destructiva se
        ejecutó vía GET.
        """
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
        """Verifica crear un cliente vía el endpoint JSON de frontend.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; POST a
        ``clientes_api:crear_cliente`` con ``nombre_razon_social``
        "Cliente Nuevo API", ``tipo_persona`` "JURIDICA" y ``documento``
        "API-002" (JSON como ``content_type``).
        Resultado esperado: ``201``, existe ``Cliente`` con documento
        "API-002" (``assertTrue ... exists()``) y ``response.json()["cliente"]
        ["estado"] == "ACTIVO"``.
        """
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
        """Verifica que no se puede crear un cliente con documento duplicado.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``
        (FISICA, documento "API-001"); POST a ``clientes_api:crear_cliente``
        con ``nombre_razon_social="Duplicado"``, ``tipo_persona="FISICA"``
        y el mismo ``documento="API-001"`` (contenido JSON).
        Resultado esperado: ``assertEqual(response.status_code, 409)`` — el
        documento duplicado se rechaza.
        """
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
        """Verifica el rechazo de datos inválidos al crear un cliente.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; POST
        a ``clientes_api:crear_cliente`` con datos JSON sin los campos
        válidos requeridos.
        Resultado esperado: ``assertEqual(response.status_code, 400)`` — se
        valida la integridad de los datos antes de persistir.
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

    def test_crear_cliente_con_cuerpo_invalido(self):
        """Verifica el rechazo de un cuerpo JSON no parseable.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; POST
        a ``clientes_api:crear_cliente`` con ``content_type="application/json"``
        y un cuerpo que no es JSON válido.
        Resultado esperado: ``assertEqual(response.status_code, 400)`` — el
        cuerpo inválido no se procesa como cliente.
        """
        response = self.client.post(
            reverse("clientes_api:crear_cliente"),
            data="no es json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_crear_cliente_requiere_administrador(self):
        """Verifica que solo un administrador puede crear clientes (API).

        Escenario: ``setUp`` autentica admin; ``autenticar_con_roles``
        reemplaza la sesión por roles ``["USUARIO"]`` (no administrador);
        POST a ``clientes_api:crear_cliente``.
        Resultado esperado: ``assertEqual(response.status_code, 403)`` y
        ``assertFalse(Cliente.objects.filter(documento="API-003").exists())``
        — no se persiste el cliente sin rol administrador.
        """
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
        """Verifica editar un cliente vía la API JSON.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``
        ("Cliente API"); POST a ``clientes_api:editar_cliente`` con
        ``[self.cliente.id]`` y ``data`` JSON ("Cliente Editado API",
        JURIDICA, "API-003").
        Resultado esperado:``assertEqual(response.status_code, 200)`` y, tras
        ``refresh_from_db``, ``assertEqual`` de ``nombre_razon_social``
        "Cliente Editado API", ``tipo_persona`` "JURIDICA" y ``documento``
        "API-003".
        """
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
        """Verifica que editar un cliente inexistente devuelve 404.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; POST
        a ``clientes_api:editar_cliente`` con args ``[999999]`` (id que no
        existe) y datos JSON.
        Resultado esperado: ``assertEqual(response.status_code, 404)``.
        """
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
        """Verifica dar de baja un cliente vía la API JSON (baja lógica).

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``
        ("Cliente API", FISICA, "API-001"); POST a
        ``clientes_api:dar_de_baja_cliente`` con ``[self.cliente.id]`` y
        ``data={}`` JSON.
        Resultado esperado: ``assertEqual(response.status_code, 200)``,
        ``refresh_from_db`` deja ``self.cliente.estado == "INACTIVO"`` y
        ``assertTrue(Cliente.objects.filter(id=self.cliente.id).exists())``
        — la baja es lógica: el registro persiste con estado INACTIVO.
        """
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
        """Verifica que dar de baja un cliente inexistente devuelve 404.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; POST
        a ``clientes_api:dar_de_baja_cliente`` con ``args=[999999]`` (id
        inexistente) y ``data={}`` JSON.
        Resultado esperado: ``assertEqual(response.status_code, 404)``.
        """
        response = self.client.post(
            reverse("clientes_api:dar_de_baja_cliente", args=[999999]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_dar_de_baja_cliente_deselecciona_si_era_el_activo(self):
        """Verifica que dar de baja deselecciona el cliente activo de la sesión.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; se
        precarga ``session["selected_client"]`` con su id/name y se guarda
        la sesión; POST a ``dar_de_baja_cliente`` con ``[self.cliente.id]``
        y ``data={}`` JSON.
        Resultado esperado: ``assertEqual(response.status_code, 200)`` y
        ``assertNotIn("selected_client", self.client.session)`` — al haber
        sido el cliente activo, la baja lo deselecciona.
        """
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
        """Verifica seleccionar un cliente activo vía la API JSON.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``
        ("Cliente API"); POST a ``clientes_api:seleccionar_cliente`` con
        ``[self.cliente.id]`` y ``data={}`` JSON.
        Resultado esperado: ``assertEqual(response.status_code, 200)`` y
        ``assertEqual`` de ``session["selected_client"]`` con
        ``{"id": self.cliente.id, "name": "Cliente API"}``.
        """
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
        """Verifica que un cliente inactivo no puede seleccionarse (404).

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``;
        ``self.cliente.dar_de_baja()`` lo inactiva; POST a
        ``clientes_api:seleccionar_cliente`` con ``[self.cliente.id]`` y
        ``data={}`` JSON.
        Resultado esperado: ``assertEqual(response.status_code, 404)`` y
        ``assertNotIn("selected_client", self.client.session)``.
        """
        self.cliente.dar_de_baja()

        response = self.client.post(
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("selected_client", self.client.session)

    def test_no_administrador_selecciona_solo_cliente_asignado(self):
        """Verifica que un no-administrador selecciona solo su cliente asignado.

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; se crea
        ``UsuarioCliente`` (``kc-api-1``/"api-cajero") para ``self.cliente``
        y se autentica con rol ``["CAJERO"]`` (``sub="kc-api-1"``); además se
        crea ``cliente_no_asignado`` ("Cliente Ajeno API", JURIDICA,
        "API-006").
        Resultado esperado: POST a ``seleccionar_cliente`` de
        ``self.cliente.id`` → ``assertEqual(status_code, 200)`` y
        `session["selected_client"]["id"] == self.cliente.id``; POST del
        ``cliente_no_asignado.id`` → ``assertEqual(response, 404)`` sin
        cambiar el cliente activo de la sesión.
        """
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
        """Verifica que las mutaciones de la API rechazan GET (405).

        Escenario: ``setUp`` autentica admin y crea ``self.cliente``; se
        recorren las URLs diseñadas para mutaciones: ``crear_cliente``,
        ``editar_cliente``, ``dar_de_baja_cliente`` y ``seleccionar_cliente``
        (con ``self.cliente.id``).
        Resultado esperado: para cada URL (``subTest``),
        ``assertEqual(self.client.get(url).status_code, 405)`` — el GET no
        está soportado en endpoints de mutación.
        """
        urls = [
            reverse("clientes_api:crear_cliente"),
            reverse("clientes_api:editar_cliente", args=[self.cliente.id]),
            reverse("clientes_api:dar_de_baja_cliente", args=[self.cliente.id]),
            reverse("clientes_api:seleccionar_cliente", args=[self.cliente.id]),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
