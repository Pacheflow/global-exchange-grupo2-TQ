import time
from unittest.mock import patch

from django.http import HttpResponse
from django.test import TestCase

from clientes.models import Cliente
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .forms import MetodoPagoForm
from .models import MetodoPago


class MetodoPagoBackendTests(TestCase):
    """
    Pruebas de Backend para HU-37 - Configurar Métodos de Pago.

    Las pruebas verifican autenticación, autorización, validaciones,
    persistencia, edición, cambio de estado y manejo de errores.
    """

    def autenticar(self, roles=None):
        """
        Crea una sesión OIDC válida para las pruebas.

        Por defecto se utiliza el rol ADMINISTRADOR, que es el rol
        autorizado para configurar métodos de pago.
        """
        roles = roles or ["ADMINISTRADOR"]

        session = self.client.session

        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-prueba-001",
            "preferred_username": "admin.prueba",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 3600

        session.save()

    def crear_cliente(self, nombre="Cliente de prueba"):
        """
        Crea un cliente utilizado como contexto para las pruebas.
        """
        return Cliente.objects.create(
            nombre_razon_social=nombre,
            tipo_persona="FISICA",
            documento=f"TEST-{Cliente.objects.count() + 1}",
        )

    def datos_metodo(self, cliente=None, **extra):
        """
        Construye datos válidos para registrar un método de pago.
        """
        cliente = cliente or self.crear_cliente()

        datos = {
            "cliente": cliente.pk,
            "nombre": "Efectivo",
            "tipo": "EFECTIVO",
            "estado": "ACTIVO",
        }

        datos.update(extra)

        return datos

    # ==============================================================
    # AUTENTICACIÓN Y AUTORIZACIÓN
    # ==============================================================

    def test_usuario_no_autenticado_es_redirigido_al_login(self):
        """
        Verifica que un usuario sin sesión OIDC es redirigido al inicio
        de sesión antes de acceder al módulo.
        """
        response = self.client.get("/metodos-pago/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_usuario_sin_rol_administrador_recibe_403(self):
        """
        Verifica que un usuario autenticado sin ADMINISTRADOR no puede
        configurar métodos de pago.
        """
        self.autenticar(["USUARIO"])

        response = self.client.get("/metodos-pago/")

        self.assertEqual(response.status_code, 403)

    # ==============================================================
    # REGISTRO
    # ==============================================================

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_registrar_metodo_pago(self, _mock_sesion):
        """
        Verifica que un administrador puede registrar un método de pago
        y que la información queda persistida.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        response = self.client.post(
            "/metodos-pago/registrar/",
            data=self.datos_metodo(cliente),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MetodoPago.objects.count(), 1)

        metodo = MetodoPago.objects.get()

        self.assertEqual(metodo.cliente, cliente)
        self.assertEqual(metodo.nombre, "Efectivo")
        self.assertEqual(metodo.tipo, "EFECTIVO")
        self.assertEqual(metodo.estado, "ACTIVO")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_nombre_se_normaliza(self, _mock_sesion):
        """
        Verifica que los espacios innecesarios del nombre son eliminados
        antes de persistir el método.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        response = self.client.post(
            "/metodos-pago/registrar/",
            data=self.datos_metodo(
                cliente,
                nombre="   Efectivo   ",
            ),
        )

        self.assertEqual(response.status_code, 302)

        metodo = MetodoPago.objects.get()

        self.assertEqual(metodo.nombre, "Efectivo")

    def test_formulario_rechaza_nombre_vacio(self):
        """
        Verifica que el Backend rechaza un método de pago sin nombre.
        """
        cliente = self.crear_cliente()

        form = MetodoPagoForm(
            data=self.datos_metodo(
                cliente,
                nombre="   ",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("nombre", form.errors)

    def test_formulario_rechaza_metodo_duplicado_para_mismo_cliente(self):
        """
        Verifica que un cliente no puede registrar dos métodos de pago
        con el mismo nombre.
        """
        cliente = self.crear_cliente()

        MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        form = MetodoPagoForm(
            data=self.datos_metodo(
                cliente,
                nombre="Efectivo",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_mismo_nombre_se_permite_para_clientes_diferentes(self):
        """
        Verifica que dos clientes diferentes pueden utilizar el mismo
        nombre de método de pago.
        """
        cliente_1 = self.crear_cliente("Cliente uno")
        cliente_2 = self.crear_cliente("Cliente dos")

        MetodoPago.objects.create(
            cliente=cliente_1,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        form = MetodoPagoForm(
            data=self.datos_metodo(
                cliente_2,
                nombre="Efectivo",
            )
        )

        self.assertTrue(form.is_valid())

    # ==============================================================
    # CONSULTA
    # ==============================================================

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_consultar_metodos(self, _mock_sesion):
        """
        Verifica que un administrador puede consultar los métodos
        de pago registrados.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        metodo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        with patch("metodos_pago.views.render") as mock_render:
            mock_render.return_value = HttpResponse("OK")

            response = self.client.get("/metodos-pago/consultar/")

        self.assertEqual(response.status_code, 200)
        mock_render.assert_called_once()

        contexto = mock_render.call_args.args[2]

        self.assertIn("metodos", contexto)
        self.assertIn(metodo, contexto["metodos"])

    # ==============================================================
    # EDICIÓN
    # ==============================================================

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_editar_metodo(self, _mock_sesion):
        """
        Verifica que un administrador puede modificar un método
        de pago existente.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        metodo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        response = self.client.post(
            f"/metodos-pago/editar/{metodo.id}/",
            data=self.datos_metodo(
                cliente,
                nombre="Tarjeta",
                tipo="TARJETA",
            ),
        )

        self.assertEqual(response.status_code, 302)

        metodo.refresh_from_db()

        self.assertEqual(metodo.nombre, "Tarjeta")
        self.assertEqual(metodo.tipo, "TARJETA")

    # ==============================================================
    # ACTIVAR / DESACTIVAR
    # ==============================================================

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_desactivar_metodo(self, _mock_sesion):
        """
        Verifica que un administrador puede desactivar un método
        de pago existente.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        metodo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        response = self.client.post(
            f"/metodos-pago/estado/{metodo.id}/",
        )

        self.assertEqual(response.status_code, 302)

        metodo.refresh_from_db()

        self.assertEqual(metodo.estado, "INACTIVO")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_reactivar_metodo(self, _mock_sesion):
        """
        Verifica que un administrador puede reactivar un método
        de pago previamente desactivado.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        metodo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="INACTIVO",
        )

        response = self.client.post(
            f"/metodos-pago/estado/{metodo.id}/",
        )

        self.assertEqual(response.status_code, 302)

        metodo.refresh_from_db()

        self.assertEqual(metodo.estado, "ACTIVO")

    # ==============================================================
    # DISPONIBILIDAD PARA NUEVAS OPERACIONES
    # ==============================================================

    def test_metodos_activos_excluye_los_inactivos(self):
        """
        Verifica que la consulta destinada a nuevas operaciones
        solo devuelve métodos de pago activos.
        """
        cliente = self.crear_cliente()

        activo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        inactivo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Tarjeta",
            tipo="TARJETA",
            estado="INACTIVO",
        )

        disponibles = MetodoPago.objects.activos()

        self.assertIn(activo, disponibles)
        self.assertNotIn(inactivo, disponibles)

    # ==============================================================
    # CONSERVACIÓN DE INFORMACIÓN HISTÓRICA
    # ==============================================================

    def test_desactivar_no_elimina_informacion_historica(self):
        """
        Verifica que desactivar un método conserva su registro
        y su información histórica.
        """
        cliente = self.crear_cliente()

        metodo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        metodo_id = metodo.id

        metodo.desactivar()

        metodo.refresh_from_db()

        self.assertTrue(MetodoPago.objects.filter(id=metodo_id).exists())
        self.assertEqual(metodo.nombre, "Efectivo")
        self.assertEqual(metodo.tipo, "EFECTIVO")
        self.assertEqual(metodo.estado, "INACTIVO")

    # ==============================================================
    # MANEJO DE ERRORES
    # ==============================================================

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    @patch("metodos_pago.views.MetodoPagoForm.save")
    def test_error_al_guardar_informa_la_situacion(
        self,
        mock_save,
        _mock_sesion,
    ):
        """
        Verifica que un error inesperado durante el registro
        se informa mediante el formulario.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        mock_save.side_effect = Exception("Error de persistencia")

        with patch("metodos_pago.views.render") as mock_render:
            mock_render.return_value = HttpResponse("OK")

            response = self.client.post(
                "/metodos-pago/registrar/",
                data=self.datos_metodo(cliente),
            )

        self.assertEqual(response.status_code, 200)
        mock_render.assert_called_once()

        contexto = mock_render.call_args.args[2]
        form = contexto["form"]

        self.assertTrue(form.non_field_errors())
        self.assertIn(
            "No fue posible guardar el método de pago.",
            form.non_field_errors()[0],
        )

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    @patch("metodos_pago.views.MetodoPagoForm.save")
    def test_error_al_actualizar_informa_la_situacion(
        self,
        mock_save,
        _mock_sesion,
    ):
        """
        Verifica que un error inesperado durante la edición
        se informa mediante el formulario.
        """
        self.autenticar()
        cliente = self.crear_cliente()

        metodo = MetodoPago.objects.create(
            cliente=cliente,
            nombre="Efectivo",
            tipo="EFECTIVO",
            estado="ACTIVO",
        )

        mock_save.side_effect = Exception("Error de persistencia")

        with patch("metodos_pago.views.render") as mock_render:
            mock_render.return_value = HttpResponse("OK")

            response = self.client.post(
                f"/metodos-pago/editar/{metodo.id}/",
                data=self.datos_metodo(
                    cliente,
                    nombre="Tarjeta",
                    tipo="TARJETA",
                ),
            )

        self.assertEqual(response.status_code, 200)
        mock_render.assert_called_once()

        contexto = mock_render.call_args.args[2]
        form = contexto["form"]

        self.assertTrue(form.non_field_errors())
        self.assertIn(
            "No fue posible actualizar el método de pago.",
            form.non_field_errors()[0],
        )
