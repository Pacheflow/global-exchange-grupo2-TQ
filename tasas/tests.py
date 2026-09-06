import json
import time
from datetime import timedelta
from decimal import Decimal
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

from .models import (
    ConsultaProveedorTasas,
    TasaComercial,
    TasaReferencia,
)
from .providers import (
    ProveedorTasasError,
    ProveedorTasasHTTP,
    RespuestaTasas,
)
from .services import consultar_tasas_referencia



# HU-17 - Consultar y visualizar tasas



class RespuestaHTTPFalsa:
    def __init__(
        self,
        payload=None,
        *,
        json_error=None,
        http_error=None,
    ):
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
    TASAS_PROVIDER_URL=(
        "https://proveedor.test/latest/__BASE__"
    ),
    TASAS_PROVIDER_NAME="Proveedor de prueba",
    TASAS_PROVIDER_TIMEOUT=3,
)
class ProveedorTasasTests(TestCase):
    def payload_valido(self):
        return {
            "result": "success",
            "base_code": "USD",
            "time_last_update_unix": 1788472800,
            "rates": {
                "EUR": 0.86,
                "PYG": 7360,
            },
        }

    def test_normaliza_una_respuesta_exitosa(self):
        session = Mock()

        session.get.return_value = (
            RespuestaHTTPFalsa(
                self.payload_valido()
            )
        )

        resultado = ProveedorTasasHTTP(
            session=session
        ).obtener(
            "usd",
            ["EUR", "PYG"],
        )

        self.assertEqual(
            resultado.moneda_base,
            "USD",
        )

        self.assertEqual(
            resultado.tasas["EUR"],
            Decimal("0.86"),
        )

        self.assertEqual(
            resultado.fuente,
            "Proveedor de prueba",
        )

        session.get.assert_called_once_with(
            "https://proveedor.test/latest/USD",
            headers={
                "Accept": "application/json"
            },
            timeout=3,
        )

    def test_controla_timeout(self):
        session = Mock()

        session.get.side_effect = requests.Timeout()

        with self.assertRaisesRegex(
            ProveedorTasasError,
            "tiempo de espera",
        ):
            ProveedorTasasHTTP(
                session=session
            ).obtener(
                "USD",
                ["EUR"],
            )

    def test_controla_error_http(self):
        session = Mock()

        session.get.return_value = (
            RespuestaHTTPFalsa(
                self.payload_valido(),
                http_error=requests.HTTPError(
                    "500"
                ),
            )
        )

        with self.assertRaisesRegex(
            ProveedorTasasError,
            "consultar",
        ):
            ProveedorTasasHTTP(
                session=session
            ).obtener(
                "USD",
                ["EUR"],
            )

    def test_rechaza_json_invalido(self):
        session = Mock()

        session.get.return_value = (
            RespuestaHTTPFalsa(
                json_error=ValueError()
            )
        )

        with self.assertRaisesRegex(
            ProveedorTasasError,
            "JSON inválido",
        ):
            ProveedorTasasHTTP(
                session=session
            ).obtener(
                "USD",
                ["EUR"],
            )

    def test_rechaza_respuesta_incompleta(self):
        payload = self.payload_valido()
        payload["rates"] = {
            "EUR": 0.86
        }

        session = Mock()
        session.get.return_value = (
            RespuestaHTTPFalsa(payload)
        )

        with self.assertRaisesRegex(
            ProveedorTasasError,
            "PYG",
        ):
            ProveedorTasasHTTP(
                session=session
            ).obtener(
                "USD",
                ["EUR", "PYG"],
            )

    def test_rechaza_valor_invalido(self):
        valores_invalidos = (
            0,
            -1,
            "no-numero",
            "Infinity",
        )

        for valor in valores_invalidos:
            with self.subTest(valor=valor):
                payload = self.payload_valido()
                payload["rates"]["EUR"] = valor

                session = Mock()
                session.get.return_value = (
                    RespuestaHTTPFalsa(
                        payload
                    )
                )

                with self.assertRaises(
                    ProveedorTasasError
                ):
                    ProveedorTasasHTTP(
                        session=session
                    ).obtener(
                        "USD",
                        ["EUR"],
                    )

    def test_rechaza_fecha_invalida(self):
        payload = self.payload_valido()

        payload["time_last_update_unix"] = (
            "fecha-invalida"
        )

        session = Mock()
        session.get.return_value = (
            RespuestaHTTPFalsa(payload)
        )

        with self.assertRaisesRegex(
            ProveedorTasasError,
            "fecha/hora",
        ):
            ProveedorTasasHTTP(
                session=session
            ).obtener(
                "USD",
                ["EUR"],
            )


