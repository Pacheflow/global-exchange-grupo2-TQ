from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda

from .models import ConsultaProveedorTasas, TasaComercial, TasaReferencia
from .providers import ProveedorTasasError, ProveedorTasasHTTP, RespuestaTasas
from .services import consultar_tasas_referencia


class RespuestaHTTPFalsa:
    def __init__(self, payload=None, *, http_error=None):
        self.payload = payload
        self.http_error = http_error

    def raise_for_status(self):
        if self.http_error:
            raise self.http_error

    def json(self):
        return self.payload


@override_settings(
    TASAS_PROVIDER_URL="https://proveedor.test/latest/__BASE__",
    TASAS_PROVIDER_NAME="Proveedor de prueba",
    TASAS_PROVIDER_TIMEOUT=3,
)
class ProveedorTasasTests(TestCase):
    def payload_valido(self):
        return {
            "result": "success",
            "base_code": "USD",
            "time_last_update_unix": 1788472800,
            "rates": {"EUR": 0.86, "PYG": 7360},
        }

    def test_proveedor_normaliza_respuesta_valida(self):
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(self.payload_valido())
        resultado = ProveedorTasasHTTP(session=session).obtener(
            "usd", ["EUR", "PYG"]
        )
        self.assertEqual(resultado.moneda_base, "USD")
        self.assertEqual(resultado.tasas["EUR"], Decimal("0.86"))
        self.assertEqual(resultado.fuente, "Proveedor de prueba")

    def test_proveedor_controla_timeout(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()
        with self.assertRaisesRegex(ProveedorTasasError, "tiempo de espera"):
            ProveedorTasasHTTP(session=session).obtener("USD", ["EUR"])

    def test_proveedor_rechaza_valor_no_positivo(self):
        payload = self.payload_valido()
        payload["rates"]["EUR"] = 0
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(payload)
        with self.assertRaises(ProveedorTasasError):
            ProveedorTasasHTTP(session=session).obtener("USD", ["EUR"])

    def test_proveedor_rechaza_valor_no_numerico(self):
        payload = self.payload_valido()
        payload["rates"]["EUR"] = "no-numero"
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(payload)
        with self.assertRaises(ProveedorTasasError):
            ProveedorTasasHTTP(session=session).obtener("USD", ["EUR"])


@override_settings(TASAS_BASE_CURRENCY="USD", TASAS_VALIDITY_SECONDS=86400)
class ServicioTasasTests(TestCase):
    def setUp(self):
        Moneda.objects.all().delete()
        self.usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
        self.eur = Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="€")

    def respuesta(self, valor="0.86"):
        return RespuestaTasas(
            moneda_base="USD",
            tasas={"EUR": Decimal(valor)},
            fuente="Proveedor de prueba",
            fecha_hora=timezone.now(),
            respuesta_original={"base_code": "USD", "rates": {"EUR": valor}},
        )

    def test_servicio_persiste_primera_tasa_y_consulta(self):
        proveedor = Mock()
        proveedor.obtener.return_value = self.respuesta()
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "actualizado")
        self.assertEqual(ConsultaProveedorTasas.objects.count(), 1)
        tasa = TasaReferencia.objects.get()
        self.assertEqual(tasa.valor, Decimal("0.86"))
        self.assertEqual(tasa.moneda_base, self.usd)
        self.assertEqual(tasa.moneda_cotizada, self.eur)

    def test_servicio_reemplaza_tasa_vigente_y_conserva_consultas(self):
        proveedor = Mock()
        proveedor.obtener.side_effect = [self.respuesta("0.86"), self.respuesta("0.88")]
        consultar_tasas_referencia(proveedor=proveedor)
        consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(TasaReferencia.objects.count(), 1)
        self.assertEqual(TasaReferencia.objects.get().valor, Decimal("0.88"))
        self.assertEqual(ConsultaProveedorTasas.objects.count(), 2)

    def test_servicio_usa_ultimo_dato_como_desactualizado_si_falla(self):
        proveedor = Mock()
        proveedor.obtener.return_value = self.respuesta()
        consultar_tasas_referencia(proveedor=proveedor)
        proveedor.obtener.side_effect = ProveedorTasasError("Proveedor sin conexión.")
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "desactualizado")
        self.assertEqual(len(resultado.tasas), 1)
        self.assertEqual(resultado.mensaje, "Proveedor sin conexión.")

    def test_servicio_sin_cache_informa_indisponibilidad(self):
        proveedor = Mock()
        proveedor.obtener.side_effect = ProveedorTasasError("Proveedor sin conexión.")
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "indisponible")
        self.assertEqual(resultado.tasas, [])


class EndpointTasasTests(TestCase):
    def setUp(self):
        Moneda.objects.all().delete()
        self.url = reverse("tasas:consultar")

    @patch("tasas.views.consultar_tasas_referencia")
    def test_endpoint_publico_diferencia_referencia_y_comercial(self, mock_consultar):
        usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
        eur = Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="€")
        consulta = ConsultaProveedorTasas.objects.create(
            fuente="Proveedor",
            moneda_base=usd,
            fecha_hora_fuente=timezone.now(),
            respuesta={},
        )
        referencia = TasaReferencia.objects.create(
            moneda_base=usd,
            moneda_cotizada=eur,
            valor=Decimal("0.86"),
            fuente="Proveedor",
            fecha_hora_fuente=timezone.now(),
            vigente_hasta=timezone.now() + timedelta(hours=1),
            consulta=consulta,
        )
        TasaComercial.objects.create(
            moneda_origen=usd,
            moneda_destino=eur,
            compra=Decimal("1.234567"),
            venta=Decimal("1.345678"),
            vigente=True,
            version=1,
            usuario_id="analista-actual",
        )
        mock_consultar.return_value.estado = "actualizado"
        mock_consultar.return_value.tasas = [referencia]
        mock_consultar.return_value.mensaje = None
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["tasas_referencia"][0]["tipo"], "REFERENCIA")
        self.assertEqual(data["tasas_comerciales"][0]["tipo"], "COMERCIAL")
        self.assertEqual(data["tasas_comerciales"][0]["par"], "USD/EUR")

    @patch("tasas.views.consultar_tasas_referencia")
    def test_endpoint_sin_datos_devuelve_503(self, mock_consultar):
        mock_consultar.return_value.estado = "indisponible"
        mock_consultar.return_value.tasas = []
        mock_consultar.return_value.mensaje = "Sin datos disponibles."
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["estado"], "indisponible")
