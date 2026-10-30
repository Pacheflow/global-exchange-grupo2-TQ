import json
import time

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
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


class MetodoPagoCatalogoEsencialTests(TestCase):
    """Pruebas del catálogo global de métodos de pago administrado por el rol ADMINISTRADOR.

    Requisito relacionado: HU-37 / RF-26.
    """

    def autenticar(self, roles=None):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-prueba-001",
            "preferred_username": "admin.prueba",
        }
        session[SESSION_ROLES] = roles or ["ADMINISTRADOR"]
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session.save()

    def test_nombre_es_unico_globalmente_sin_distinguir_mayusculas(self):
        """Comprueba que el nombre de un método de pago sea único en el catálogo global.

        Se espera que el formulario rechace el duplicado sin distinguir mayúsculas y
        que la base de datos lo rechace con IntegrityError.
        """
        MetodoPago.objects.create(nombre="Efectivo", naturaleza="EFECTIVO")
        form = MetodoPagoForm(data={"nombre": " efectivo ", "activo": True})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["nombre"][0].code, "duplicate")
        with self.assertRaises(IntegrityError), transaction.atomic():
            MetodoPago.objects.create(nombre="EFECTIVO", naturaleza="EFECTIVO")

    def test_administrador_crea_metodo_global_con_tipo_electronico(self):
        """Comprueba que un administrador pueda registrar un método de pago del catálogo global.

        Se espera que el método se cree con tipo electrónico y sin estar vinculado a un cliente.
        """
        self.assertEqual(Cliente.objects.count(), 0)
        self.autenticar()
        response = self.client.post(
            "/api/metodos-pago/registrar/",
            data=json.dumps(
                {
                    "nombre": "Billetera electrónica",
                    "naturaleza": "ELECTRONICO",
                    "descripcion": "Pago mediante una billetera habilitada.",
                    "activo": True,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 201)
        metodo = MetodoPago.objects.get()
        self.assertEqual(metodo.nombre, "Billetera electrónica")
        with self.assertRaises(FieldDoesNotExist):
            MetodoPago._meta.get_field("cliente")
        with self.assertRaises(FieldDoesNotExist):
            MetodoPago._meta.get_field("tipo")

    def test_administrador_edita_metodo(self):
        """Comprueba que un administrador pueda editar un método de pago.

        Se espera que los cambios se persistan correctamente.
        """
        self.autenticar()
        metodo = MetodoPago.objects.create(nombre="QR", naturaleza="ELECTRONICO")
        response = self.client.post(
            f"/api/metodos-pago/editar/{metodo.id}/",
            data=json.dumps(
                {
                    "nombre": "Pago QR",
                    "naturaleza": "EFECTIVO",
                    "descripcion": "Pago mediante código QR.",
                    "activo": False,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        metodo.refresh_from_db()
        self.assertEqual(metodo.nombre, "Pago QR")
        self.assertEqual(metodo.naturaleza, "EFECTIVO")
        self.assertEqual(response.json()["metodo"]["naturaleza_display"], "Efectivo")
        self.assertEqual(metodo.descripcion, "Pago mediante código QR.")
        self.assertFalse(metodo.activo)

    def test_administrador_activa_y_desactiva_sin_eliminar(self):
        """Comprueba que un administrador pueda activar y desactivar un método de pago.

        Se espera que el método deje de aparecer entre los activos al desactivarse y
        vuelva a aparecer al reactivarse, conservando siempre su registro.
        """
        self.autenticar()
        metodo = MetodoPago.objects.create(nombre="Efectivo", naturaleza="EFECTIVO")
        url = f"/api/metodos-pago/estado/{metodo.id}/"
        desactivar = self.client.post(url, HTTP_ACCEPT="application/json")
        metodo.refresh_from_db()
        self.assertEqual(desactivar.status_code, 200)
        self.assertFalse(metodo.activo)
        self.assertFalse(MetodoPago.objects.activos().filter(pk=metodo.pk).exists())
        self.assertTrue(MetodoPago.objects.filter(pk=metodo.pk).exists())

        reactivar = self.client.post(url, HTTP_ACCEPT="application/json")
        metodo.refresh_from_db()
        self.assertEqual(reactivar.status_code, 200)
        self.assertTrue(metodo.activo)
        self.assertTrue(MetodoPago.objects.activos().filter(pk=metodo.pk).exists())

    def test_usuario_no_administrador_no_puede_modificar_catalogo(self):
        """Comprueba que únicamente los administradores puedan modificar el catálogo.

        Se espera que un usuario sin ese rol reciba acceso denegado (403).

        Requisito relacionado: RNF-02.
        """
        self.autenticar(["USUARIO"])
        response = self.client.post(
            "/api/metodos-pago/registrar/",
            data=json.dumps({"nombre": "Efectivo", "activo": True}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MetodoPago.objects.exists())

    def test_api_devuelve_catalogo_global_sin_propietario_cliente(self):
        """Comprueba que la API devuelva métodos de pago globales, sin depender de un cliente.

        Se espera que ninguna opción del catálogo incluya información de cliente o tipo.
        """
        self.autenticar()
        MetodoPago.objects.create(
            nombre="Transferencia bancaria",
            naturaleza="ELECTRONICO",
            descripcion="Transferencia desde una cuenta bancaria.",
        )
        response = self.client.get(
            "/api/metodos-pago/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("clientes", response.json())
        metodo = response.json()["metodos"][0]
        self.assertNotIn("cliente", metodo)
        self.assertNotIn("tipo", metodo)
        self.assertEqual(metodo["nombre"], "Transferencia bancaria")
        self.assertTrue(metodo["activo"])
        self.assertEqual(metodo["naturaleza"], "ELECTRONICO")
        self.assertEqual(metodo["naturaleza_display"], "Electrónico")


class MetodoPagoTipoTests(TestCase):
    """Tipo obligatorio en CRUD, sin reclasificar métodos heredados."""

    autenticar = MetodoPagoCatalogoEsencialTests.autenticar

    def test_administrador_crea_tipo_efectivo(self):
        self.autenticar()
        response = self.client.post(
            "/api/metodos-pago/registrar/",
            data=json.dumps({"nombre": "Medio físico", "naturaleza": "EFECTIVO", "activo": True}),
            content_type="application/json", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["metodo"]["naturaleza"], "EFECTIVO")
        self.assertEqual(response.json()["metodo"]["naturaleza_display"], "Efectivo")
        self.assertEqual(MetodoPago.objects.get().naturaleza, "EFECTIVO")

    def test_api_rechaza_tipo_ausente_sin_clasificar_o_invalido(self):
        self.autenticar()
        for naturaleza in (None, "", "SIN_CLASIFICAR", "OTRO"):
            with self.subTest(naturaleza=naturaleza):
                datos = {"nombre": "Sin tipo", "activo": True}
                if naturaleza is not None:
                    datos["naturaleza"] = naturaleza
                response = self.client.post(
                    "/api/metodos-pago/registrar/", data=json.dumps(datos),
                    content_type="application/json", HTTP_ACCEPT="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("naturaleza", response.json()["detalles"])
        self.assertFalse(MetodoPago.objects.exists())

    def test_modelo_rechaza_nuevo_activo_sin_clasificacion(self):
        for datos in ({}, {"naturaleza": "SIN_CLASIFICAR"}):
            with self.subTest(datos=datos), self.assertRaises(ValidationError):
                MetodoPago.objects.create(nombre="Método sin tipo", **datos)
        self.assertFalse(MetodoPago.objects.exists())

    def test_form_solo_ofrece_dos_tipos_y_exige_seleccion(self):
        form = MetodoPagoForm()
        self.assertEqual(form.fields["naturaleza"].label, "Tipo")
        self.assertEqual(list(form.fields["naturaleza"].choices), [
            ("", "Seleccioná un tipo"), ("ELECTRONICO", "Electrónico"), ("EFECTIVO", "Efectivo"),
        ])
        self.assertTrue(form.fields["naturaleza"].required)

    def test_legacy_sigue_visible_y_no_se_reclasifica_al_listar(self):
        self.autenticar()
        legado = MetodoPago.objects.create(nombre="Legado", activo=False)
        # Reproduce un registro activo anterior a esta regla, sin deshabilitar la validación de save.
        MetodoPago.objects.filter(pk=legado.pk).update(activo=True)
        response = self.client.get("/api/metodos-pago/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metodos"][0]["naturaleza_display"], "Sin clasificar")
        legado.refresh_from_db()
        self.assertEqual(legado.naturaleza, "SIN_CLASIFICAR")
        self.assertTrue(legado.activo)
        legado.descripcion = "Se conserva la información histórica"
        legado.save(update_fields=["descripcion"])
        legado.refresh_from_db()
        self.assertEqual(legado.naturaleza, "SIN_CLASIFICAR")

    def test_editar_legacy_pide_tipo_explicito_y_permite_clasificar(self):
        self.autenticar()
        legado = MetodoPago.objects.create(nombre="Legado", activo=False)
        url = f"/api/metodos-pago/editar/{legado.pk}/"
        datos = {"nombre": "Legado", "activo": False}
        response = self.client.post(url, data=json.dumps(datos), content_type="application/json", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        legado.refresh_from_db()
        self.assertEqual(legado.naturaleza, "SIN_CLASIFICAR")
        datos["naturaleza"] = "ELECTRONICO"
        response = self.client.post(url, data=json.dumps(datos), content_type="application/json", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        legado.refresh_from_db()
        self.assertEqual(legado.naturaleza, "ELECTRONICO")
        self.assertFalse(legado.activo)

    def test_activar_legacy_exige_clasificacion_en_modelo_y_api(self):
        self.autenticar()
        legado = MetodoPago.objects.create(nombre="Legado", activo=False)
        with self.assertRaises(ValidationError):
            legado.activar()
        legado.refresh_from_db()
        self.assertFalse(legado.activo)
        response = self.client.post(f"/api/metodos-pago/estado/{legado.pk}/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Seleccioná Electrónico o Efectivo", response.json()["error"])
        legado.refresh_from_db()
        self.assertFalse(legado.activo)
        legado.naturaleza = "EFECTIVO"
        legado.save(update_fields=["naturaleza"])
        response = self.client.post(f"/api/metodos-pago/estado/{legado.pk}/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        legado.refresh_from_db()
        self.assertTrue(legado.activo)

    def test_actualizacion_parcial_no_activa_un_tipo_no_persistido(self):
        legado = MetodoPago.objects.create(nombre="Legado", activo=False)
        legado.naturaleza = "EFECTIVO"
        with self.assertRaises(ValidationError):
            legado.activar()
        legado.refresh_from_db()
        self.assertFalse(legado.activo)
        self.assertEqual(legado.naturaleza, "SIN_CLASIFICAR")

    def test_no_se_puede_quitar_clasificacion_de_un_activo(self):
        metodo = MetodoPago.objects.create(nombre="Clasificado", naturaleza="EFECTIVO")
        metodo.naturaleza = "SIN_CLASIFICAR"
        with self.assertRaises(ValidationError):
            metodo.save(update_fields=["naturaleza"])
        metodo.refresh_from_db()
        self.assertEqual(metodo.naturaleza, "EFECTIVO")