@override_settings(
    TASAS_BASE_CURRENCY="USD",
    TASAS_VALIDITY_SECONDS=86400,
)
class ServicioTasasTests(TestCase):
    def setUp(self):
        self.usd = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
        )

        self.eur = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
        )

    def respuesta(self, valor="0.86"):
        return RespuestaTasas(
            moneda_base="USD",
            tasas={
                "EUR": Decimal(valor)
            },
            fuente="Proveedor de prueba",
            fecha_hora=timezone.now(),
            respuesta_original={
                "base_code": "USD",
                "rates": {
                    "EUR": valor
                },
            },
        )

    def test_persiste_respuesta_valida_y_ultima_tasa(
        self,
    ):
        proveedor = Mock()

        proveedor.obtener.return_value = (
            self.respuesta()
        )

        resultado = consultar_tasas_referencia(
            proveedor=proveedor
        )

        self.assertEqual(
            resultado.estado,
            "actualizado",
        )

        self.assertEqual(
            ConsultaProveedorTasas.objects.count(),
            1,
        )

        tasa = TasaReferencia.objects.get()

        self.assertEqual(
            tasa.valor,
            Decimal("0.86"),
        )

        self.assertEqual(
            tasa.moneda_base,
            self.usd,
        )

        self.assertEqual(
            tasa.moneda_cotizada,
            self.eur,
        )

    def test_actualizacion_reemplaza_valor_y_conserva_consultas(
        self,
    ):
        proveedor = Mock()

        proveedor.obtener.side_effect = [
            self.respuesta("0.86"),
            self.respuesta("0.88"),
        ]

        consultar_tasas_referencia(
            proveedor=proveedor
        )

        consultar_tasas_referencia(
            proveedor=proveedor
        )

        self.assertEqual(
            TasaReferencia.objects.count(),
            1,
        )

        self.assertEqual(
            TasaReferencia.objects.get().valor,
            Decimal("0.88"),
        )

        self.assertEqual(
            ConsultaProveedorTasas.objects.count(),
            2,
        )

    def test_fallo_devuelve_ultimo_dato_desactualizado(
        self,
    ):
        proveedor = Mock()

        proveedor.obtener.return_value = (
            self.respuesta()
        )

        consultar_tasas_referencia(
            proveedor=proveedor
        )

        proveedor.obtener.side_effect = (
            ProveedorTasasError(
                "Proveedor sin conexión."
            )
        )

        resultado = consultar_tasas_referencia(
            proveedor=proveedor
        )

        self.assertEqual(
            resultado.estado,
            "desactualizado",
        )

        self.assertEqual(
            len(resultado.tasas),
            1,
        )

        self.assertEqual(
            resultado.mensaje,
            "Proveedor sin conexión.",
        )

    def test_fallo_sin_dato_previo_informa_indisponibilidad(
        self,
    ):
        proveedor = Mock()

        proveedor.obtener.side_effect = (
            ProveedorTasasError(
                "Proveedor sin conexión."
            )
        )

        resultado = consultar_tasas_referencia(
            proveedor=proveedor
        )

        self.assertEqual(
            resultado.estado,
            "indisponible",
        )

        self.assertEqual(
            resultado.tasas,
            [],
        )

    def test_sin_moneda_base_no_consulta_proveedor(
        self,
    ):
        self.usd.estado = "INACTIVA"
        self.usd.save()

        proveedor = Mock()

        resultado = consultar_tasas_referencia(
            proveedor=proveedor
        )

        self.assertEqual(
            resultado.estado,
            "indisponible",
        )

        proveedor.obtener.assert_not_called()

    def test_sin_monedas_cotizadas_devuelve_vacio(
        self,
    ):
        self.eur.estado = "INACTIVA"
        self.eur.save()

        proveedor = Mock()

        resultado = consultar_tasas_referencia(
            proveedor=proveedor
        )

        self.assertEqual(
            resultado.estado,
            "vacio",
        )

        proveedor.obtener.assert_not_called()


