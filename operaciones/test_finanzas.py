"""Regresión del contrato financiero HU-S6-02 (sin servicios externos)."""
from datetime import date, datetime
from decimal import Decimal
import time
import uuid
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import CategoriaCliente, Cliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from tasas.models import TasaComercial
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)
from .finanzas import importes_pyg, reporte_financiero
from .models import Transaccion


@override_settings(TIME_ZONE="America/Asuncion")
class FinanzasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pyg, _ = Moneda.objects.get_or_create(codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"})
        cls.usd, _ = Moneda.objects.get_or_create(codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"})
        cls.eur, _ = Moneda.objects.get_or_create(codigo="EUR", defaults={"nombre": "Euro", "simbolo": "€"})
        categoria, _ = CategoriaCliente.objects.get_or_create(nombre="Finanzas")
        cls.cliente = Cliente.objects.create(nombre_razon_social="Finanzas", tipo_persona="FISICA",
                                             documento="S6-01", categoria=categoria)
        cls.metodo = MetodoPago.objects.create(nombre="Finanzas", naturaleza="ELECTRONICO")
        cls.tasa = TasaComercial.objects.create(moneda_origen=cls.usd, moneda_destino=cls.pyg,
                                                compra=7000, venta=7100, usuario_id="admin")

    def operacion(self, fecha="2026-10-01T12:00:00", **cambios):
        datos = dict(clave_idempotencia=str(uuid.uuid4()), cliente=self.cliente,
                     creado_por_keycloak_id="admin", tipo="COMPRA", moneda_origen=self.usd,
                     moneda_destino=self.pyg, monto_origen=Decimal("100"),
                     monto_destino=Decimal("693000"), tasa_comercial=self.tasa,
                     tasa_aplicada=Decimal("7000"), porcentaje_comision=Decimal("1"),
                     importe_comision=Decimal("7000"), metodo_pago=self.metodo,
                     metodo_pago_nombre="Finanzas", estado="COMPLETADA")
        datos.update(cambios)
        op = Transaccion.objects.create(**datos)
        instante = datetime.fromisoformat(fecha).replace(tzinfo=ZoneInfo("America/Asuncion"))
        Transaccion.objects.filter(pk=op.pk).update(fecha_creacion=instante)
        op.refresh_from_db()
        return op

    def reporte(self, **cambios):
        datos = dict(desde=date(2026, 10, 1), hasta=date(2026, 10, 3))
        datos.update(cambios)
        return reporte_financiero(**datos)

    def login(self, rol="ADMINISTRADOR"):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = int(time.time()) + 600
        session[SESSION_ROLES] = [rol]
        session[SESSION_USUARIO] = {"sub": "admin", "username": "admin"}
        session.save()

    def test_comision_destino_pyg_y_volumen_una_sola_pata(self):
        self.operacion()
        total = self.reporte()["totales"]
        self.assertEqual(total["ganancia"], "7000.000000")
        self.assertEqual(total["comisiones"], total["ganancia"])
        self.assertEqual(total["volumen"], "700000.000000")
        self.assertEqual((total["compras"], total["ventas"]), (1, 0))

    def test_comision_origen_pyg_se_convierte_con_tasa_aplicada(self):
        op = self.operacion(tipo="VENTA", moneda_origen=self.pyg, moneda_destino=self.usd,
                            monto_origen=Decimal("700000"), monto_destino=Decimal("99"),
                            tasa_aplicada=Decimal("0.00014"), importe_comision=Decimal("1"))
        volumen, comision = importes_pyg(op)
        self.assertEqual(volumen, Decimal("700000"))
        self.assertAlmostEqual(comision, Decimal("7142.857142857142857"), places=12)
        self.assertEqual(self.reporte()["totales"]["ventas"], 1)

    def test_no_revaloriza_con_tasas_actuales(self):
        self.operacion()
        antes = self.reporte()
        TasaComercial.objects.filter(pk=self.tasa.pk).update(compra=1, venta=2)
        self.assertEqual(antes, self.reporte())

    def test_pares_sin_pyg_se_informan_sin_sumarlos(self):
        self.operacion(moneda_destino=self.eur)
        self.operacion()
        reporte = self.reporte()
        self.assertEqual(reporte["totales"]["operaciones"], 2)
        self.assertEqual(reporte["totales"]["operaciones_convertidas"], 1)
        self.assertEqual(reporte["totales"]["ganancia"], "7000.000000")
        self.assertFalse(reporte["totales"]["completo"])
        self.assertEqual(reporte["sin_conversion"], [{"par": "USD/EUR", "operaciones": 1}])
        self.assertTrue(reporte["advertencias"])

    def test_excluye_pendientes_canceladas_y_fuera_del_rango(self):
        self.operacion(estado="PENDIENTE")
        self.operacion(estado="CANCELADA", cancelado_por_keycloak_id="a", cancelado_por_username="a",
                        cancelado_en=datetime(2026, 10, 1, tzinfo=ZoneInfo("UTC")), motivo_cancelacion="Prueba")
        self.operacion(fecha="2026-09-30T23:59:59")
        self.operacion(fecha="2026-10-04T00:00:00")
        self.assertEqual(self.reporte()["totales"]["operaciones"], 0)

    def test_limites_locales_inclusivos_y_dias_vacios(self):
        self.operacion(fecha="2026-10-01T00:00:00")
        self.operacion(fecha="2026-10-03T23:59:59")
        reporte = self.reporte()
        self.assertEqual(reporte["totales"]["operaciones"], 2)
        self.assertEqual([p["operaciones"] for p in reporte["periodos"]], [1, 0, 1])

    def test_semana_empieza_lunes_y_conserva_rango_parcial(self):
        self.operacion()
        reporte = self.reporte(agrupacion="semana")
        self.assertEqual(reporte["periodos"][0]["inicio"], "2026-09-28")
        self.assertEqual(reporte["periodos"][0]["desde"], "2026-10-01")
        self.assertEqual(reporte["periodos"][0]["hasta"], "2026-10-03")

    def test_mes_y_cambio_de_anio(self):
        reporte = self.reporte(desde=date(2026, 12, 31), hasta=date(2027, 1, 1), agrupacion="mes")
        self.assertEqual([p["inicio"] for p in reporte["periodos"]], ["2026-12-01", "2027-01-01"])

    def test_redondea_solo_al_final(self):
        for _ in range(3):
            self.operacion(moneda_origen=self.pyg, moneda_destino=self.usd,
                            tasa_aplicada=Decimal("3"), importe_comision=Decimal("1"))
        self.assertEqual(self.reporte()["totales"]["ganancia"], "1.000000")

    def test_reporte_vacio(self):
        reporte = self.reporte()
        self.assertTrue(reporte["totales"]["completo"])
        self.assertEqual(reporte["totales"]["ganancia"], "0.000000")
        self.assertEqual(len(reporte["periodos"]), 3)

    def test_valida_rango_y_agrupacion(self):
        for datos in ({"agrupacion": "anio"}, {"hasta": date(2026, 9, 30)}, {"hasta": date(2027, 10, 2)}):
            with self.subTest(datos=datos), self.assertRaises(ValidationError):
                self.reporte(**datos)

    def test_api_autenticacion_y_permisos(self):
        url = reverse("operaciones:metricas_financieras")
        self.assertEqual(self.client.get(url).status_code, 401)
        for rol in ("CLIENTE", "CAJERO", "OPERADOR"):
            self.login(rol)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.login()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_api_contrato_y_errores(self):
        self.login()
        url = reverse("operaciones:metricas_financieras")
        self.operacion()
        response = self.client.get(url, {"desde": "2026-10-01", "hasta": "2026-10-03"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.reporte())
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for query in ("desde=2026-02-30", "desde=20261001", "agrupacion=anio", "cliente=1",
                      "desde=2026-10-01&desde=2026-10-02", "hasta=9999-12-31", "desde="):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(url + "?" + query).status_code, 400)

    def test_consulta_no_crece_por_operacion(self):
        for _ in range(5):
            self.operacion()
        with self.assertNumQueries(1):
            self.reporte()
