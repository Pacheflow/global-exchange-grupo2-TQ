"""Dashboard filtrado: contrato, períodos, precisión, actividad y permisos."""
import json
import re
import time
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import DatabaseError, connection
from django.http import QueryDict
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from monedas.models import Moneda
from operaciones import test_finanzas as fixtures
from operaciones.models import Transaccion
from usuarios.dashboard import divisas_dashboard, validar_filtros
from usuarios.services.keycloak import SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO


@override_settings(TIME_ZONE="America/Asuncion")
class DashboardAdministrativoTests(TestCase):
    setUpTestData = classmethod(fixtures.FinanzasTests.setUpTestData.__func__)
    operacion = fixtures.FinanzasTests.operacion

    def setUp(self):
        self.url = reverse("operaciones:dashboard_metricas")
        self.panel = reverse("usuarios:dashboard")
        self.autenticar(["ADMINISTRADOR"])
        reloj = patch("usuarios.dashboard.timezone.localdate", return_value=date(2026, 11, 19))
        reloj.start()
        self.addCleanup(reloj.stop)

    def autenticar(self, roles, *, expirada=False):
        sesion = self.client.session
        perfil = {"sub": "qa-dashboard", "preferred_username": "QA"}
        sesion.update({SESSION_AUTENTICADO: True, SESSION_EXPIRA_EN: time.time() + (-60 if expirada else 3600),
                       SESSION_ROLES: roles, SESSION_USUARIO: perfil, "kc_user": perfil})
        sesion.save()

    def datos(self, **query):
        response = self.client.get(self.url, query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_periodos_calendario_y_granularidad(self):
        for periodo, desde, agrupacion in (("hoy", "2026-11-19", "dia"),
                ("semana", "2026-11-16", "dia"), ("mes", "2026-11-01", "dia"),
                ("3meses", "2026-09-01", "mes"), ("6meses", "2026-06-01", "mes"),
                ("12meses", "2025-12-01", "mes")):
            with self.subTest(periodo=periodo):
                data = self.datos(periodo=periodo)
                self.assertEqual(data["filtros"]["desde"], desde)
                self.assertEqual(data["filtros"]["hasta"], "2026-11-19")
                self.assertEqual(data["filtros"]["agrupacion"], agrupacion)
                self.assertEqual(data["filtros"]["zona_horaria"], "America/Asuncion")

    def test_personalizado_inferido_y_explicito(self):
        for query in (dict(desde="2026-10-01", hasta="2026-10-03"),
                      dict(periodo="personalizado", desde="2026-10-01", hasta="2026-10-03")):
            with self.subTest(query=query):
                self.assertEqual(self.datos(**query)["filtros"]["periodo"], "personalizado")
        self.assertEqual(len(self.datos(desde="2026-10-01", hasta="2026-10-03")["evolucion"]), 3)

    def test_limite_inclusivo_y_umbral_de_puntos(self):
        for hasta, agrupacion, longitud in (("2026-03-03", "dia", 62), ("2026-03-04", "mes", 3)):
            data = self.datos(desde="2026-01-01", hasta=hasta)
            self.assertEqual(data["filtros"]["agrupacion"], agrupacion)
            self.assertEqual(len(data["evolucion"]), longitud)
        self.assertEqual(self.client.get(self.url, {"desde": "2024-01-01", "hasta": "2024-12-31"}).status_code, 200)
        self.assertEqual(self.client.get(self.url, {"desde": "2024-01-01", "hasta": "2025-01-01"}).status_code, 400)

    def test_compra_y_venta_usd_se_suman_sin_duplicar_y_siempre_en_pyg(self):
        self.operacion(fecha="2026-11-18T12:00:00")
        self.operacion(fecha="2026-11-19T12:00:00", tipo="VENTA", moneda_origen=self.pyg,
                       moneda_destino=self.usd, tasa_aplicada=Decimal("0.00014"), importe_comision=Decimal("0.98"))
        resumen = self.datos(divisa="USD")["resumen"]
        self.assertEqual(resumen["ganancia_pyg"], "14000.000000")
        self.assertEqual(resumen["volumen_pyg"], "700100.000000")
        self.assertEqual((resumen["operaciones"], resumen["compras"], resumen["ventas"]), (2, 1, 1))
        self.assertEqual(resumen["moneda"], "PYG")
        self.assertEqual(Transaccion.objects.count(), 2)

    def test_eur_y_todas_respetan_divisa_y_no_recalcula_tasa_actual(self):
        self.operacion(fecha="2026-11-01T12:00:00")
        self.operacion(fecha="2026-11-01T12:00:00", moneda_origen=self.eur, importe_comision=3500)
        self.tasa.compra = 9999
        self.tasa.save(update_fields=["compra"])
        self.assertEqual(self.datos(divisa="USD")["resumen"]["ganancia_pyg"], "7000.000000")
        self.assertEqual(self.datos(divisa="EUR")["resumen"]["ganancia_pyg"], "3500.000000")
        self.assertEqual(self.datos()["resumen"]["ganancia_pyg"], "10500.000000")

    def test_combinacion_periodo_divisa_y_limites_locales(self):
        for fecha in ("2026-11-18T23:59:59", "2026-11-19T00:00:00", "2026-11-19T23:59:59", "2026-11-20T00:00:00"):
            self.operacion(fecha=fecha)
        self.operacion(fecha="2026-11-19T12:00:00", moneda_origen=self.eur)
        datos = self.datos(periodo="hoy", divisa="USD")
        self.assertEqual(datos["resumen"]["operaciones"], 2)
        self.assertEqual(datos["resumen"]["ganancia_pyg"], "14000.000000")
        self.assertEqual(len(datos["actividad_reciente"]), 2)

    def test_sin_operaciones_o_divisa_sin_datos_ceros_y_sin_dona(self):
        self.operacion(fecha="2026-10-01T12:00:00")
        for query in ({}, {"divisa": "EUR"}):
            data = self.datos(**query)
            for key in ("ganancia_pyg", "volumen_pyg"):
                self.assertEqual(data["resumen"][key], "0.000000")
            for key in ("operaciones", "compras", "ventas"):
                self.assertEqual(data["resumen"][key], 0)
            self.assertEqual(data["actividad_reciente"], [])

    def test_exclusiones_sin_pyg_conservan_conteos_y_actividad(self):
        self.operacion(fecha="2026-11-01T12:00:00")
        self.operacion(fecha="2026-11-01T12:00:00", moneda_destino=self.eur)
        datos = self.datos(divisa="USD")
        self.assertEqual(datos["resumen"]["ganancia_pyg"], "7000.000000")
        self.assertEqual(datos["resumen"]["excluidas"], 1)
        self.assertEqual(datos["resumen"]["operaciones"], 2)
        self.assertEqual(len(datos["actividad_reciente"]), 2)
        self.assertTrue(datos["advertencias"])

    def test_solo_cruces_sin_conversion_son_subtotal_cero_con_aviso(self):
        self.operacion(fecha="2026-11-01T12:00:00", moneda_destino=self.eur)
        datos = self.datos(divisa="USD")
        self.assertEqual(datos["resumen"]["ganancia_pyg"], "0.000000")
        self.assertEqual(datos["resumen"]["excluidas"], 1)
        response = self.client.get(self.panel, {"divisa": "USD"})
        self.assertContains(response, "Subtotal disponible: 1 operaciones excluidas")

    def test_semana_y_meses_cruzan_anio(self):
        divisas = divisas_dashboard()
        semana = validar_filtros(QueryDict("periodo=semana"), divisas=divisas, hoy=date(2027, 1, 1))
        self.assertEqual(semana["desde"], "2026-12-28")
        trimestre = validar_filtros(QueryDict("periodo=3meses"), divisas=divisas, hoy=date(2027, 1, 1))
        self.assertEqual(trimestre["desde"], "2026-11-01")

    def test_actividad_filtrada_limitada_a_cinco_y_ordenada(self):
        elegidas = [self.operacion(fecha="2026-11-18T12:00:00") for _ in range(7)]
        self.operacion(fecha="2026-10-18T12:00:00")
        self.operacion(fecha="2026-11-18T12:00:00", moneda_origen=self.eur)
        reciente = self.datos(divisa="USD")["actividad_reciente"]
        self.assertEqual([op["id"] for op in reciente], [op.pk for op in reversed(elegidas[-5:])])
        self.assertEqual(self.client.get(reciente[0]["detalle"]).status_code, 200)

    def test_solo_completadas(self):
        self.operacion(fecha="2026-11-01T12:00:00")
        self.operacion(fecha="2026-11-01T12:00:00", estado="PENDIENTE")
        self.operacion(fecha="2026-11-01T12:00:00", estado="CANCELADA", cancelado_por_keycloak_id="qa", cancelado_por_username="qa", cancelado_en="2026-11-01T12:00:00Z", motivo_cancelacion="QA")
        self.assertEqual(self.datos()["resumen"]["operaciones"], 1)

    def test_distribucion_cambia_de_divisa_a_tipo(self):
        self.operacion(fecha="2026-11-01T12:00:00")
        self.operacion(fecha="2026-11-01T12:00:00", tipo="VENTA", moneda_origen=self.eur)
        todas = self.datos()["distribucion"]
        self.assertEqual(todas["modo"], "divisa")
        self.assertEqual({p["categoria"] for p in todas["categorias"]}, {"USD", "EUR"})
        self.assertEqual([p["porcentaje"] for p in todas["categorias"]], ["50.00", "50.00"])
        usd = self.datos(divisa="USD")["distribucion"]
        self.assertEqual(usd["titulo"], "Compras vs Ventas")
        self.assertEqual(usd["categorias"][0], {"categoria": "Compra", "cantidad": 1, "porcentaje": "100.00"})

    def test_parametros_invalidos_no_llegan_a_servicio(self):
        for query in ("periodo=otro", "periodo=", "divisa=ZZZ", "divisa=PYG", "divisa=usd", "periodo=mes&periodo=hoy",
                      "divisa=USD&divisa=EUR", "foo=1", "desde=2026-11-01", "hasta=2026-11-19",
                      "desde=2026-11-20&hasta=2026-11-19", "desde=2026-02-30&hasta=2026-03-01",
                      "desde=20261101&hasta=2026-11-19", "periodo=hoy&desde=2026-11-01&hasta=2026-11-19",
                      "desde=9999-12-30&hasta=9999-12-31"):
            with self.subTest(query=query), patch("operaciones.dashboard_views.consultar_dashboard_administrativo") as servicio:
                self.assertEqual(self.client.get(self.url + "?" + query).status_code, 400)
                servicio.assert_not_called()

    def test_catalogo_dinamico_solo_activas_y_sin_pyg(self):
        Moneda.objects.update_or_create(codigo="BRL", defaults={"nombre": "Real", "simbolo": "R", "estado": "ACTIVA"})
        Moneda.objects.update_or_create(codigo="ARS", defaults={"nombre": "Peso", "simbolo": "$", "estado": "INACTIVA"})
        codigos = {m["codigo"] for m in divisas_dashboard()}
        self.assertIn("BRL", codigos)
        self.assertNotIn("ARS", codigos)
        self.assertNotIn("PYG", codigos)
        self.assertEqual(self.client.get(self.url, {"divisa": "ARS"}).status_code, 400)
        self.assertEqual(self.datos(divisa="BRL")["resumen"]["operaciones"], 0)

    def test_permisos_api_y_paneles_por_rol(self):
        self.assertEqual(Client().get(self.url).status_code, 401)
        self.assertEqual(Client().get(self.panel).status_code, 302)
        for rol, plantilla in (("USUARIO", "usuario"), ("CAJERO", "cajero"), ("ANALISTA_CAMBIARIO", "analista")):
            self.autenticar([rol])
            self.assertEqual(self.client.get(self.url).status_code, 403)
            with patch("usuarios.dashboard.consultar_dashboard_administrativo") as consulta:
                response = self.client.get(self.panel)
            consulta.assert_not_called()
            self.assertTemplateUsed(response, f"frontend/dashboard_{plantilla}.html")
        self.autenticar(["ADMINISTRADOR"], expirada=True)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_json_coherente_cache_y_metodos(self):
        response = self.client.get(self.url)
        data = response.json()
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(data["fecha_imputacion"], "fecha_creacion")
        self.assertEqual(sum(p["cantidad"] for p in self.datos(divisa="USD")["distribucion"]["categorias"]), data["resumen"]["operaciones"])
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_error_controlado_no_se_disfraza_de_cero(self):
        with patch("operaciones.dashboard_views.consultar_dashboard_administrativo", side_effect=DatabaseError):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("resumen", response.json())
        with patch("usuarios.dashboard.consultar_dashboard_administrativo", side_effect=DatabaseError):
            response = self.client.get(self.panel)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No disponible", count=5)
        self.assertIsNone(response.context["datos_dashboard"])

    def test_inicial_ssr_y_api_comparten_filtros_datos_y_pyg(self):
        self.operacion(fecha="2026-11-01T12:00:00", importe_comision=Decimal("51660.5"))
        response = self.client.get(self.panel, {"divisa": "USD"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/dashboard_administrador.html")
        self.assertContains(response, "51.661 PYG")
        self.assertContains(response, "Actividad reciente")
        self.assertContains(response, "Ver reporte completo")
        self.assertContains(response, "Ganancia del período")
        self.assertNotContains(response, "Ganancia semanal")
        data = json.loads(re.search(r'<script id="dashboard-inicial" type="application/json">(.*?)</script>', response.content.decode(), re.S).group(1))
        self.assertEqual(data, self.datos(divisa="USD"))
        self.assertEqual(data["resumen"]["ganancia_pyg"], "51660.500000")

    def test_panel_invalido_400_y_sin_consulta(self):
        with patch("usuarios.dashboard.consultar_dashboard_administrativo") as servicio:
            response = self.client.get(self.panel, {"periodo": "otro"})
        servicio.assert_not_called()
        self.assertEqual(response.status_code, 400)

    def test_lecturas_sin_io_externo_ni_escrituras_y_sin_n_mas_uno(self):
        for _ in range(7):
            self.operacion(fecha="2026-11-01T12:00:00")
        with patch("requests.sessions.Session.request", side_effect=AssertionError("IO externo")):
            with CaptureQueriesContext(connection) as consultas:
                self.datos(divisa="USD")
        self.assertFalse(any(re.search(r"\b(INSERT|UPDATE|DELETE)\b", q["sql"], re.I) for q in consultas))
        self.assertEqual(len([q for q in consultas if 'FROM "operaciones_transaccion"' in q["sql"]]), 2)