class EndpointTasasTests(TestCase):
    def autenticar(self):
        session = self.client.session

        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-1",
            "username": "prueba",
        }
        session[SESSION_ROLES] = [
            "USUARIO"
        ]
        session[SESSION_EXPIRA_EN] = (
            time.time() + 3600
        )

        session.save()

    def test_anonimo_recibe_401(self):
        response = self.client.get(
            "/tasas/"
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    @patch(
        "tasas.views.consultar_tasas_referencia"
    )
    def test_respuesta_exitosa_diferencia_referencia_y_comercial(
        self,
        mock_consultar,
    ):
        self.autenticar()

        usd = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
        )

        eur = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
        )

        consulta = (
            ConsultaProveedorTasas.objects.create(
                fuente="Proveedor",
                moneda_base=usd,
                fecha_hora_fuente=timezone.now(),
                respuesta={},
            )
        )

        tasa = TasaReferencia.objects.create(
            moneda_base=usd,
            moneda_cotizada=eur,
            valor=Decimal("0.86"),
            fuente="Proveedor",
            fecha_hora_fuente=timezone.now(),
            vigente_hasta=(
                timezone.now()
                + timedelta(hours=1)
            ),
            consulta=consulta,
        )

        mock_consultar.return_value.estado = (
            "actualizado"
        )

        mock_consultar.return_value.tasas = [
            tasa
        ]

        mock_consultar.return_value.mensaje = (
            None
        )

        response = self.client.get(
            "/tasas/"
        )

        data = response.json()

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            data["tasas_referencia"][0]["tipo"],
            "REFERENCIA",
        )

        self.assertEqual(
            data["tasas_referencia"][0]["fuente"],
            "Proveedor",
        )

        self.assertFalse(
            data["tasas_referencia"][0][
                "desactualizada"
            ]
        )

        self.assertEqual(
            data["tasas_comerciales"],
            [],
        )

    @patch(
        "tasas.views.consultar_tasas_referencia"
    )
    def test_indisponibilidad_sin_datos_devuelve_503(
        self,
        mock_consultar,
    ):
        self.autenticar()

        mock_consultar.return_value.estado = (
            "indisponible"
        )

        mock_consultar.return_value.tasas = []

        mock_consultar.return_value.mensaje = (
            "Sin datos disponibles."
        )

        response = self.client.get(
            "/tasas/"
        )

        self.assertEqual(
            response.status_code,
            503,
        )

        self.assertEqual(
            response.json()["estado"],
            "indisponible",
        )



# HU-21 - Administrar tasas comerciales



