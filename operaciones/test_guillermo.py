"""Pruebas esenciales de HU-23 Venta y HU-32/HU-24 Historial y detalle."""

import json
import time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente, UsuarioCliente
from pagos.models import Pago
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

    def test_bandeja_y_detalle_cajero_sin_asociaciones_ni_cliente(self):
        """Cajero consulta detalles ajenos sin asociaciones; su bandeja excluye las operaciones online."""
        otro = self.crear_cliente_asociado()
        primero = self.crear().transaccion
        segundo = self.crear(cliente_id=otro.pk).transaccion
        UsuarioCliente.objects.all().delete()
        self.autenticar(roles=("CAJERO", "USUARIO"))
        sesion = self.client.session
        sesion.pop("selected_client", None)
        sesion.save()
        url = reverse("operaciones:historial_transacciones")
        datos = self.client.get(url).json()["transacciones"]
        self.assertEqual(datos, [])
        self.assertTrue(all("pago_estado" in tx for tx in datos))
        self.assertEqual(self.client.get(reverse("operaciones:detalle_transaccion", args=[segundo.pk])).status_code, 200)
        pagina = self.client.get(reverse("operaciones_web:inicio"))
        self.assertContains(pagina, "Bandeja operativa")
        self.assertNotContains(pagina, 'data-operation-form')
        self.assertContains(pagina, reverse("operaciones_web:presencial"))
        self.assertNotContains(pagina, "Seleccioná un cliente para operar")
        datos = self.client.get(url).json()["transacciones"]
        self.assertEqual(datos, [])
        detalle = self.client.get(reverse("operaciones:detalle_transaccion", args=[segundo.pk]))
        self.assertEqual(detalle.status_code, 200)
        inexistente = self.client.get(reverse("operaciones:detalle_transaccion", args=[999999]))
        self.assertEqual(inexistente.status_code, 404)

    def test_usuario_sigue_requiriendo_cliente_para_historial_y_detalle(self):
        tx = self.crear().transaccion
        self.autenticar()
        sesion = self.client.session
        sesion.pop("selected_client", None)
        sesion.save()
        self.assertEqual(self.client.get(reverse("operaciones:historial_transacciones")).status_code, 400)
        self.assertEqual(self.client.get(reverse("operaciones:detalle_transaccion", args=[tx.pk])).status_code, 400)

    def test_bandeja_e_historial_cajero_separan_estados_y_clientes(self):
        """Sin asociaciones, la bandeja excluye pendientes online y el historial solo completadas/canceladas."""
        from django.utils import timezone
        from .models import Transaccion
        segundo = self.crear_cliente_asociado()
        excluido = self.crear_cliente_asociado_documento("cliente-excluido")
        esperados = {"PENDIENTE": set(), "COMPLETADA": set(), "CANCELADA": set()}
        for cliente in (self.cliente, segundo, excluido):
            for estado in esperados:
                tx = self.crear(cliente_id=cliente.pk, clave_idempotencia=self.clave_idempotencia()).transaccion
                campos = {"estado": estado}
                if estado == "CANCELADA":
                    campos.update(cancelado_por_keycloak_id=self.usuario_id,
                        cancelado_por_username=self.usuario_username,
                        cancelado_en=timezone.now(), motivo_cancelacion="Prueba histórica")
                Transaccion.objects.filter(pk=tx.pk).update(**campos)
                esperados[estado].add(tx.pk)
        UsuarioCliente.objects.all().delete()
        self.autenticar(roles=("CAJERO", "USUARIO"))
        sesion = self.client.session
        sesion.pop("selected_client", None)
        sesion.save()
        url = reverse("operaciones:historial_transacciones")
        bandeja = self.client.get(url).json()["transacciones"]
        historico = self.client.get(url, {"vista": "historial"}).json()["transacciones"]
        self.assertEqual(bandeja, [])
        self.assertEqual({tx["id"] for tx in historico}, esperados["COMPLETADA"] | esperados["CANCELADA"])
        self.assertTrue(all("pago_estado" in tx for tx in bandeja + historico))

    def crear_cliente_asociado_documento(self, documento):
        cliente = Cliente.objects.create(nombre_razon_social=documento, tipo_persona="FISICA",
            documento=documento, estado="ACTIVO", categoria=self.categoria)
        UsuarioCliente.objects.create(cliente=cliente, keycloak_user_id=self.usuario_id,
            username=self.usuario_username, activo=True)
        return cliente

    def test_historial_cajero_solo_lectura_y_sidebar_unico(self):
        """Historial es de solo lectura; bandeja ofrece acceso presencial sin mostrar el formulario online."""
        from html.parser import HTMLParser

        class Sidebar(HTMLParser):
            def __init__(self):
                super().__init__()
                self.en_nav = False
                self.activos = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "nav" and attrs.get("class") == "ge-frontend-nav":
                    self.en_nav = True
                if self.en_nav and tag == "a" and attrs.get("aria-current") == "page":
                    self.activos.append(attrs["href"])
            def handle_endtag(self, tag):
                if tag == "nav":
                    self.en_nav = False

        self.autenticar(roles=("CAJERO",))
        sesion = self.client.session
        sesion["selected_client"] = {"id": "inválido"}
        sesion.save()
        for nombre in ("inicio", "historial"):
            url = reverse(f"operaciones_web:{nombre}")
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 200)
            parser = Sidebar()
            parser.feed(respuesta.content.decode())
            self.assertEqual(parser.activos, [url])
            self.assertNotContains(respuesta, 'data-operation-form')
            if nombre == "historial":
                self.assertNotContains(respuesta, 'Nueva operación en efectivo')
            if nombre == "historial":
                for atributo in ('data-can-pay="false"', 'data-can-liquidate="false"',
                                 'data-can-view-payment="false"', 'data-can-cancel="false"'):
                    self.assertContains(respuesta, atributo)
                self.assertContains(respuesta, '?vista=historial')
            else:
                self.assertContains(respuesta, 'data-can-liquidate="true"')

    def test_historial_nuevo_no_altera_usuario_ni_admin(self):
        tx = self.crear().transaccion
        from .models import Transaccion
        Transaccion.objects.filter(pk=tx.pk).update(estado="COMPLETADA")
        pendiente = self.crear(clave_idempotencia=self.clave_idempotencia()).transaccion
        for roles in (("USUARIO",), ("ADMINISTRADOR", "CAJERO")):
            self.autenticar(roles=roles)
            url = reverse("operaciones:historial_transacciones")
            for query in ({}, {"vista": "historial"}):
                datos = self.client.get(url, query).json()["transacciones"]
                self.assertEqual({item["id"] for item in datos}, {tx.pk, pendiente.pk})
            self.assertEqual(self.client.get(reverse("operaciones_web:historial")).status_code, 403)

    def test_cajero_renderiza_bandeja_con_selected_client_invalido(self):
        """La bandeja y acceso presencial no requieren cliente en sesión ni asociaciones del cajero."""
        for roles in (("CAJERO",), ("CAJERO", "USUARIO")):
            with self.subTest(roles=roles):
                self.autenticar(roles=roles)
                sesion = self.client.session
                sesion["selected_client"] = {"id": "contexto-invalido"}
                sesion.save()
                respuesta = self.client.get(reverse("operaciones_web:inicio"))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "Bandeja operativa")
                self.assertNotContains(respuesta, 'data-operation-form')
                self.assertContains(respuesta, reverse("operaciones_web:presencial"))
                self.assertIsNone(respuesta.context["cliente_operacion"])
                self.assertContains(respuesta, "Historial de operaciones")

    def test_usuario_con_contexto_invalido_conserva_comportamiento_previo(self):
        self.autenticar()
        sesion = self.client.session
        sesion["selected_client"] = {"id": "contexto-invalido"}
        sesion.save()
        # Caracterización del comportamiento previo; no corregir USUARIO en este paso.
        with self.assertRaises(ValueError):
            self.client.get(reverse("operaciones_web:inicio"))

    def test_venta_previsualiza_y_confirma_con_tasa_de_venta(self):
        """VENTA previsualiza con tasa de venta y completa al confirmar sin Pago Stripe."""

        preview = self.previsualizar(tipo="VENTA")
        resultado = self.crear(tipo="VENTA")

        self.assertEqual(preview.tasa, self.tasa.venta)
        self.assertEqual(resultado.transaccion.tasa_aplicada, self.tasa.venta)
        self.assertEqual(resultado.transaccion.estado, "COMPLETADA")

    def test_api_confirmacion_y_repeticion_registran_pendiente_sin_pago(self):
        """COMPRA y VENTA se registran una sola vez sin iniciar pagos."""
        self.autenticar()
        for tipo in ("COMPRA", "VENTA"):
            with self.subTest(tipo=tipo):
                datos = json.dumps(self.parametros_confirmacion_http(tipo=tipo), default=str)
                nueva = self.client.post(
                    reverse("operaciones:crear_transaccion"),
                    data=datos, content_type="application/json",
                )
                self.assertEqual(nueva.status_code, 201)
                self.assertFalse(nueva.json()["repetida"])
                self.assertEqual(nueva.json()["transaccion"]["estado"], "COMPLETADA" if tipo == "VENTA" else "PENDIENTE")

                repetida = self.client.post(
                    reverse("operaciones:crear_transaccion"),
                    data=datos, content_type="application/json",
                )
                self.assertEqual(repetida.status_code, 200)
                self.assertTrue(repetida.json()["repetida"])
                original = nueva.json()["transaccion"]
                recuperada = repetida.json()["transaccion"]
                self.assertEqual(recuperada["id"], original["id"])
                self.assertEqual(recuperada["estado"], "COMPLETADA" if tipo == "VENTA" else "PENDIENTE")
                for campo in ("monto_origen", "monto_destino", "tasa_aplicada", "porcentaje_comision", "importe_comision"):
                    self.assertEqual(Decimal(recuperada[campo]), Decimal(original[campo]))
                self.assertFalse(Pago.objects.exists())

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
        self.assertEqual(response.json()["transacciones"][0]["estado"], "COMPLETADA")

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
        self.assertEqual(detalle["estado"], "COMPLETADA")
        self.assertEqual(detalle["tasa_aplicada"], tasa_guardada)
        self.assertEqual(detalle["tasa_comercial"]["version"], 1)
        self.assertEqual(detalle["metodo_pago"]["nombre"], "Tarjeta de prueba")
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
