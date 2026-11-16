"""HU-18 / IS2TQ2026-22: histórico público, filtros y representación temporal."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda
from .historico import construir_grafico
from .models import TasaComercial


class HistoricoTasasTests(TestCase):
    def setUp(self):
        Moneda.objects.all().delete()
        self.usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
        self.pyg = Moneda.objects.create(codigo="PYG", nombre="Guaraní", simbolo="Gs.")
        self.eur = Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="€", estado="INACTIVA")
        self.api = reverse("tasas:historico")
        self.web = reverse("tasas_web:historico")
        self.filtros = {"moneda_origen_id": self.usd.pk, "moneda_destino_id": self.pyg.pk,
                        "desde": "2026-11-01", "hasta": "2026-11-03"}

    def registrar(self, fecha, compra="7200.1234567890", venta="7300.9876543210", origen=None, destino=None):
        row = TasaComercial.objects.create(
            moneda_origen=origen or self.usd, moneda_destino=destino or self.pyg,
            compra=compra, venta=venta, vigente=False, usuario_id="identidad-interna",
            usuario_username="usuario-privado",
        )
        TasaComercial.objects.filter(pk=row.pk).update(fecha_registro=timezone.make_aware(fecha))
        row.refresh_from_db()
        return row

    def test_visitante_consulta_versiones_anteriores_en_orden_sin_auditoria(self):
        self.registrar(datetime(2026, 11, 3, 12))
        self.registrar(datetime(2026, 11, 1, 12))
        response = self.client.get(self.api, self.filtros)
        self.assertEqual(response.status_code, 200)
        rows = response.json()["registros"]
        self.assertEqual(len(rows), 2)
        self.assertLess(rows[0]["fecha"], rows[1]["fecha"])
        self.assertEqual(rows[0]["compra"], "7200.1234567890")
        self.assertEqual(set(rows[0]), {"fecha", "compra", "venta"})
        self.assertNotIn("identidad-interna", response.content.decode())
        self.assertNotIn("usuario-privado", response.content.decode())

    def test_fechas_inclusivas_en_zona_local_y_aislamiento_de_par(self):
        self.registrar(datetime(2026, 10, 31, 23, 59, 59))
        self.registrar(datetime(2026, 11, 1, 0))
        self.registrar(datetime(2026, 11, 3, 23, 59, 59, 999999))
        self.registrar(datetime(2026, 11, 4, 0))
        self.registrar(datetime(2026, 11, 2, 12), origen=self.eur)
        self.registrar(datetime(2026, 11, 2, 12), origen=self.pyg, destino=self.usd)
        self.assertEqual(len(self.client.get(self.api, self.filtros).json()["registros"]), 2)

    def test_sin_fechas_devuelve_todo_el_historico_del_par(self):
        self.registrar(datetime(2020, 1, 1))
        self.registrar(datetime(2026, 11, 4))
        response = self.client.get(self.api, {"moneda_origen_id": self.usd.pk, "moneda_destino_id": self.pyg.pk})
        self.assertEqual(len(response.json()["registros"]), 2)

    def test_permite_limite_inicial_o_final_independiente(self):
        self.registrar(datetime(2026, 11, 1))
        self.registrar(datetime(2026, 11, 4))
        for quitar in ("desde", "hasta"):
            with self.subTest(quitar=quitar):
                filtros = self.filtros.copy()
                filtros.pop(quitar)
                cantidad = 1 if quitar == "desde" else 2
                self.assertEqual(len(self.client.get(self.api, filtros).json()["registros"]), cantidad)

    def test_moneda_inactiva_conserva_su_historia(self):
        self.registrar(datetime(2026, 11, 2), origen=self.eur)
        filtros = {**self.filtros, "moneda_origen_id": self.eur.pk}
        self.assertEqual(len(self.client.get(self.api, filtros).json()["registros"]), 1)

    def test_rechaza_filtros_invalidos_sin_error_de_servidor(self):
        for cambios in ({"moneda_origen_id": "abc"}, {"moneda_destino_id": 999999},
                        {"moneda_destino_id": self.usd.pk}, {"desde": "2026-02-30"},
                        {"desde": "2026-11-05"}, {"hasta": "9999-12-31"}, {"moneda_origen_id": ""}):
            with self.subTest(cambios=cambios):
                filtros = {**self.filtros, **cambios}
                self.assertEqual(self.client.get(self.api, filtros).status_code, 400)
                response = self.client.get(self.web, filtros)
                self.assertEqual(response.status_code, 400)
                self.assertNotContains(response, '<svg viewBox=', status_code=400)

    def test_api_requiere_seleccion_de_par(self):
        self.assertEqual(self.client.get(self.api).status_code, 400)

    def test_mensaje_sin_datos_y_sin_grafico_inventado(self):
        response = self.client.get(self.web, self.filtros)
        self.assertContains(response, "No hay información disponible")
        self.assertNotContains(response, '<svg viewBox=')
        self.assertEqual(self.client.get(self.api, self.filtros).json()["registros"], [])

    def test_catalogo_vacio_no_produce_errores(self):
        Moneda.objects.all().delete()
        self.assertContains(self.client.get(self.web), "No hay información disponible")

    def test_catalogo_sin_tasas_muestra_estado_vacio(self):
        self.assertContains(self.client.get(self.web), "No hay información disponible")

    def test_grafico_y_tabla_disponibles_para_visitante_y_usuario(self):
        self.registrar(datetime(2026, 11, 2, 12))
        for autenticado in (False, True):
            with self.subTest(autenticado=autenticado):
                if autenticado:
                    session = self.client.session
                    session["kc_user"] = {"sub": "usuario", "given_name": "Persona"}
                    session["roles"] = ["USUARIO"]
                    session.save()
                response = self.client.get(self.web, self.filtros)
                self.assertContains(response, "Evolución de USD/PYG")
                self.assertContains(response, '<svg viewBox=')
                self.assertContains(response, "Compra")
                self.assertContains(response, "Venta")
                self.assertNotContains(response, "usuario-privado")

    def test_consultas_publicas_no_habilitan_el_historial_administrativo(self):
        self.assertEqual(self.client.get(reverse("tasas:historial_tasas_comerciales")).status_code, 401)

    def test_solo_lectura_no_consulta_proveedor_ni_modifica_tasas(self):
        self.registrar(datetime(2026, 11, 2))
        with patch("tasas.views.consultar_tasas_referencia") as proveedor:
            self.client.get(self.api, self.filtros)
            self.client.get(self.web, self.filtros)
            proveedor.assert_not_called()
        self.assertEqual(TasaComercial.objects.count(), 1)
        for url in (self.api, self.web):
            self.assertEqual(self.client.post(url, self.filtros).status_code, 405)

    def test_paginacion_preserva_filtros_y_grafico_completo(self):
        for i in range(26):
            self.registrar(datetime(2026, 11, 2) + timedelta(minutes=i))
        response = self.client.get(self.web, {**self.filtros, "page": 2})
        self.assertEqual(len(response.context["pagina"]), 1)
        self.assertEqual(len(response.context["grafico"]["puntos"]), 26)
        self.assertIn("desde=2026-11-01", response.context["parametros"])
        self.assertNotIn("page=", response.context["parametros"])
        self.assertContains(response, "Página 2 de 2")

    def test_paginacion_inicial_preserva_par_y_fechas_predeterminadas(self):
        hoy = timezone.localdate()
        for i in range(26):
            self.registrar(datetime.combine(hoy, datetime.min.time()) + timedelta(minutes=i))
        response = self.client.get(self.web)
        self.assertIn("moneda_origen_id=", response.context["parametros"])
        self.assertIn("desde=", response.context["parametros"])

    def test_grafico_posiciona_fechas_por_tiempo_no_por_indice(self):
        registros = [self.registrar(datetime(2026, 11, dia)) for dia in (1, 2, 11)]
        grafico = construir_grafico(registros)
        self.assertEqual([p["x"] for p in grafico["puntos"]], ["100.00", "188.00", "980.00"])

    def test_un_solo_registro_y_series_constantes_se_grafican(self):
        row = self.registrar(datetime(2026, 11, 2), compra="0.0000000001", venta="0.0000000001")
        grafico = construir_grafico([row])
        self.assertEqual(grafico["puntos"][0]["x"], "540.00")
        self.assertEqual(grafico["puntos"][0]["compra"], "0.0000000001")
        self.assertEqual(grafico["puntos"][0]["y_compra"], grafico["puntos"][0]["y_venta"])

    def test_registros_simultaneos_tienen_orden_determinista(self):
        self.registrar(datetime(2026, 11, 2), compra="7000")
        self.registrar(datetime(2026, 11, 2), compra="7100")
        rows = self.client.get(self.api, self.filtros).json()["registros"]
        self.assertEqual([Decimal(row["compra"]) for row in rows], [Decimal("7000"), Decimal("7100")])
