from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda

from .models import ConsultaProveedorTasas, TasaReferencia
from .simulador import simular_conversion


class SimuladorConversionTests(TestCase):
    """Pruebas del simulador de conversión entre monedas.

    Requisito relacionado: RF-09.
    """

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

    def test_simulacion_con_tasa_directa(self):
        """Comprueba la conversión simulada cuando existe una tasa directa entre las monedas.

        Se espera que el resultado use la tasa de referencia vigente del par.
        """
        resultado = simular_conversion(
            moneda_origen_id=self.usd.id,
            moneda_destino_id=self.pyg.id,
            monto="100",
        )

        self.assertEqual(resultado.tasa, Decimal("7000.0000000000"))
        self.assertEqual(resultado.resultado, Decimal("700000.0000000000"))

    def test_simulacion_con_tasa_inversa(self):
        """Comprueba la conversión simulada cuando la tasa disponible está en sentido inverso.

        Se espera que el resultado se calcule con la tasa invertida.
        """
        resultado = simular_conversion(
            moneda_origen_id=self.pyg.id,
            moneda_destino_id=self.usd.id,
            monto="7000",
        )

        self.assertEqual(resultado.resultado, Decimal("1.0000000000"))

    def test_simulacion_con_tasa_cruzada(self):
        """Comprueba la conversión simulada cruzando por la moneda base configurada.

        Se espera que el resultado se calcule a partir de las tasas de ambas monedas
        frente a la base.
        """
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

        self.assertEqual(resultado.resultado, Decimal("0.8750000000"))

    def test_rechaza_monto_cero(self):
        """Comprueba que no se permita simular con un monto cero.

        Se espera que la solicitud sea rechazada (400) indicando el campo monto.
        """
        response = self.client.post(
            self.url, self.payload(monto="0"), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_monto_no_numerico(self):
        """Comprueba que no se permita simular con un monto no numérico.

        Se espera que la solicitud sea rechazada (400) indicando el campo monto.
        """
        response = self.client.post(
            self.url, self.payload(monto="abc"), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_monto_no_finito(self):
        """Comprueba que no se permita simular con un monto no finito.

        Se espera que la solicitud sea rechazada (400) indicando el campo monto.
        """
        response = self.client.post(
            self.url, self.payload(monto="NaN"), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_moneda_inactiva(self):
        """Comprueba que una moneda inactiva no pueda utilizarse en la simulación.

        Se espera que la solicitud sea rechazada (400) indicando la moneda.
        """
        self.pyg.estado = "INACTIVA"
        self.pyg.save(update_fields=["estado"])

        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("moneda_destino", response.json()["detalles"])

    def test_rechaza_misma_moneda(self):
        """Comprueba que no se permita simular una conversión entre la misma moneda.

        Se espera que la solicitud sea rechazada (400) indicando las monedas.
        """
        response = self.client.post(
            self.url,
            self.payload(moneda_destino_id=self.usd.id),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("monedas", response.json()["detalles"])

    def test_rechaza_moneda_inexistente(self):
        """Comprueba que no se permita simular con una moneda inexistente.

        Se espera que la solicitud sea rechazada (400) indicando la moneda de origen.
        """
        response = self.client.post(
            self.url,
            self.payload(moneda_origen_id=999999),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("moneda_origen", response.json()["detalles"])

    def test_informa_si_no_existe_tasa(self):
        """Comprueba que la simulación informe cuando no existe una tasa para el par.

        Se espera que la solicitud sea rechazada (400) indicando el campo tasa.
        """
        response = self.client.post(
            self.url,
            self.payload(moneda_destino_id=self.eur.id),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("tasa", response.json()["detalles"])

    def test_no_utiliza_tasa_desactualizada(self):
        """Comprueba que la simulación no utilice tasas de referencia vencidas.

        Se espera que la solicitud sea rechazada indicando la ausencia de tasa vigente.
        """
        self.tasa.vigente_hasta = timezone.now() - timedelta(minutes=1)
        self.tasa.save(update_fields=["vigente_hasta"])

        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("tasa", response.json()["detalles"])

    def test_simulacion_no_modifica_datos(self):
        """Comprueba que la simulación no registre ni modifique datos.

        Se espera que la consulta devuelva el resultado sin crear consultas ni tasas nuevas.
        """
        cantidad_consultas = ConsultaProveedorTasas.objects.count()
        cantidad_tasas = TasaReferencia.objects.count()

        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ConsultaProveedorTasas.objects.count(), cantidad_consultas)
        self.assertEqual(TasaReferencia.objects.count(), cantidad_tasas)
