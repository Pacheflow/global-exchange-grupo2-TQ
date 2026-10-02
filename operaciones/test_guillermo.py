"""Pruebas esenciales de HU-23 Venta y HU-32/HU-24 Historial y detalle."""

import time

from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente, UsuarioCliente
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .tests import BaseOperacionesTests


class FlujosGuillermoTests(BaseOperacionesTests):
    """Protege Venta, métodos y consultas aisladas por cliente."""

    def autenticar(self, *, cliente=None, roles=("USUARIO",)):
        """Configura una sesión OIDC válida con un cliente seleccionado."""

        cliente = cliente or self.cliente
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session[SESSION_ROLES] = list(roles)
        session[SESSION_USUARIO] = {
            "sub": self.usuario_id,
            "username": self.usuario_username,
        }
        session["selected_client"] = {
            "id": cliente.id,
            "name": cliente.nombre_razon_social,
        }
        session.save()

    def crear_cliente_asociado(self):
        """Crea un segundo cliente autorizado para probar el aislamiento."""

        cliente = Cliente.objects.create(
            nombre_razon_social="Segundo cliente",
            tipo_persona="FISICA",
            documento="987654",
            estado="ACTIVO",
            categoria=self.categoria,
        )
        UsuarioCliente.objects.create(
            cliente=cliente,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )
        return cliente

    def test_venta_previsualiza_y_confirma_con_tasa_de_venta(self):
        """Comprueba el flujo HU-23 con la tasa de venta y estado PENDIENTE."""

        preview = self.previsualizar(tipo="VENTA")
        resultado = self.crear(tipo="VENTA")

        self.assertEqual(preview.tasa, self.tasa.venta)
        self.assertEqual(resultado.transaccion.tasa_aplicada, self.tasa.venta)
        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")

    def test_metodos_expone_solo_activos_y_preselecciona_preferido(self):
        """Comprueba que HU-23 ofrezca solo métodos activos y el preferido."""

        self.cliente.metodo_pago_preferido = self.metodo_activo
        self.cliente.save(update_fields=["metodo_pago_preferido"])
        self.autenticar()

        response = self.client.get(reverse("operaciones:metodos_pago_operacion"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["metodo_pago_preferido"]["id"],
            self.metodo_activo.id,
        )
        self.assertEqual(
            [item["id"] for item in payload["metodos_pago"]],
            [self.metodo_activo.id],
        )

    def test_metodo_preferido_inactivo_no_se_preselecciona(self):
        """Comprueba que un método preferido inactivo no quede disponible."""

        self.cliente.metodo_pago_preferido = self.metodo_inactivo
        self.cliente.save(update_fields=["metodo_pago_preferido"])
        self.autenticar()

        response = self.client.get(reverse("operaciones:metodos_pago_operacion"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["metodo_pago_preferido"])

    def test_historial_muestra_solo_el_cliente_seleccionado(self):
        """Comprueba que HU-32 no mezcle dos clientes autorizados del usuario."""

        propia = self.crear(tipo="VENTA").transaccion
        segundo = self.crear_cliente_asociado()
        ajena_al_contexto = self.crear(
            cliente_id=segundo.id,
            clave_idempotencia=self.clave_idempotencia(),
            tipo="VENTA",
        ).transaccion
        self.autenticar(cliente=self.cliente)

        response = self.client.get(reverse("operaciones:historial_transacciones"))

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["transacciones"]]
        self.assertIn(propia.id, ids)
        self.assertNotIn(ajena_al_contexto.id, ids)

    def test_detalle_de_otro_cliente_no_es_accesible(self):
        """Comprueba que HU-24 oculte transacciones ajenas al contexto actual."""

        segundo = self.crear_cliente_asociado()
        otra = self.crear(
            cliente_id=segundo.id,
            clave_idempotencia=self.clave_idempotencia(),
            tipo="VENTA",
        ).transaccion
        self.autenticar(cliente=self.cliente)

        response = self.client.get(
            reverse("operaciones:detalle_transaccion", args=[otra.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_detalle_incluye_snapshots_y_cancelacion_sin_recalcular(self):
        """Comprueba que el detalle use snapshots y exponga su auditoría."""

        transaccion = self.crear(tipo="VENTA").transaccion
        tasa_guardada = str(transaccion.tasa_aplicada)
        self.actualizar_cotizacion(venta="8100.000000")
        self.autenticar()

        response = self.client.get(
            reverse("operaciones:detalle_transaccion", args=[transaccion.id])
        )

        self.assertEqual(response.status_code, 200)
        detalle = response.json()["transaccion"]
        self.assertEqual(detalle["tasa_aplicada"], tasa_guardada)
        self.assertEqual(detalle["tasa_comercial"]["version"], 1)
        self.assertEqual(detalle["metodo_pago"]["nombre"], "Efectivo")
        self.assertIn("cancelacion", detalle)

    def test_historial_y_detalle_rechazan_escrituras(self):
        """Comprueba que HU-32/HU-24 permanezcan estrictamente de lectura."""

        transaccion = self.crear(tipo="VENTA").transaccion
        self.autenticar()

        historial = self.client.post(reverse("operaciones:historial_transacciones"))
        detalle = self.client.post(
            reverse("operaciones:detalle_transaccion", args=[transaccion.id])
        )

        self.assertEqual(historial.status_code, 405)
        self.assertEqual(detalle.status_code, 405)


class RutasGuillermoTests(TestCase):
    """Comprueba los contratos HTTP agregados para Guillermo."""

    def test_rutas_de_metodos_y_detalle(self):
        """Comprueba los nombres y rutas públicas dentro del API."""

        self.assertEqual(
            reverse("operaciones:metodos_pago_operacion"),
            "/api/operaciones/metodos-pago/",
        )
        self.assertEqual(
            reverse("operaciones:detalle_transaccion", args=[7]),
            "/api/operaciones/7/detalle/",
        )
