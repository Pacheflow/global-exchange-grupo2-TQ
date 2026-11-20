"""Mercado analista: filtros, historia, precisión, agregados y aislamiento de rol."""
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda
from operaciones import test_finanzas as fixtures
from usuarios.services.keycloak import SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO
from .models import TasaComercial, TasaReferencia, ConsultaProveedorTasas


@override_settings(TIME_ZONE="America/Asuncion")
class DashboardAnalistaTests(TestCase):
    setUpTestData = classmethod(fixtures.FinanzasTests.setUpTestData.__func__)
    operacion = fixtures.FinanzasTests.operacion

    def setUp(self):
        self.url = reverse("tasas:dashboard_analista")
        self.panel = reverse("usuarios:dashboard")
        self.login()
        reloj = patch("usuarios.dashboard.timezone.localdate", return_value=date(2026, 11, 19))
        reloj.start()
        self.addCleanup(reloj.stop)
        TasaComercial.objects.update(vigente=False, fecha_registro=timezone.make_aware(datetime(2020, 1, 1)))

    def login(self, roles=None):
        sesion = self.client.session
        perfil = {"sub": "analista-prueba", "preferred_username": "Analista"}
        sesion.update({SESSION_AUTENTICADO: True, SESSION_EXPIRA_EN: time.time() + 3600,
            SESSION_ROLES: roles or ["ANALISTA_CAMBIARIO"], SESSION_USUARIO: perfil, "kc_user": perfil})
        sesion.save()

    def datos(self, **query):
        response = self.client.get(self.url, query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def registrar(self, fecha, compra="6000", venta="6100", moneda=None, vigente=False, destino=None):
        row = TasaComercial.objects.create(moneda_origen=moneda or self.usd,
            moneda_destino=destino or self.pyg, compra=Decimal(compra), venta=Decimal(venta),
            usuario_id="autor-privado", vigente=vigente)
        TasaComercial.objects.filter(pk=row.pk).update(fecha_registro=timezone.make_aware(datetime.fromisoformat(fecha)))
        row.refresh_from_db()
        return row

    def referencia(self, codigo="USD", valor="6500", vencida=False):
        moneda = Moneda.objects.get(codigo=codigo)
        consulta = ConsultaProveedorTasas.objects.create(fuente="Prueba", moneda_base=moneda,
            fecha_hora_fuente=timezone.now(), respuesta={})
        return TasaReferencia.objects.create(moneda_base=moneda, moneda_cotizada=self.pyg,
            valor=Decimal(valor), fuente="Prueba", consulta=consulta, fecha_hora_fuente=timezone.now(),
            vigente_hasta=timezone.now() + timedelta(days=-1 if vencida else 1))

    def test_acceso_analista_json_privado_y_sin_datos_administrativos(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertEqual(data["criterio_variacion"], "compra_comercial")
        for campo in ("ganancia", "comision", "cliente", "usuario_id", "autor-privado", "rentabilidad"):
            self.assertNotIn(campo, response.content.decode().lower())

    def test_otros_roles_y_multirrol_efectivo_rechazados(self):
        for roles in (["ADMINISTRADOR"], ["USUARIO"], ["CAJERO"], ["ADMINISTRADOR", "ANALISTA_CAMBIARIO"]):
            with self.subTest(roles=roles):
                self.login(roles)
                self.assertEqual(self.client.get(self.url).status_code, 403)
        self.login(["USUARIO", "ANALISTA_CAMBIARIO"])
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_sesion_expirada_y_anonimo(self):
        session = self.client.session
        session[SESSION_EXPIRA_EN] = time.time() - 60
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_solo_get(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def periodo(self, periodo, desde):
        filtros = self.datos(periodo=periodo)["filtros"]
        self.assertEqual(filtros["desde"], desde)
        self.assertEqual(filtros["hasta"], "2026-11-19")
    def test_hoy(self): self.periodo("hoy", "2026-11-19")
    def test_semana(self): self.periodo("semana", "2026-11-16")
    def test_mes(self): self.periodo("mes", "2026-11-01")
    def test_tres_meses(self): self.periodo("3meses", "2026-09-01")
    def test_seis_meses(self): self.periodo("6meses", "2026-06-01")
    def test_doce_meses(self): self.periodo("12meses", "2025-12-01")

    def test_personalizado_e_inclusion_de_extremos_locales(self):
        self.registrar("2026-11-02T00:00:00")
        self.registrar("2026-11-03T23:59:59")
        self.registrar("2026-11-04T00:00:00")
        data = self.datos(desde="2026-11-02", hasta="2026-11-03", divisa="USD")
        self.assertEqual(data["filtros"]["periodo"], "personalizado")
        self.assertEqual(len(data["evolucion"]["puntos"]), 2)

    def test_usd_y_eur_aislan_series_mercado_y_variacion(self):
        for moneda, compra in ((self.usd, "6000"), (self.eur, "7000")):
            self.registrar("2026-11-01T12:00:00", compra=compra, moneda=moneda, vigente=True)
        for codigo in ("USD", "EUR"):
            data = self.datos(divisa=codigo)
            self.assertEqual(data["evolucion"]["par"], codigo + "/PYG")
            self.assertEqual([r["divisa"] for r in data["mercado"]], [codigo])
            self.assertEqual([r["divisa"] for r in data["variaciones"]], [codigo])

    def test_todas_y_catalogo_dinamico_incluyen_nueva_divisa(self):
        brl = Moneda.objects.create(codigo="ZAR", nombre="Rand", simbolo="R")
        self.registrar("2026-11-01T12:00:00", moneda=brl, vigente=True)
        self.assertIn("ZAR", [r["divisa"] for r in self.datos()["mercado"]])
        self.assertEqual(self.datos(divisa="ZAR")["evolucion"]["par"], "ZAR/PYG")
        brl.estado = "INACTIVA"
        brl.save()
        self.assertEqual(self.client.get(self.url, {"divisa": "ZAR"}).status_code, 400)
        self.assertNotIn("ZAR", [r["divisa"] for r in self.datos()["mercado"]])

    def test_evolucion_compra_y_venta_no_interpoladas(self):
        self.registrar("2026-11-01T10:00:00", compra="6000.1234567890", venta="6100.5678901234")
        self.registrar("2026-11-03T12:00:00", compra="6120", venta="6200")
        puntos = self.datos(divisa="USD")["evolucion"]["puntos"]
        self.assertEqual(len(puntos), 2)
        self.assertEqual(puntos[0]["compra"], "6000.123456789")
        self.assertEqual(puntos[0]["venta"], "6100.5678901234")
        self.assertEqual(puntos[1]["compra"], "6120")

    def test_compactacion_diaria_conserva_ambos_extremos(self):
        self.registrar("2026-11-01T08:00:00", compra="6000")
        self.registrar("2026-11-01T10:00:00", compra="6050")
        self.registrar("2026-11-01T12:00:00", compra="6100")
        puntos = self.datos(divisa="USD")["evolucion"]["puntos"]
        self.assertEqual([p["compra"] for p in puntos], ["6000", "6100"])

    def test_variacion_compra_real_no_se_mezcla_con_referencia_ni_venta(self):
        self.referencia(valor="9999")
        self.registrar("2026-10-31T23:59:59", compra="1")
        self.registrar("2026-11-01T10:00:00", compra="6000", venta="8000")
        self.registrar("2026-11-19T10:00:00", compra="6120", venta="7000")
        data = self.datos(divisa="USD")
        var = data["variaciones"][0]["variacion"]
        self.assertEqual(var["porcentaje"], "2")
        self.assertEqual(var["absoluta"], "120")
        self.assertEqual(data["referencias"]["USD"]["valor"], "9999")

    def test_mayor_variacion_por_magnitud_con_signo(self):
        for moneda, inicial, final in ((self.usd, "6000", "6120"), (self.eur, "7000", "6300")):
            self.registrar("2026-11-01T10:00:00", compra=inicial, moneda=moneda)
            self.registrar("2026-11-19T10:00:00", compra=final, moneda=moneda)
        mayor = self.datos()["resumen"]["mayor_variacion"]
        self.assertEqual((mayor["divisa"], mayor["porcentaje"]), ("EUR", "-10"))

    def test_mas_operada_respeta_periodo_completada_y_divisa(self):
        self.operacion(fecha="2026-11-19T12:00:00")
        self.operacion(fecha="2026-11-19T12:00:00")
        self.operacion(fecha="2026-11-18T12:00:00", moneda_origen=self.eur)
        self.operacion(fecha="2026-10-18T12:00:00", moneda_origen=self.eur)
        self.operacion(fecha="2026-11-19T12:00:00", estado="PENDIENTE", moneda_origen=self.eur)
        self.assertEqual(self.datos()["resumen"]["divisa_mas_operada"], {"divisa": "USD", "operaciones": 2})
        self.assertEqual(self.datos(divisa="EUR")["resumen"]["divisa_mas_operada"], {"divisa": "EUR", "operaciones": 1})

    def test_tasas_vigentes_y_ultima_actualizacion_reales_no_dependen_del_periodo(self):
        self.registrar("2026-11-01T10:00:00")
        ultima = self.registrar("2026-11-19T14:35:00", vigente=True)
        self.registrar("2026-11-18T14:30:00", vigente=True, moneda=self.eur)
        summary = self.datos(periodo="hoy")["resumen"]
        self.assertEqual(summary["tasas_vigentes"], 2)
        self.assertEqual(summary["ultima_actualizacion"], ultima.fecha_registro.isoformat())
        self.assertEqual(self.datos(divisa="EUR")["resumen"]["tasas_vigentes"], 1)

    def test_spread_exacto_venta_menos_compra_sin_redondeo(self):
        self.registrar("2026-11-19T12:00:00", compra="6000.4", venta="6100.7", vigente=True)
        row = self.datos(divisa="USD")["mercado"][0]
        self.assertEqual((row["compra"], row["venta"], row["spread"]), ("6000.4", "6100.7", "100.3"))

    def test_operaciones_por_divisa_conteos_y_porcentajes(self):
        for moneda in (self.usd, self.usd, self.eur):
            self.operacion(fecha="2026-11-19T12:00:00", moneda_origen=moneda)
        data = self.datos()["distribucion"]
        self.assertEqual(data["modo"], "divisa")
        categorias = {r["nombre"]: r for r in data["categorias"]}
        self.assertEqual(categorias["USD"]["cantidad"], 2)
        self.assertAlmostEqual(Decimal(categorias["USD"]["porcentaje"]), Decimal("66.6666666666666667"))

    def test_cruces_no_duplican_una_divisa_ni_exponen_importes(self):
        self.operacion(fecha="2026-11-19T12:00:00", moneda_destino=self.eur)
        data = self.datos()
        self.assertEqual(data["resumen"]["operaciones"], 1)
        self.assertEqual(data["distribucion"]["total"], 2)
        self.assertEqual({c["nombre"]: c["cantidad"] for c in data["distribucion"]["categorias"]}, {"USD": 1, "EUR": 1})

    def test_divisa_seleccionada_compra_venta_sin_dona_de_una_divisa(self):
        self.operacion(fecha="2026-11-19T12:00:00")
        self.operacion(fecha="2026-11-19T12:00:00", tipo="VENTA", moneda_origen=self.pyg, moneda_destino=self.usd)
        data = self.datos(divisa="USD")["distribucion"]
        self.assertEqual(data["modo"], "tipo")
        self.assertEqual({c["nombre"]: c["porcentaje"] for c in data["categorias"]}, {"Compra": "50", "Venta": "50"})

    def test_vacio_y_una_version_no_inventan_variaciones(self):
        data = self.datos()
        self.assertEqual(data["mercado"], [])
        self.assertEqual(data["evolucion"]["puntos"], [])
        self.assertIsNone(data["resumen"]["mayor_variacion"])
        self.assertIsNone(data["resumen"]["divisa_mas_operada"])
        self.registrar("2026-11-19T12:00:00")
        self.assertIsNone(self.datos(divisa="USD")["variaciones"][0]["variacion"])

    def test_parametros_invalidos_400(self):
        for query in ({"periodo": "x"}, {"divisa": "XXX"}, {"divisa": "PYG"}, {"desde": "2026-11-20", "hasta": "2026-11-01"},
                {"periodo": "personalizado"}, {"desde": "2020-01-01", "hasta": "2026-11-01"}, {"hasta": "9999-12-31", "desde": "9999-12-30"}, {"ganancia": "1"}):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.url, query).status_code, 400)
        self.assertEqual(self.client.get(self.url + "?divisa=USD&divisa=EUR").status_code, 400)

    def test_referencia_vencida_no_se_presenta_como_vigente(self):
        self.referencia(vencida=True)
        self.assertIsNone(self.datos()["referencias"]["USD"])

    def test_dashboard_html_sin_500_con_tablas_y_sin_ganancias(self):
        self.registrar("2026-11-19T12:00:00", vigente=True)
        response = self.client.get(self.panel)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/dashboard_analista.html")
        self.assertContains(response, "Mercado actual")
        self.assertContains(response, 'data-analyst-dashboard')
        self.assertNotContains(response, "Ganancia")
        self.assertNotContains(response, "Próximamente")
        self.assertNotContains(response, "dashboard.js")
        self.assertEqual(self.client.get(self.panel, {"periodo": "invalid"}).status_code, 400)

    def test_base_no_disponible_degrada_sin_trazas(self):
        with patch("tasas.dashboard_analista.consultar_dashboard_analista", side_effect=DatabaseError("secreto")):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secreto", response.content.decode())
            page = self.client.get(self.panel)
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "No se pudieron cargar")
