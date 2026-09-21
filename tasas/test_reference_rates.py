from datetime import timedelta
from decimal import Decimal
import time
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import ConsultaProveedorTasas, TasaComercial, TasaReferencia
from .providers import ProveedorTasasError, ProveedorTasasHTTP, RespuestaTasas
from .services import consultar_tasas_referencia


class RespuestaHTTPFalsa:
    def __init__(self, payload=None, *, json_error=None, http_error=None):
        self.payload = payload
        self.json_error = json_error
        self.http_error = http_error

    def raise_for_status(self):
        if self.http_error:
            raise self.http_error

    def json(self):
        if self.json_error:
            raise self.json_error
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

    def test_normaliza_una_respuesta_exitosa(self):
        """Normaliza una respuesta exitosa del proveedor externo.

        Escenario: sesión HTTP simulada (``Mock``) que devuelve un payload
        válido desde ``RespuestaHTTPFalsa``.

        Datos relevantes: ``obtener("usd", ["EUR", "PYG"])``; payload con
        ``base_code="USD"``, ``result="success"`` y tasas
        ``{"EUR": 0.86, "PYG": 7360}``.

        Resultado esperado: ``RespuestaTasas`` con ``moneda_base="USD"``,
        ``tasas["EUR"] == Decimal("0.86")``, ``fuente="Proveedor de
        prueba"`` y la sesión consultada con la URL resuelta
        (``https://proveedor.test/latest/USD``), encabezado ``Accept`` y
        ``timeout=3``.

        Assertions relevantes: ``assertEqual(resultado.moneda_base,
        "USD")``, ``assertEqual(resultado.tasas["EUR"], ...)``,
        ``assertEqual(resultado.fuente, ...)`` y ``session.get.
        assert_called_once_with(...)``.
        """
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(self.payload_valido())

        resultado = ProveedorTasasHTTP(session=session).obtener(
            "usd", ["EUR", "PYG"]
        )

        self.assertEqual(resultado.moneda_base, "USD")
        self.assertEqual(resultado.tasas["EUR"], Decimal("0.86"))
        self.assertEqual(resultado.fuente, "Proveedor de prueba")
        session.get.assert_called_once_with(
            "https://proveedor.test/latest/USD",
            headers={"Accept": "application/json"},
            timeout=3,
        )

    def test_controla_timeout(self):
        """Traduce el timeout del proveedor a un error controlado.

        Escenario: sesión HTTP simulada cuyo ``get`` lanza
        ``requests.Timeout()``.

        Datos relevantes: ``obtener("USD", ["EUR"])``.

        Resultado esperado: se eleva ``ProveedorTasasError`` cuyo mensaje
        contiene ``"tiempo de espera"``.

        Assertion relevante: ``assertRaisesRegex(ProveedorTasasError,
        "tiempo de espera")``.
        """
        session = Mock()
        session.get.side_effect = requests.Timeout()
        with self.assertRaisesRegex(ProveedorTasasError, "tiempo de espera"):
            ProveedorTasasHTTP(session=session).obtener("USD", ["EUR"])

    def test_controla_error_http(self):
        """Traduce los errores HTTP del proveedor a un error controlado.

        Escenario: sesión HTTP simulada que responde con
        ``requests.HTTPError("500")`` vía ``RespuestaHTTPFalsa``.

        Datos relevantes: ``obtener("USD", ["EUR"])``.

        Resultado esperado: se eleva ``ProveedorTasasError`` cuyo mensaje
        contiene ``"consultar"``.

        Assertion relevante: ``assertRaisesRegex(ProveedorTasasError,
        "consultar")``.
        """
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(
            self.payload_valido(), http_error=requests.HTTPError("500")
        )
        with self.assertRaisesRegex(ProveedorTasasError, "consultar"):
            ProveedorTasasHTTP(session=session).obtener("USD", ["EUR"])

    def test_rechaza_json_invalido(self):
        """Rechaza un cuerpo que no es JSON válido del proveedor.

        Escenario: sesión HTTP simulada cuyo ``json()`` lanza
        ``ValueError`` (a través de ``RespuestaHTTPFalsa``).

        Datos relevantes: ``obtener("USD", ["EUR"])``.

        Resultado esperado: se eleva ``ProveedorTasasError`` cuyo mensaje
        contiene ``"JSON inválido"``.

        Assertion relevante: ``assertRaisesRegex(ProveedorTasasError,
        "JSON inválido")``.
        """
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(json_error=ValueError())
        with self.assertRaisesRegex(ProveedorTasasError, "JSON inválido"):
            ProveedorTasasHTTP(session=session).obtener("USD", ["EUR"])

    def test_rechaza_respuesta_incompleta(self):
        """Rechaza una respuesta que no incluye todas las monedas pedidas.

        Escenario: payload con ``rates`` que omite la moneda ``PYG``.

        Datos relevantes: ``obtener("USD", ["EUR", "PYG"])`` con
        ``rates={"EUR": 0.86}`` (solicita ``PYG``).

        Resultado esperado: se eleva ``ProveedorTasasError`` cuyo mensaje
        menciona la moneda faltante (``"PYG"``).

        Assertion relevante: ``assertRaisesRegex(ProveedorTasasError,
        "PYG")``.
        """
        payload = self.payload_valido()
        payload["rates"] = {"EUR": 0.86}
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(payload)
        with self.assertRaisesRegex(ProveedorTasasError, "PYG"):
            ProveedorTasasHTTP(session=session).obtener("USD", ["EUR", "PYG"])

    def test_rechaza_valor_cero_negativo_no_numerico_o_infinito(self):
        """Rechaza tasas con valor cero, negativo, no numérico o infinito.

        Escenario: se itera con ``subTest`` sobre los valores ``0``,
        ``-1``, ``"no-numero"`` y ``"Infinity"``.

        Datos relevantes: para cada valor se reemplaza la tasa de ``EUR``
        en un payload válido y se invoca ``obtener("USD", ["EUR"])``.

        Resultado esperado: ``ProveedorTasasError`` en cada caso.

        Assertion relevante: ``assertRaises(ProveedorTasasError)`` dentro de
        cada ``subTest``.
        """
        for valor in (0, -1, "no-numero", "Infinity"):
            with self.subTest(valor=valor):
                payload = self.payload_valido()
                payload["rates"]["EUR"] = valor
                session = Mock()
                session.get.return_value = RespuestaHTTPFalsa(payload)
                with self.assertRaises(ProveedorTasasError):
                    ProveedorTasasHTTP(session=session).obtener("USD", ["EUR"])

    def test_rechaza_fecha_invalida(self):
        """Rechaza una fecha/hora de fuente inválida en el payload.

        Escenario: payload cuyo ``time_last_update_unix`` no es un número
        entero convertible a timestamp.

        Datos relevantes: ``time_last_update_unix="fecha-invalida"``;
        ``obtener("USD", ["EUR"])``.

        Resultado esperado: se eleva ``ProveedorTasasError`` cuyo mensaje
        contiene ``"fecha/hora"``.

        Assertion relevante: ``assertRaisesRegex(ProveedorTasasError,
        "fecha/hora")``.
        """
        payload = self.payload_valido()
        payload["time_last_update_unix"] = "fecha-invalida"
        session = Mock()
        session.get.return_value = RespuestaHTTPFalsa(payload)
        with self.assertRaisesRegex(ProveedorTasasError, "fecha/hora"):
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

    def test_persiste_respuesta_valida_y_ultima_tasa(self):
        """Persiste la respuesta válida y la última tasa de referencia.

        Escenario: ``consultar_tasas_referencia`` con un proveedor mockeado
        que devuelve una ``RespuestaTasas`` válida.

        Datos relevantes: base ``USD``, cotizada ``EUR`` con
        ``valor="0.86"`` (``TASAS_BASE_CURRENCY="USD"``).

        Resultado esperado: ``estado="actualizado"``, una única
        ``ConsultaProveedorTasas`` persistida y una ``TasaReferencia`` con
        ``valor=Decimal("0.86")`` ligada a ``USD``/``EUR``.

        Assertions relevantes: ``assertEqual(resultado.estado,
        "actualizado")``, ``assertEqual(ConsultaProveedorTasas.objects.
        count(), 1)`` y comprobación de la tasa persistida (``valor``,
        ``moneda_base``, ``moneda_cotizada``).
        """
        proveedor = Mock()
        proveedor.obtener.return_value = self.respuesta()
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "actualizado")
        self.assertEqual(ConsultaProveedorTasas.objects.count(), 1)
        tasa = TasaReferencia.objects.get()
        self.assertEqual(tasa.valor, Decimal("0.86"))
        self.assertEqual(tasa.moneda_base, self.usd)
        self.assertEqual(tasa.moneda_cotizada, self.eur)

    def test_actualizacion_reemplaza_valor_vigente_y_conserva_consultas(self):
        """Una actualización reemplaza el valor vigente y conserva consultas.

        Escenario: el proveedor mockeado devuelve primero ``0.86`` y luego
        ``0.88`` en dos llamadas a ``consultar_tasas_referencia``.

        Datos relevantes: ``proveedor.obtener.side_effect`` con dos
        respuestas para el par ``USD/EUR``.

        Resultado esperado: se mantiene una única ``TasaReferencia`` con
        ``valor=Decimal("0.88")`` y se acumulan dos
        ``ConsultaProveedorTasas`` (trazabilidad conservada).

        Assertions relevantes: ``assertEqual(TasaReferencia.objects.count(),
        1)``, ``assertEqual(TasaReferencia.objects.get().valor, ...)`` y
        ``assertEqual(ConsultaProveedorTasas.objects.count(), 2)``.
        """
        proveedor = Mock()
        proveedor.obtener.side_effect = [self.respuesta("0.86"), self.respuesta("0.88")]
        consultar_tasas_referencia(proveedor=proveedor)
        consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(TasaReferencia.objects.count(), 1)
        self.assertEqual(TasaReferencia.objects.get().valor, Decimal("0.88"))
        self.assertEqual(ConsultaProveedorTasas.objects.count(), 2)

    def test_fallo_devuelve_ultimo_dato_como_desactualizado(self):
        """Un fallo del proveedor devuelve el último dato como desactualizado.

        Escenario: primero se consulta con éxito (``0.86``) y luego el
        proveedor mockeado lanza ``ProveedorTasasError``.

        Datos relevantes: ``proveedor.obtener.side_effect =
        ProveedorTasasError("Proveedor sin conexión.")``.

        Resultado esperado: ``estado="desactualizado"``, se conserva una
        tasa guardada y ``mensaje="Proveedor sin conexión."``.

        Assertions relevantes: ``assertEqual(resultado.estado,
        "desactualizado")``, ``assertEqual(len(resultado.tasas), 1)`` y
        ``assertEqual(resultado.mensaje, ...)``.
        """
        proveedor = Mock()
        proveedor.obtener.return_value = self.respuesta()
        consultar_tasas_referencia(proveedor=proveedor)
        proveedor.obtener.side_effect = ProveedorTasasError("Proveedor sin conexión.")
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "desactualizado")
        self.assertEqual(len(resultado.tasas), 1)
        self.assertEqual(resultado.mensaje, "Proveedor sin conexión.")

    def test_fallo_sin_dato_previo_informa_indisponibilidad(self):
        """Sin dato previo, un fallo informa indisponibilidad.

        Escenario: el proveedor mockeado lanza ``ProveedorTasasError`` en
        la primera consulta (no hay tasas guardadas).

        Datos relevantes: ``proveedor.obtener.side_effect =
        ProveedorTasasError("Proveedor sin conexión.")``.

        Resultado esperado: ``estado="indisponible"`` y ``tasas`` vacía.

        Assertions relevantes: ``assertEqual(resultado.estado,
        "indisponible")`` y ``assertEqual(resultado.tasas, [])``.
        """
        proveedor = Mock()
        proveedor.obtener.side_effect = ProveedorTasasError("Proveedor sin conexión.")
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "indisponible")
        self.assertEqual(resultado.tasas, [])

    def test_sin_moneda_base_no_consulta_proveedor(self):
        """Sin moneda base activa no se consulta al proveedor.

        Escenario: la moneda base ``USD`` se desactiva antes de consultar.

        Datos relevantes: ``self.usd.estado = "INACTIVA"`` (y
        ``self.usd.save()``); proveedor mockeado.

        Resultado esperado: ``estado="indisponible"`` y ``proveedor.obtener``
        nunca se invoca.

        Assertions relevantes: ``assertEqual(resultado.estado,
        "indisponible")`` y ``proveedor.obtener.assert_not_called()``.
        """
        self.usd.estado = "INACTIVA"
        self.usd.save()
        proveedor = Mock()
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "indisponible")
        proveedor.obtener.assert_not_called()

    def test_sin_monedas_cotizadas_devuelve_estado_vacio(self):
        """Sin monedas cotizadas activas se devuelve estado vacío.

        Escenario: la única moneda cotizada ``EUR`` se desactiva antes de
        consultar.

        Datos relevantes: ``self.eur.estado = "INACTIVA"`` (y
        ``self.eur.save()``); proveedor mockeado.

        Resultado esperado: ``estado="vacio"`` y ``proveedor.obtener`` nunca
        se invoca.

        Assertions relevantes: ``assertEqual(resultado.estado, "vacio")`` y
        ``proveedor.obtener.assert_not_called()``.
        """
        self.eur.estado = "INACTIVA"
        self.eur.save()
        proveedor = Mock()
        resultado = consultar_tasas_referencia(proveedor=proveedor)
        self.assertEqual(resultado.estado, "vacio")
        proveedor.obtener.assert_not_called()


