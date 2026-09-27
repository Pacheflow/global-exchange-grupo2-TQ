import json
import time

from django.core.exceptions import FieldDoesNotExist
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
        MetodoPago.objects.create(nombre="Efectivo")
        form = MetodoPagoForm(data={"nombre": " efectivo ", "activo": True})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors.as_data()["nombre"][0].code, "duplicate")
        with self.assertRaises(IntegrityError), transaction.atomic():
            MetodoPago.objects.create(nombre="EFECTIVO")

    def test_administrador_crea_metodo_global_sin_cliente_ni_tipo_cerrado(self):
        self.assertEqual(Cliente.objects.count(), 0)
        self.autenticar()
        response = self.client.post(
            "/api/metodos-pago/registrar/",
            data=json.dumps(
                {
                    "nombre": "Billetera electrónica",
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
        self.autenticar()
        metodo = MetodoPago.objects.create(nombre="QR")
        response = self.client.post(
            f"/api/metodos-pago/editar/{metodo.id}/",
            data=json.dumps(
                {
                    "nombre": "Pago QR",
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
        self.assertEqual(metodo.descripcion, "Pago mediante código QR.")
        self.assertFalse(metodo.activo)

    def test_administrador_activa_y_desactiva_sin_eliminar(self):
        self.autenticar()
        metodo = MetodoPago.objects.create(nombre="Efectivo")
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
        self.autenticar()
        MetodoPago.objects.create(
            nombre="Transferencia bancaria",
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
