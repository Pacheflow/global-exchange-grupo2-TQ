from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda

from .models import ConsultaProveedorTasas, TasaReferencia
from .simulador import simular_conversion


class SimuladorConversionTests(TestCase):
    def setUp(self):
        Moneda.objects.all().delete()
        self.usd = Moneda.objects.create(
            codigo="USD", nombre="Dólar estadounidense", simbolo="$", estado="ACTIVA"
        )
        self.pyg = Moneda.objects.create(
            codigo="PYG", nombre="Guaraní", simbolo="Gs.", estado="ACTIVA"
        )
        self.eur = Moneda.objects.create(
            codigo="EUR", nombre="Euro", simbolo="€", estado="ACTIVA"
        )
        self.fecha = timezone.now()
        self.consulta = ConsultaProveedorTasas.objects.create(
            fuente="Proveedor de prueba",
            moneda_base=self.usd,
            fecha_hora_fuente=self.fecha,
            respuesta={"PYG": "7000"},
        )
        self.tasa = TasaReferencia.objects.create(
            moneda_base=self.usd,
            moneda_cotizada=self.pyg,
            valor=Decimal("7000"),
            fuente="Proveedor de prueba",
            fecha_hora_fuente=self.fecha,
            vigente_hasta=self.fecha + timedelta(hours=1),
            consulta=self.consulta,
        )
        self.url = reverse("tasas:simular_conversion")

    def payload(self, **overrides):
        data = {
            "moneda_origen_id": self.usd.id,
            "moneda_destino_id": self.pyg.id,
            "monto": "100",
        }
        data.update(overrides)
        return data

    def test_simulacion_valida_con_tasa_directa(self):
        resultado = simular_conversion(
            moneda_origen_id=self.usd.id,
            moneda_destino_id=self.pyg.id,
            monto="100",
        )
        self.assertEqual(resultado.moneda_origen, self.usd)
        self.assertEqual(resultado.moneda_destino, self.pyg)
        self.assertEqual(resultado.monto, Decimal("100"))
        self.assertEqual(resultado.tasa, Decimal("7000.0000000000"))
        self.assertEqual(resultado.resultado, Decimal("700000.0000000000"))
        self.assertEqual(resultado.tipo_tasa, "REFERENCIA")

    def test_simulacion_valida_con_tasa_inversa(self):
        resultado = simular_conversion(
            moneda_origen_id=self.pyg.id,
            moneda_destino_id=self.usd.id,
            monto="7000",
        )
        self.assertEqual(resultado.resultado, Decimal("1.0000000000"))
        self.assertEqual(resultado.tipo_tasa, "REFERENCIA")

    def test_simulacion_valida_con_tasa_cruzada(self):
        TasaReferencia.objects.create(
            moneda_base=self.usd,
            moneda_cotizada=self.eur,
            valor=Decimal("0.875"),
            fuente="Proveedor de prueba",
            fecha_hora_fuente=self.fecha,
            vigente_hasta=self.fecha + timedelta(hours=1),
            consulta=self.consulta,
        )

        resultado = simular_conversion(
            moneda_origen_id=self.pyg.id,
            moneda_destino_id=self.eur.id,
            monto="7000",
        )

        self.assertEqual(resultado.tasa, Decimal("0.000125"))
        self.assertEqual(resultado.resultado, Decimal("0.8750000000"))

    def test_rechaza_monto_cero(self):
        response = self.client.post(
            self.url, self.payload(monto="0"), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_monto_negativo(self):
        response = self.client.post(
            self.url, self.payload(monto="-50"), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_monto_no_numerico(self):
        response = self.client.post(
            self.url, self.payload(monto="abc"), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_moneda_inactiva(self):
        self.pyg.estado = "INACTIVA"
        self.pyg.save()
        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("moneda_destino", response.json()["detalles"])

    def test_rechaza_misma_moneda(self):
        response = self.client.post(
            self.url,
            self.payload(moneda_destino_id=self.usd.id),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monedas", response.json()["detalles"])

    def test_informa_si_no_existe_tasa(self):
        response = self.client.post(
            self.url,
            self.payload(moneda_destino_id=self.eur.id),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tasa", response.json()["detalles"])

    def test_no_utiliza_tasa_desactualizada(self):
        self.tasa.vigente_hasta = timezone.now() - timedelta(minutes=1)
        self.tasa.save()
        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tasa", response.json()["detalles"])

    def test_simulador_es_publico(self):
        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        datos = response.json()
        self.assertEqual(datos["moneda_origen"], "USD")
        self.assertEqual(datos["moneda_destino"], "PYG")
        self.assertEqual(datos["tipo_tasa"], "REFERENCIA")
        self.assertEqual(datos["resultado"], "700000.0000000000")

    def test_simulacion_no_modifica_datos(self):
        cantidad_consultas = ConsultaProveedorTasas.objects.count()
        cantidad_tasas = TasaReferencia.objects.count()
        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ConsultaProveedorTasas.objects.count(), cantidad_consultas
        )
        self.assertEqual(TasaReferencia.objects.count(), cantidad_tasas)