class EndpointTasasTests(TestCase):
    def setUp(self):
        Moneda.objects.all().delete()
        self.url = reverse("tasas:consultar")

    def autenticar(self):
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {"sub": "usuario-1", "username": "prueba"}
        session[SESSION_ROLES] = ["USUARIO"]
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session.save()

    @patch("tasas.views.consultar_tasas_referencia")
    def test_consulta_de_referencia_es_publica(self, mock_consultar):
        """La consulta de tasas de referencia es pública (sin autenticación).

        Escenario: ``GET`` a ``tasas:consultar`` sin sesión OIDC, con el
        servicio de referencia mockeado devolviendo estado ``"vacio"``.

        Datos relevantes: estado ``"vacio"``, sin tasas y mensaje
        ``"No hay monedas activas configuradas."``.

        Resultado esperado: ``200`` y ``estado == "vacio"`` en la respuesta
        JSON.

        Assertions relevantes: ``assertEqual(response.status_code, 200)`` y
        ``assertEqual(response.json()["estado"], "vacio")``.
        """
        mock_consultar.return_value.estado = "vacio"
        mock_consultar.return_value.tasas = []
        mock_consultar.return_value.mensaje = "No hay monedas activas configuradas."
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["estado"], "vacio")

    @patch("tasas.views.consultar_tasas_referencia")
    def test_respuesta_exitosa_diferencia_referencia_y_comercial(self, mock_consultar):
        """Una respuesta exitosa diferencia tasas de referencia y comerciales.

        Escenario: se crean una ``TasaReferencia`` vigente y dos
        ``TasaComercial`` (histórica ``vigente=False`` y vigente
        ``vigente=True``), con el servicio de referencia mockeado
        (``estado="actualizado"``).

        Datos relevantes: `GET` a ``tasas:consultar``; tasas de referencia
        ``USD/EUR`` y comerciales del mismo par con ``version=2``.

        Resultado esperado: ``200``, una tasa de referencia con
        ``tipo="REFERENCIA"`` y ``desactualizada=False``, y una única tasa
        comercial (``id`` de la vigente) con ``tipo="COMERCIAL"``,
        ``par="USD/EUR"``, ``compra="1.234567"``, ``venta="1.345678"``,
        ``vigente=True`` y ``version=2``.

        Assertions relevantes: ``assertEqual`` sobre status, ``tipo``,
        ``fuente``, ``desactualizada``, ``len(tasas_comerciales)``, ``id``,
        ``par``, ``compra``, ``venta``, ``vigente`` y ``version``.
        """
        self.autenticar()
        usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
        eur = Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="€")
        consulta = ConsultaProveedorTasas.objects.create(
            fuente="Proveedor",
            moneda_base=usd,
            fecha_hora_fuente=timezone.now(),
            respuesta={},
        )
        tasa = TasaReferencia.objects.create(
            moneda_base=usd,
            moneda_cotizada=eur,
            valor=Decimal("0.86"),
            fuente="Proveedor",
            fecha_hora_fuente=timezone.now(),
            vigente_hasta=timezone.now() + timedelta(hours=1),
            consulta=consulta,
        )
        historica = TasaComercial.objects.create(
            moneda_origen=usd,
            moneda_destino=eur,
            compra=Decimal("1.111111"),
            venta=Decimal("1.222222"),
            vigente=False,
            version=1,
            usuario_id="analista-anterior",
        )
        vigente = TasaComercial.objects.create(
            moneda_origen=usd,
            moneda_destino=eur,
            compra=Decimal("1.234567"),
            venta=Decimal("1.345678"),
            vigente=True,
            version=2,
            usuario_id="analista-actual",
        )
        mock_consultar.return_value.estado = "actualizado"
        mock_consultar.return_value.tasas = [tasa]
        mock_consultar.return_value.mensaje = None

        response = self.client.get(self.url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["tasas_referencia"][0]["tipo"], "REFERENCIA")
        self.assertEqual(data["tasas_referencia"][0]["fuente"], "Proveedor")
        self.assertFalse(data["tasas_referencia"][0]["desactualizada"])
        self.assertEqual(len(data["tasas_comerciales"]), 1)
        comercial = data["tasas_comerciales"][0]
        self.assertEqual(comercial["id"], vigente.id)
        self.assertNotEqual(comercial["id"], historica.id)
        self.assertEqual(comercial["tipo"], "COMERCIAL")
        self.assertEqual(comercial["par"], "USD/EUR")
        self.assertEqual(comercial["compra"], "1.234567")
        self.assertEqual(comercial["venta"], "1.345678")
        self.assertTrue(comercial["vigente"])
        self.assertEqual(comercial["version"], 2)
        self.assertEqual(comercial["fecha_hora"], vigente.fecha_registro.isoformat())

    @patch("tasas.views.consultar_tasas_referencia")
    def test_indisponibilidad_sin_datos_devuelve_503(self, mock_consultar):
        """La indisponibilidad sin datos se responde con ``503``.

        Escenario: sesión autenticada y ``GET`` a ``tasas:consultar`` con el
        servicio de referencia mockeado en estado ``"indisponible"``.

        Datos relevantes: estado ``"indisponible"``, sin tasas y mensaje
        ``"Sin datos disponibles."``.

        Resultado esperado: ``response.status_code == 503`` y
        ``estado == "indisponible"`` en la respuesta JSON.

        Assertions relevantes: ``assertEqual(response.status_code, 503)`` y
        ``assertEqual(response.json()["estado"], "indisponible")``.
        """
        self.autenticar()
        mock_consultar.return_value.estado = "indisponible"
        mock_consultar.return_value.tasas = []
        mock_consultar.return_value.mensaje = "Sin datos disponibles."
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["estado"], "indisponible")
