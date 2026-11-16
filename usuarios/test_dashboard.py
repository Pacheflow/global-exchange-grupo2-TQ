"""Contrato y permisos del dashboard administrativo de Sprint 6, fase 1."""

import json
import re
import time
import uuid
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import DatabaseError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from operaciones.models import Transaccion
from tasas.models import TasaComercial
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)


class DashboardAdministrativoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cliente = Cliente.objects.create(nombre_razon_social="Cliente dashboard",
                                            tipo_persona="FISICA", documento="QA-DASH")
        cls.origen = Moneda.objects.create(codigo="QDUSD", nombre="USD QA", simbolo="$", estado="ACTIVA")
        cls.destino = Moneda.objects.create(codigo="QDPYG", nombre="PYG QA", simbolo="Gs", estado="ACTIVA")
        cls.metodo = MetodoPago.objects.create(nombre="Dashboard QA", naturaleza="ELECTRONICO")
        cls.tasa = TasaComercial.objects.create(moneda_origen=cls.origen, moneda_destino=cls.destino,
                                               compra=7000, venta=7100, usuario_id="qa")

    def setUp(self):
        self.url = reverse("usuarios:dashboard")
        self.autenticar(["ADMINISTRADOR"])

    def autenticar(self, roles, *, expirada=False):
        sesion = self.client.session
        sesion[SESSION_AUTENTICADO] = True
        perfil = {"sub": "dashboard-qa", "preferred_username": "admin_qa"}
        sesion[SESSION_USUARIO] = perfil
        sesion["kc_user"] = perfil
        sesion[SESSION_EXPIRA_EN] = time.time() + (-60 if expirada else 3600)
        sesion[SESSION_ROLES] = roles
        sesion.save()

    def operacion(self, tipo="COMPRA", estado="COMPLETADA", fecha=None):
        cancelacion = dict(cancelado_por_keycloak_id="qa", cancelado_por_username="qa",
                           cancelado_en=timezone.now(), motivo_cancelacion="QA") if estado == "CANCELADA" else {}
        op = Transaccion.objects.create(
            clave_idempotencia=str(uuid.uuid4()), cliente=self.cliente,
            creado_por_keycloak_id="qa", tipo=tipo, estado=estado,
            moneda_origen=self.origen, moneda_destino=self.destino,
            monto_origen=100, monto_destino=693000, tasa_comercial=self.tasa,
            tasa_aplicada=7000, porcentaje_comision=1, importe_comision=7000,
            metodo_pago=self.metodo, metodo_pago_nombre="Dashboard QA", **cancelacion,
        )
        if fecha:
            Transaccion.objects.filter(pk=op.pk).update(fecha_creacion=fecha)
        return op

    def resumen(self):
        return self.client.get(self.url).context["resumen_dashboard"]

    def test_administrador_visualiza_dashboard_y_contrato_json(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "frontend/dashboard_administrador.html")
        contenido = re.search(r'<script id="dashboard-resumen" type="application/json">(.*?)</script>',
                              respuesta.content.decode(), re.S).group(1)
        self.assertEqual(json.loads(contenido), {
            "ganancia_dia": None, "ganancia_semana": None, "ganancia_mes": None,
            "operaciones": 0, "compras": 0, "ventas": 0, "volumen": None, "moneda": "PYG",
        })

    def test_otros_roles_no_reciben_dashboard_ni_consultan_datos_administrativos(self):
        for rol, plantilla in (("USUARIO", "usuario"), ("CAJERO", "cajero"),
                               ("ANALISTA_CAMBIARIO", "analista")):
            with self.subTest(rol=rol):
                self.autenticar([rol])
                with patch("usuarios.dashboard.consultar_dashboard_administrativo") as consulta:
                    respuesta = self.client.get(self.url)
                consulta.assert_not_called()
                self.assertEqual(respuesta.status_code, 200)
                self.assertTemplateUsed(respuesta, f"frontend/dashboard_{plantilla}.html")
                self.assertTemplateNotUsed(respuesta, "frontend/dashboard_administrador.html")
                self.assertNotIn("resumen_dashboard", respuesta.context)
                self.assertNotContains(respuesta, 'id="dashboard-resumen"')

    def test_anonimo_y_sesion_expirada_no_reciben_dashboard(self):
        for expirada in (False, True):
            with self.subTest(expirada=expirada):
                if expirada:
                    self.autenticar(["ADMINISTRADOR"], expirada=True)
                    cliente = self.client
                else:
                    cliente = Client()
                with patch("usuarios.dashboard.consultar_dashboard_administrativo") as consulta:
                    respuesta = cliente.get(self.url)
                self.assertEqual(respuesta.status_code, 302)
                consulta.assert_not_called()

    def test_conteo_total_operaciones(self):
        self.operacion()
        self.operacion("VENTA")
        self.assertEqual(self.resumen()["operaciones"], 2)

    def test_conteo_compra(self):
        self.operacion()
        self.operacion()
        self.operacion("VENTA")
        self.assertEqual(self.resumen()["compras"], 2)

    def test_conteo_venta(self):
        self.operacion()
        self.operacion("VENTA")
        self.operacion("VENTA")
        self.assertEqual(self.resumen()["ventas"], 2)

    def test_solo_completadas_en_conteos_y_actividad(self):
        completada = self.operacion()
        self.operacion("VENTA", "PENDIENTE")
        self.operacion("VENTA", "CANCELADA")
        respuesta = self.client.get(self.url)
        resumen = respuesta.context["resumen_dashboard"]
        self.assertEqual((resumen["operaciones"], resumen["compras"], resumen["ventas"]), (1, 1, 0))
        self.assertEqual([op.pk for op in respuesta.context["actividad_reciente"]], [completada.pk])

    def test_periodo_historico_incluye_fechas_antiguas_y_no_aplica_filtros_get(self):
        self.operacion(fecha=datetime(2020, 1, 1, tzinfo=ZoneInfo("America/Asuncion")))
        self.operacion("VENTA")
        respuesta = self.client.get(self.url, {"fecha_desde": "2099-01-01", "estado": "PENDIENTE"})
        self.assertEqual(respuesta.context["resumen_dashboard"]["operaciones"], 2)
        self.assertContains(respuesta, "histórico completo, sin filtro de fechas")

    def test_sin_operaciones_completadas_muestra_vacio_y_ceros_reales(self):
        self.operacion(estado="PENDIENTE")
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Todavía no hay operaciones completadas")
        for clave in ("operaciones", "compras", "ventas"):
            self.assertEqual(respuesta.context["resumen_dashboard"][clave], 0)

    def test_metricas_financieras_no_disponibles_aunque_haya_comisiones(self):
        self.operacion()
        respuesta = self.client.get(self.url)
        for clave in ("ganancia_dia", "ganancia_semana", "ganancia_mes", "volumen"):
            self.assertIsNone(respuesta.context["resumen_dashboard"][clave])
        self.assertContains(respuesta, "No disponible", count=4)
        for texto in ("Próximamente", "Reporte futuro", "—"):
            self.assertNotContains(respuesta, texto)

    def test_cero_financiero_disponible_no_se_confunde_con_null(self):
        from usuarios.dashboard import contrato_dashboard
        resumen = contrato_dashboard()
        resumen.update(ganancia_dia="0", operaciones=0, compras=0, ventas=0)
        with patch("usuarios.dashboard.consultar_dashboard_administrativo", return_value=(resumen, [])):
            respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "0 PYG")
        self.assertContains(respuesta, "No disponible", count=3)

    def test_carga_y_actividad_son_lecturas_sin_llamadas_externas(self):
        self.operacion()
        antes = list(Transaccion.objects.values())
        with patch("requests.sessions.Session.request", side_effect=AssertionError("IO externo")) as externo:
            with CaptureQueriesContext(connection) as consultas:
                respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        externo.assert_not_called()
        escrituras = [q["sql"] for q in consultas if re.search(
            r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", q["sql"], re.I)]
        self.assertEqual(escrituras, [])
        self.assertEqual(list(Transaccion.objects.values()), antes)
        lecturas_operaciones = [q for q in consultas if 'FROM "operaciones_transaccion"' in q["sql"]]
        self.assertEqual(len(lecturas_operaciones), 2)

    def test_actividad_limitada_a_cinco_ordenada_por_fecha_e_id(self):
        fecha = datetime(2026, 1, 1, tzinfo=ZoneInfo("America/Asuncion"))
        operaciones = [self.operacion(fecha=fecha) for _ in range(7)]
        self.operacion(fecha=datetime(2020, 1, 1, tzinfo=ZoneInfo("America/Asuncion")))
        respuesta = self.client.get(self.url)
        self.assertEqual([op.pk for op in respuesta.context["actividad_reciente"]],
                         [op.pk for op in reversed(operaciones[-5:])])
        self.assertEqual(respuesta.context["resumen_dashboard"]["operaciones"], 8)

    def test_enlaces_a_reporte_y_detalle_funcionan(self):
        op = self.operacion()
        respuesta = self.client.get(self.url)
        for url in (reverse("operaciones_web:reporte_administrativo_transacciones"),
                    reverse("operaciones_web:detalle_reporte_transaccion", args=[op.pk])):
            self.assertContains(respuesta, f'href="{url}"')
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_error_no_se_presenta_como_cero_ni_como_periodo_vacio(self):
        with patch("usuarios.dashboard.consultar_dashboard_administrativo", side_effect=DatabaseError):
            respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "No se pudieron cargar los datos del dashboard")
        self.assertContains(respuesta, 'role="alert"')
        self.assertNotContains(respuesta, "Todavía no hay operaciones completadas")
        self.assertIsNone(respuesta.context["resumen_dashboard"]["operaciones"])
        self.assertContains(respuesta, "No disponible", count=7)