class TasaComercialTests(TestCase):
    """Pruebas de HU-21 - Administrar tasas comerciales."""

    def setUp(self):
        self.usd = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar estadounidense",
            simbolo="$",
            estado="ACTIVA",
        )

        self.pyg = Moneda.objects.create(
            codigo="PYG",
            nombre="Guaraní",
            simbolo="Gs.",
            estado="ACTIVA",
        )

        self.eur = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
            estado="INACTIVA",
        )

        self.url = reverse(
            "tasas:administrar_tasa_comercial"
        )

    def autenticar_con_roles(self, roles):
        """Crea una sesión válida para las pruebas."""
        session = self.client.session

        session[SESSION_AUTENTICADO] = True

        session[SESSION_USUARIO] = {
            "sub": "analista-keycloak-1",
            "username": "analista.prueba",
            "email": "analista@example.com",
        }

        session[SESSION_ROLES] = roles

        session[SESSION_EXPIRA_EN] = (
            time.time() + 3600
        )

        session.save()

    def enviar_tasa(self, datos):
        """Envía una tasa comercial como JSON."""
        return self.client.post(
            self.url,
            data=json.dumps(datos),
            content_type="application/json",
        )

    def test_usuario_anonimo_no_puede_modificar_tasa(
        self,
    ):
        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(
            response.status_code,
            401,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            0,
        )

    def test_usuario_con_rol_incorrecto_recibe_403(
        self,
    ):
        self.autenticar_con_roles(
            ["USUARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            0,
        )

    def test_analista_puede_registrar_tasa(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            1,
        )

        tasa = TasaComercial.objects.get()

        self.assertEqual(
            tasa.version,
            1,
        )

        self.assertTrue(
            tasa.vigente
        )

        self.assertEqual(
            tasa.usuario_id,
            "analista-keycloak-1",
        )

    def test_rechaza_tasa_menor_o_igual_a_cero(
        self,
    ):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "0",
                "venta": "7300",
            }
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            0,
        )

    def test_rechaza_moneda_inactiva(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.eur.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            0,
        )

    def test_no_permite_misma_moneda_en_el_par(
        self,
    ):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.usd.id,
                "compra": "1",
                "venta": "1.1",
            }
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            0,
        )

    def test_primera_tasa_necesita_compra_y_venta(
        self,
    ):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
            }
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            0,
        )

    def test_modificacion_conserva_historico(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        primera = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(
            primera.status_code,
            201,
        )

        segunda = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7250",
            }
        )

        self.assertEqual(
            segunda.status_code,
            201,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            2,
        )

        version_1 = (
            TasaComercial.objects.get(
                version=1
            )
        )

        version_2 = (
            TasaComercial.objects.get(
                version=2
            )
        )

        self.assertFalse(
            version_1.vigente
        )

        self.assertTrue(
            version_2.vigente
        )

        self.assertEqual(
            str(version_1.compra),
            "7200.000000",
        )

        self.assertEqual(
            str(version_2.compra),
            "7250.000000",
        )

        self.assertEqual(
            version_2.venta,
            version_1.venta,
        )

    def test_modificacion_registra_auditoria(self):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        tasa = TasaComercial.objects.get()

        self.assertEqual(
            tasa.usuario_id,
            "analista-keycloak-1",
        )

        self.assertEqual(
            tasa.usuario_username,
            "analista.prueba",
        )

        self.assertIsNotNone(
            tasa.fecha_registro
        )

    def test_validacion_fallida_no_modifica_tasa_vigente(
        self,
    ):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        primera = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(
            primera.status_code,
            201,
        )

        tasa_original = (
            TasaComercial.objects.get(
                vigente=True
            )
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "venta": "0",
            }
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            TasaComercial.objects.count(),
            1,
        )

        tasa_original.refresh_from_db()

        self.assertTrue(
            tasa_original.vigente
        )

        self.assertEqual(
            str(tasa_original.compra),
            "7200.000000",
        )

        self.assertEqual(
            str(tasa_original.venta),
            "7300.000000",
        )

    def test_historial_devuelve_versiones_registradas(
        self,
    ):
        self.autenticar_con_roles(
            ["ANALISTA_CAMBIARIO"]
        )

        self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "venta": "7350",
            }
        )

        response = self.client.get(
            reverse(
                "tasas:historial_tasas_comerciales"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            len(
                response.json()["tasas"]
            ),
            2,
        )