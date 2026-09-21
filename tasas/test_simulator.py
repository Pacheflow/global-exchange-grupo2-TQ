import time
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

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
        """Simula la conversión usando la tasa directa del par.

        Escenario: ``simular_conversion`` para el par ``USD/PYG`` con una
        tasa de referencia vigente directa (base ``USD``).

        Datos relevantes: ``monto="100"``, tasa ``PYG`` de ``7000``
        (``self.tasa`` vigente 1 hora).

        Resultado esperado: monedas de origen/destino ``USD`` y ``PYG``,
        ``monto == Decimal("100")``, ``tasa == Decimal("7000.0000000000")``,
        ``resultado == Decimal("700000.0000000000")`` y ``tipo_tasa ==
        "REFERENCIA"``.

        Assertions relevantes: ``assertEqual`` sobre ``moneda_origen``,
        ``moneda_destino``, ``monto``, ``tasa``, ``resultado`` y
        ``tipo_tasa``.
        """
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
        """Simula la conversión usando la tasa inversa del par.

        Escenario: ``simular_conversion`` para el par ``PYG/USD`` cuando no
        existe la tasa directa sino la inversa (``USD/PYG``).

        Datos relevantes: ``monto="7000"``, cotizada ``USD``; usa
        ``1 / 7000`` con ``self.tasa`` vigente.

        Resultado esperado: ``resultado == Decimal("1.0000000000")`` y
        ``tipo_tasa == "REFERENCIA"``.

        Assertions relevantes: ``assertEqual(resultado.resultado, ...)`` y
        ``assertEqual(resultado.tipo_tasa, "REFERENCIA")``.
        """
        resultado = simular_conversion(
            moneda_origen_id=self.pyg.id,
            moneda_destino_id=self.usd.id,
            monto="7000",
        )
        self.assertEqual(resultado.resultado, Decimal("1.0000000000"))
        self.assertEqual(resultado.tipo_tasa, "REFERENCIA")

    def test_simulacion_valida_con_tasa_cruzada(self):
        """Simula la conversión cruzada vía la moneda base.

        Escenario: ``simular_conversion`` del par ``PYG/EUR`` sin tasa
        directa ni inversa; se resuelve mediante ``USD`` como moneda base.

        Datos relevantes: se crea ``TasaReferencia`` extra ``USD/EUR`` de
        ``0.875``; ``monto="7000"``; la tasa cruzada resulta
        ``0.875 / 7000 = 0.000125``.

        Resultado esperado: ``tasa == Decimal("0.000125")`` y ``resultado ==
        Decimal("0.8750000000")``.

        Assertions relevantes: ``assertEqual(resultado.tasa, ...)`` y
        ``assertEqual(resultado.resultado, ...)``.
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

        self.assertEqual(resultado.tasa, Decimal("0.000125"))
        self.assertEqual(resultado.resultado, Decimal("0.8750000000"))

    def test_rechaza_monto_cero(self):
        """Rechaza un monto de simulación igual a cero.

        Escenario: ``POST`` a ``tasas:simular_conversion`` con
        ``monto="0"``.

        Datos relevantes: par ``USD/PYG`` con ``monto="0"``.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"monto"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("monto", response.json()["detalles"])``.
        """
        response = self.client.post(
            self.url, self.payload(monto="0"), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_monto_negativo(self):
        """Rechaza un monto de simulación negativo.

        Escenario: ``POST`` a ``tasas:simular_conversion`` con
        ``monto="-50"``.

        Datos relevantes: par ``USD/PYG`` con ``monto="-50"``.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"monto"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("monto", response.json()["detalles"])``.
        """
        response = self.client.post(
            self.url, self.payload(monto="-50"), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_monto_no_numerico(self):
        """Rechaza un monto no numérico en la simulación.

        Escenario: ``POST`` a ``tasas:simular_conversion`` con
        ``monto="abc"``.

        Datos relevantes: par ``USD/PYG`` con ``monto="abc"``.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"monto"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("monto", response.json()["detalles"])``.
        """
        response = self.client.post(
            self.url, self.payload(monto="abc"), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_monto_ausente_y_no_finito(self):
        """Rechaza un monto ausente o no finito en la simulación.

        Escenario: se itera con ``subTest`` sobre los montos ``None`` y
        ``"NaN"`` en ``POST`` a ``tasas:simular_conversion``.

        Datos relevantes: ``self.payload(monto=monto)`` para cada caso.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"monto"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("monto", response.json()["detalles"])``.
        """
        for monto in (None, "NaN"):
            with self.subTest(monto=monto):
                response = self.client.post(
                    self.url,
                    self.payload(monto=monto),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("monto", response.json()["detalles"])

    def test_rechaza_moneda_inactiva(self):
        """Rechaza una moneda destino inactiva en la simulación.

        Escenario: la moneda destino ``PYG`` se pone en estado
        ``INACTIVA`` antes de simular el par ``USD/PYG``.

        Datos relevantes: ``self.pyg.estado = "INACTIVA"`` y ``save()``;
        ``POST`` a ``tasas:simular_conversion`` con el payload usual.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"moneda_destino"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("moneda_destino", response.json()["detalles"])``.
        """
        self.pyg.estado = "INACTIVA"
        self.pyg.save()
        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("moneda_destino", response.json()["detalles"])

    def test_rechaza_moneda_origen_inactiva(self):
        """Rechaza una moneda origen inactiva en la simulación.

        Escenario: la moneda origen ``USD`` se pone en estado ``INACTIVA``
        antes de simular el par ``USD/PYG``.

        Datos relevantes: ``self.usd.estado = "INACTIVA"`` y
        ``save(update_fields=["estado"])``.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"moneda_origen"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("moneda_origen", response.json()["detalles"])``.
        """
        self.usd.estado = "INACTIVA"
        self.usd.save(update_fields=["estado"])

        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("moneda_origen", response.json()["detalles"])

    def test_rechaza_misma_moneda(self):
        """Rechaza una simulación con la misma moneda de origen y destino.

        Escenario: ``POST`` a ``tasas:simular_conversion`` con ``USD`` como
        origen y también como destino de la operación.

        Datos relevantes: ``self.payload(moneda_destino_id=self.usd.id)``.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"monedas"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("monedas", response.json()["detalles"])``.
        """
        response = self.client.post(
            self.url,
            self.payload(moneda_destino_id=self.usd.id),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("monedas", response.json()["detalles"])

    def test_rechaza_monedas_ausentes_o_inexistentes(self):
        """Rechaza monedas ausentes o inexistentes en la simulación.

        Escenario: se itera con ``subTest`` sobre casos donde la moneda de
        origen o destino es ``None`` o un ``id`` inexistente (``999999``).

        Datos relevantes: casos con ``campo`` ``"moneda_origen"`` /
        ``"moneda_destino"`` y ``self.payload(**valores)``.

        Resultado esperado: ``response.status_code == 400`` para todos y el
        error incluye la clave del campo implicado.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn(campo, response.json()["detalles"])`` dentro de cada
        ``subTest``.
        """
        casos = (
            ({"moneda_origen_id": None}, "moneda_origen"),
            ({"moneda_destino_id": None}, "moneda_destino"),
            ({"moneda_origen_id": 999999}, "moneda_origen"),
            ({"moneda_destino_id": 999999}, "moneda_destino"),
        )
        for valores, campo in casos:
            with self.subTest(valores=valores):
                response = self.client.post(
                    self.url,
                    self.payload(**valores),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(campo, response.json()["detalles"])

    def test_informa_si_no_existe_tasa(self):
        """Informa error cuando no existe tasa para el par simulado.

        Escenario: ``POST`` a ``tasas:simular_conversion`` para el par
        ``USD/EUR`` sin ``TasaReferencia`` registrada.

        Datos relevantes: ``self.payload(moneda_destino_id=self.eur.id)``.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"tasa"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("tasa", response.json()["detalles"])``.
        """
        response = self.client.post(
            self.url,
            self.payload(moneda_destino_id=self.eur.id),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tasa", response.json()["detalles"])

    def test_no_utiliza_tasa_desactualizada(self):
        """No utiliza una tasa de referencia desactualizada.

        Escenario: la tasa vigente vence (``vigente_hasta`` en el pasado)
        antes de simular el par ``USD/PYG``.

        Datos relevantes: ``self.tasa.vigente_hasta = timezone.now() -
        timedelta(minutes=1)`` y ``save()``.

        Resultado esperado: ``response.status_code == 400`` y el error
        incluye la clave ``"tasa"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertIn("tasa", response.json()["detalles"])``.
        """
        self.tasa.vigente_hasta = timezone.now() - timedelta(minutes=1)
        self.tasa.save()
        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tasa", response.json()["detalles"])

    def test_simulador_es_publico(self):
        """El simulador de conversión es accesible sin autenticación.

        Escenario: ``POST`` anónimo a ``tasas:simular_conversion`` para el
        par ``USD/PYG``.

        Datos relevantes: ``monto="100"`` y tasa ``7000`` para el par.

        Resultado esperado: ``200`` con ``moneda_origen="USD"``,
        ``moneda_destino="PYG"``, ``monto="100"``, ``tasa="7000.0000000000"``,
        ``tipo_tasa="REFERENCIA"``, ``fecha_hora`` igual a la fijada y
        ``resultado="700000.0000000000"``.

        Assertions relevantes: ``assertEqual`` sobre ``status_code`` y cada
        campo de ``datos``.
        """
        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        datos = response.json()
        self.assertEqual(datos["moneda_origen"], "USD")
        self.assertEqual(datos["moneda_destino"], "PYG")
        self.assertEqual(datos["monto"], "100")
        self.assertEqual(datos["tasa"], "7000.0000000000")
        self.assertEqual(datos["tipo_tasa"], "REFERENCIA")
        self.assertEqual(datos["fecha_hora"], self.fecha.isoformat())
        self.assertEqual(datos["resultado"], "700000.0000000000")

    def test_usuario_autenticado_utiliza_el_mismo_endpoint_y_algoritmo(self):
        """El usuario autenticado usa el mismo endpoint y algoritmo.

        Escenario: sesión autenticada con ``sub="usuario-hu19"``,
        ``username="usuario.hu19"`` y rol ``USUARIO`` antes de un ``POST``
        al simulador.

        Datos relevantes: par ``USD/PYG`` con ``monto="100"`` y tasa
        ``7000`` vigente.

        Resultado esperado: ``200``, ``tipo_tasa="REFERENCIA"`` y
        ``resultado=="700000.0000000000"`` (mismo cálculo que sin sesión).

        Assertions relevantes: ``assertEqual(response.status_code, 200)`` y
        ``assertEqual(response.json()["tipo_tasa"], "REFERENCIA")`` y
        ``assertEqual(response.json()["resultado"], "700000.0000000000")``.
        """
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {"sub": "usuario-hu19", "username": "usuario.hu19"}
        session[SESSION_ROLES] = ["USUARIO"]
        session[SESSION_EXPIRA_EN] = time.time() + 3600
        session.save()

        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tipo_tasa"], "REFERENCIA")
        self.assertEqual(response.json()["resultado"], "700000.0000000000")

    def test_el_calculo_refleja_el_valor_persistido_actual(self):
        """El cálculo usa el valor de tasa actualmente persistido.

        Escenario: se actualiza el valor de la tasa vigente a ``7100``
        (``save(update_fields=["valor"])``) y luego se simula.

        Datos relevantes: par ``USD/PYG`` con ``self.tasa.valor =
        Decimal("7100")``.

        Resultado esperado: ``200`` con ``tasa="7100.0000000000"`` y
        ``resultado="710000.0000000000"``.

        Assertions relevantes: ``assertEqual(response.status_code, 200)`` y
        ``assertEqual`` sobre ``tasa`` y ``resultado`` en la respuesta.
        """
        self.tasa.valor = Decimal("7100")
        self.tasa.save(update_fields=["valor"])

        response = self.client.post(
            self.url, self.payload(), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasa"], "7100.0000000000")
        self.assertEqual(response.json()["resultado"], "710000.0000000000")

    def test_landing_entrega_csrf_para_el_simulador_publico(self):
        """La landing entrega el token CSRF para el simulador público.

        Escenario: cliente con ``enforce_csrf_checks=True`` visita
        ``usuarios:home`` para obtener el token y luego envía ``POST`` al
        simulador con y sin ``HTTP_X_CSRFTOKEN``.

        Datos relevantes: ``landing`` ``GET``, ``navegador.cookies[
        "csrftoken"].value`` como token; ``sin_token`` y ``con_token``.

        Resultado esperado: landing ``200``, ``sin_token`` ``403`` y
        ``con_token`` ``200``.

        Assertions relevantes: ``assertEqual`` sobre ``landing.status_code``,
        ``sin_token.status_code`` y ``con_token.status_code``.
        """
        navegador = Client(enforce_csrf_checks=True)
        landing = navegador.get(reverse("usuarios:home"))
        token = navegador.cookies["csrftoken"].value

        sin_token = navegador.post(
            self.url,
            self.payload(),
            content_type="application/json",
        )
        con_token = navegador.post(
            self.url,
            self.payload(),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(landing.status_code, 200)
        self.assertEqual(sin_token.status_code, 403)
        self.assertEqual(con_token.status_code, 200)

    def test_simulacion_no_modifica_datos(self):
        """Simular una conversión no modifica datos persistentes.

        Escenario: anterior a la simulación se registran los contadores de
        ``ConsultaProveedorTasas`` y ``TasaReferencia``.

        Datos relevantes: ``POST`` al simulador para el par ``USD/PYG``.

        Resultado esperado: ``200`` y los contadores de ambos modelos se
        mantienen sin cambios tras la simulación.

        Assertions relevantes: ``assertEqual(response.status_code, 200)`` y
        ``assertEqual`` sobre los ``count()`` de ambos modelos.
        """
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
