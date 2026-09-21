import json
import time

from django.test import TestCase
from django.urls import reverse

from monedas.models import Moneda
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import TasaComercial


class TasaComercialTests(TestCase):
    """Pruebas de HU-21 - Administrar tasas comerciales."""

    def setUp(self):
        Moneda.objects.all().delete()
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
        session[SESSION_EXPIRA_EN] = time.time() + 3600

        session.save()

    def enviar_tasa(self, datos):
        """Envía una tasa comercial como JSON."""
        return self.client.post(
            self.url,
            data=json.dumps(datos),
            content_type="application/json",
        )

    def crear_tasa_vigente(self):
        """Crea mediante la API la tasa base usada en pruebas de baja."""
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])
        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )
        self.assertEqual(response.status_code, 201)
        return TasaComercial.objects.get()

    def test_usuario_anonimo_no_puede_modificar_tasa(self):
        """Un usuario anónimo no puede modificar una tasa comercial.

        Escenario: petición ``POST /api/tasas/comerciales/`` utilizando el
        helper ``self.enviar_tasa`` sin sesión OIDC previa.

        Datos relevantes: par ``USD/PYG`` con ``compra="7200"`` y
        ``venta="7300"``.

        Resultado esperado: ``response.status_code == 401`` y no se persiste
        ninguna tasa (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 401)`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_usuario_con_rol_incorrecto_recibe_403(self):
        """Un usuario con rol no autorizado recibe ``403``.

        Escenario: sesión OIDC vigente con rol ``USUARIO``
        (``self.autenticar_con_roles(["USUARIO"])``) al enviar una tasa
        comercial.

        Datos relevantes: par ``USD/PYG`` con ``compra="7200"`` y
        ``venta="7300"``.

        Resultado esperado: ``response.status_code == 403`` porque el
        endpoint exige rol ``ANALISTA_CAMBIARIO``.

        Assertion relevante: ``assertEqual(response.status_code, 403)``.
        """
        self.autenticar_con_roles(["USUARIO"])

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 403)

    def test_administrador_no_puede_crear_ni_modificar_tasa(self):
        """Un administrador no puede crear ni modificar tasas comerciales.

        Escenario: sesión OIDC vigente con rol ``ADMINISTRADOR``
        (``self.autenticar_con_roles(["ADMINISTRADOR"])``) al enviar una
        tasa comercial.

        Datos relevantes: par ``USD/PYG`` con ``compra="7200"`` y
        ``venta="7300"``.

        Resultado esperado: ``response.status_code == 403`` y no se persiste
        ninguna tasa (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 403)`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_administrador_puede_consultar_el_historial_sin_modificar_tasas(self):
        """Un administrador consulta el historial sin modificar tasas.

        Escenario: sesión OIDC vigente con rol ``ADMINISTRADOR``
        (``self.autenticar_con_roles(["ADMINISTRADOR"])``) consultando
        ``GET`` ``tasas:historial_tasas_comerciales``.

        Datos relevantes: sin tasas persistidas; el historial devuelve las
        monedas activas del sistema.

        Resultado esperado: ``200``, la primera moneda activa es ``PYG`` y
        no se crea ninguna tasa (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 200)``,
        ``assertEqual(response.json()["monedas"][0]["codigo"], "PYG")`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.get(
            reverse("tasas:historial_tasas_comerciales")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["monedas"][0]["codigo"], "PYG")
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_analista_puede_registrar_tasa(self):
        """Un analista cambiario registra la primera tasa del par.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``
        (``self.autenticar_con_roles(...)``) enviando una tasa comercial.

        Datos relevantes: par ``USD/PYG`` con ``compra="7200"`` y
        ``venta="7300"``.

        Resultado esperado: ``201``, se persiste una sola tasa con
        ``version=1``, ``vigente=True`` y ``usuario_id="analista-keycloak-1"``;
        el historial la muestra como única y vigente.

        Assertions relevantes: ``assertEqual(response.status_code, 201)``,
        ``assertEqual(TasaComercial.objects.count(), 1)``,
        ``assertEqual(tasa.version, 1)``, ``assertTrue(tasa.vigente)``,
        ``assertEqual(tasa.usuario_id, "analista-keycloak-1")`` y chequeo
        del historial (``200``, una tasa, ``vigente=True``).
        """
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

        self.assertEqual(response.status_code, 201)
        self.assertEqual(TasaComercial.objects.count(), 1)

        tasa = TasaComercial.objects.get()

        self.assertEqual(tasa.version, 1)
        self.assertTrue(tasa.vigente)
        self.assertEqual(
            tasa.usuario_id,
            "analista-keycloak-1",
        )

        historial = self.client.get(
            reverse("tasas:historial_tasas_comerciales")
        )
        self.assertEqual(historial.status_code, 200)
        self.assertEqual(len(historial.json()["tasas"]), 1)
        self.assertTrue(historial.json()["tasas"][0]["vigente"])

    def test_rechaza_tasa_menor_o_igual_a_cero(self):
        """Rechaza una tasa de compra menor o igual a cero.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``
        enviando una tasa comercial.

        Datos relevantes: par ``USD/PYG`` con ``compra="0"``
        (``venta="7300"``).

        Resultado esperado: ``response.status_code == 400`` y no se persiste
        ninguna tasa (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
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

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_rechaza_moneda_inactiva(self):
        """Rechaza una tasa cuyo par usa una moneda inactiva.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``
        enviando una tasa comercial.

        Datos relevantes: moneda de origen ``EUR`` con estado ``INACTIVA``
        (``self.eur``) y destino ``PYG``; ``compra="7200"`` y
        ``venta="7300"``.

        Resultado esperado: ``response.status_code == 400`` y no se persiste
        ninguna tasa (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
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

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_no_permite_misma_moneda_en_el_par(self):
        """Rechaza un par que repite la misma moneda de origen y destino.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``
        enviando una tasa comercial.

        Datos relevantes: ``moneda_origen_id`` y ``moneda_destino_id``
        apuntan a la misma moneda ``USD`` (``compra="1"``, ``venta="1.1"``).

        Resultado esperado: ``response.status_code == 400`` y no se persiste
        ninguna tasa (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
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

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_primera_tasa_necesita_compra_y_venta(self):
        """La primera tasa de un par exige compra y venta.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``
        enviando una tasa comercial con valores parciales.

        Datos relevantes: par ``USD/PYG`` enviando sólo ``compra="7200"``
        (sin venta) sin tasa previa del par.

        Resultado esperado: ``response.status_code == 400`` y no se persiste
        ninguna tasa (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
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

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_modificacion_conserva_historico(self):
        """Modificar un par conserva el histórico y crea una nueva versión.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``;
        primero se registra la tasa base y luego se envía una modificación.

        Datos relevantes: primera ``compra="7200"`` y ``venta="7300"``
        (``201``); segunda sólo ``compra="7250"`` para el mismo par
        ``USD/PYG``.

        Resultado esperado: ``201`` en ambos envíos, ``count() == 2``,
        ``version 1`` queda ``vigente=False`` con ``compra="7200.000000"``,
        ``version 2`` queda ``vigente=True`` con ``compra="7250.000000"`` y
        conserva la venta ``7300.000000`` de la versión anterior.

        Assertions relevantes: ``assertEqual(segunda.status_code, 201)``,
        ``assertEqual(TasaComercial.objects.count(), 2)``,
        ``assertFalse(version_1.vigente)``, ``assertTrue(version_2.vigente)``
        y comparaciones de ``compra``/``venta`` por versión.
        """
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

        self.assertEqual(primera.status_code, 201)

        segunda = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7250",
            }
        )

        self.assertEqual(segunda.status_code, 201)
        self.assertEqual(TasaComercial.objects.count(), 2)

        version_1 = TasaComercial.objects.get(
            version=1
        )

        version_2 = TasaComercial.objects.get(
            version=2
        )

        self.assertFalse(version_1.vigente)
        self.assertTrue(version_2.vigente)

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
        """El registro de una tasa guarda los datos de auditoría del usuario.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``
        enviando una tasa comercial.

        Datos relevantes: par ``USD/PYG`` con ``compra="7200"`` y
        ``venta="7300"``; sesión con ``sub="analista-keycloak-1"`` y
        ``username="analista.prueba"``.

        Resultado esperado: ``201`` y la tasa persistida conserva
        ``usuario_id="analista-keycloak-1"``,
        ``usuario_username="analista.prueba"`` y ``fecha_registro`` no nula.

        Assertions relevantes: ``assertEqual(response.status_code, 201)``,
        ``assertEqual(tasa.usuario_id, "analista-keycloak-1")``,
        ``assertEqual(tasa.usuario_username, "analista.prueba")`` y
        ``assertIsNotNone(tasa.fecha_registro)``.
        """
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

        self.assertEqual(response.status_code, 201)

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

    def test_validacion_fallida_no_modifica_tasa_vigente(self):
        """Una validación fallida deja intacta la tasa vigente actual.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``; se
        registra la tasa base y luego se envía una modificación inválida.

        Datos relevantes: primera ``compra="7200"`` y ``venta="7300"``
        (``201``); segunda con ``venta="0"`` para el mismo par ``USD/PYG``.

        Resultado esperado: ``400`` en la segunda petición, ``count() == 1``
        y la tasa vigente original conserva ``vigente=True``,
        ``compra="7200.000000"`` y ``venta="7300.000000"``.

        Assertions relevantes: ``assertEqual(response.status_code, 400)``,
        ``assertEqual(TasaComercial.objects.count(), 1)``,
        ``assertTrue(tasa_original.vigente)`` y comparaciones de
        ``compra``/``venta``.
        """
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

        self.assertEqual(primera.status_code, 201)

        tasa_original = TasaComercial.objects.get(
            vigente=True
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "venta": "0",
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TasaComercial.objects.count(), 1)

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

    def test_historial_devuelve_versiones_registradas(self):
        """El historial devuelve las versiones registradas del par.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``; se
        registran dos versiones para el par ``USD/PYG``.

        Datos relevantes: primera ``compra="7200"``, ``venta="7300"``;
        segunda sólo ``venta="7350"`` (reutiliza la compra vigente). Se
        consulta ``GET`` ``tasas:historial_tasas_comerciales``.

        Resultado esperado: ``200``, ``len(tasas) == 2`` con versiones
        ``[2, 1]`` en ese orden, estados ``[True, False]`` y ambas con
        ``usuario_username="analista.prueba"``.

        Assertions relevantes: ``assertEqual(response.status_code, 200)``,
        ``assertEqual(len(response.json()["tasas"]), 2)``,
        ``assertEqual([tasa["version"] for tasa in versiones], [2, 1])``,
        ``assertEqual([tasa["vigente"] for tasa in versiones], [True, False])``
        y chequeo del conjunto de ``usuario_username``.
        """
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
            len(response.json()["tasas"]),
            2,
        )
        versiones = response.json()["tasas"]
        self.assertEqual([tasa["version"] for tasa in versiones], [2, 1])
        self.assertEqual([tasa["vigente"] for tasa in versiones], [True, False])
        self.assertEqual(
            {tasa["usuario_username"] for tasa in versiones},
            {"analista.prueba"},
        )

    def test_no_existe_eliminacion_de_tasas_comerciales(self):
        """Verifica que no existe eliminación de tasas comerciales via API.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO`` y una
        tasa registrada para el par ``USD/PYG``.

        Datos relevantes: se envía ``DELETE`` al endpoint de
        administración de tasas comerciales (``self.url``).

        Resultado esperado: ``response.status_code == 405`` (método no
        permitido) y la tasa persistida se conserva
        (``TasaComercial.objects.count() == 1``).

        Assertions relevantes: ``assertEqual(response.status_code, 405)`` y
        ``assertEqual(TasaComercial.objects.count(), 1)``.
        """
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])
        self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7200",
                "venta": "7300",
            }
        )

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(TasaComercial.objects.count(), 1)

    def test_endpoint_de_referencia_no_acepta_edicion_manual(self):
        """El endpoint de referencia no acepta edición manual vía POST.

        Escenario: sesión OIDC vigente con rol ``ANALISTA_CAMBIARIO``
        (``self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])``) enviando
        ``POST`` al endpoint de consulta de tasas de referencia
        (``tasas:consultar``).

        Datos relevantes: cuerpo vacío ``{}`` en la petición.

        Resultado esperado: ``response.status_code == 405`` (método no
        permitido) y no se registra ninguna tasa comercial
        (``TasaComercial.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 405)`` y
        ``assertEqual(TasaComercial.objects.count(), 0)``.
        """
        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

        response = self.client.post(reverse("tasas:consultar"), {})

        self.assertEqual(response.status_code, 405)
        self.assertEqual(TasaComercial.objects.count(), 0)

    def test_analista_puede_desactivar_tasa_comercial(self):
        """Un analista cambiario puede desactivar una tasa comercial.

        Escenario: sesión creada con rol ``ANALISTA_CAMBIARIO`` mediante
        ``self.crear_tasa_vigente()`` y petición ``POST`` a
        ``tasas:desactivar_tasa_comercial``.

        Datos relevantes: tasa vigente existente; cuerpo ``{}`` en JSON.

        Resultado esperado: ``response.status_code == 200``, la respuesta
        JSON reporta ``vigente=False`` y en base la tasa queda desactivada
        (``tasa.vigente is False`` tras ``refresh_from_db()``).

        Assertions relevantes: ``assertEqual(response.status_code, 200)``,
        ``assertFalse(response.json()["tasa"]["vigente"])`` y
        ``assertFalse(tasa.vigente)``.
        """
        tasa = self.crear_tasa_vigente()

        response = self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["tasa"]["vigente"])
        tasa.refresh_from_db()
        self.assertFalse(tasa.vigente)

    def test_administrador_no_puede_desactivar_tasa_comercial(self):
        """Un administrador no puede desactivar una tasa comercial.

        Escenario: se crea una tasa vigente (``self.crear_tasa_vigente()``)
        y luego se cambia la sesión a rol ``ADMINISTRADOR`` antes de enviar
        ``POST`` a ``tasas:desactivar_tasa_comercial``.

        Datos relevantes: tasa vigente existente; cuerpo ``{}`` en JSON.

        Resultado esperado: ``response.status_code == 403`` y la tasa
        permanece vigente (``tasa.vigente is True`` tras
        ``refresh_from_db()``).

        Assertions relevantes: ``assertEqual(response.status_code, 403)`` y
        ``assertTrue(tasa.vigente)``.
        """
        tasa = self.crear_tasa_vigente()
        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        tasa.refresh_from_db()
        self.assertTrue(tasa.vigente)

    def test_tasa_desactivada_permanece_en_historial(self):
        """Una tasa desactivada permanece visible en el historial.

        Escenario: se crea una tasa vigente y se desactiva vía
        ``POST`` ``tasas:desactivar_tasa_comercial``; luego se consulta el
        historial filtrando por el par ``USD/PYG``.

        Datos relevantes: ``self.crear_tasa_vigente()`` para el par
        ``USD/PYG``.

        Resultado esperado: ``200``, ``len(tasas) == 1`` con el ``id`` de la
        tasa desactivada y ``vigente=False`` en la respuesta JSON.

        Assertions relevantes: ``assertEqual(response.status_code, 200)``,
        ``assertEqual(len(response.json()["tasas"]), 1)``,
        ``assertEqual(response.json()["tasas"][0]["id"], tasa.id)`` y
        ``assertFalse(response.json()["tasas"][0]["vigente"])``.
        """
        tasa = self.crear_tasa_vigente()
        self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        response = self.client.get(
            reverse("tasas:historial_tasas_comerciales"),
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["tasas"]), 1)
        self.assertEqual(response.json()["tasas"][0]["id"], tasa.id)
        self.assertFalse(response.json()["tasas"][0]["vigente"])

    def test_desactivacion_no_elimina_fisicamente_el_registro(self):
        """Desactivar una tasa no elimina físicamente el registro.

        Escenario: se crea una tasa vigente y se desactiva vía
        ``POST`` ``tasas:desactivar_tasa_comercial`` (cuerpo ``{}``).

        Datos relevantes: ``self.crear_tasa_vigente()`` (par ``USD/PYG``).

        Resultado esperado: el registro persiste: ``count() == 1``,
        ``Moneda.objects.filter(pk=tasa.id).exists()`` es ``True`` y su
        estado queda ``vigente=False``.

        Assertions relevantes: ``assertEqual(TasaComercial.objects.count(),
        1)``, ``assertTrue(...filter(pk=tasa.id).exists())`` y
        ``assertFalse(TasaComercial.objects.get(pk=tasa.id).vigente)``.
        """
        tasa = self.crear_tasa_vigente()

        self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(TasaComercial.objects.count(), 1)
        self.assertTrue(TasaComercial.objects.filter(pk=tasa.id).exists())
        self.assertFalse(TasaComercial.objects.get(pk=tasa.id).vigente)

    def test_nueva_tasa_tras_baja_reanuda_versionado_del_par(self):
        """Registrar una nueva tasa tras la baja reanuda el versionado.

        Escenario: se crea una tasa vigente, se desactiva y luego se
        registra una nueva tasa para el mismo par ``USD/PYG``.

        Datos relevantes: ``self.crear_tasa_vigente()`` (versión 1,
        ``compra="7200"``, ``venta="7300"``); desactivación; nuevo envío
        con ``compra="7250"`` y ``venta="7350"``.

        Resultado esperado: ``201``, ``count() == 2``, la nueva tasa tiene
        ``version=2`` y ``vigente=True``, y la versión anterior queda
        ``vigente=False`` (una sola vigente por par).

        Assertions relevantes: ``assertEqual(response.status_code, 201)``,
        ``assertEqual(TasaComercial.objects.count(), 2)``,
        ``assertEqual(response.json()["tasa"]["version"], 2)``,
        ``assertEqual(TasaComercial.objects.filter(vigente=True).count(),
        1)`` y ``assertFalse(...get(pk=tasa.id).vigente)``.
        """
        tasa = self.crear_tasa_vigente()
        self.client.post(
            reverse("tasas:desactivar_tasa_comercial", args=[tasa.id]),
            data=json.dumps({}),
            content_type="application/json",
        )

        response = self.enviar_tasa(
            {
                "moneda_origen_id": self.usd.id,
                "moneda_destino_id": self.pyg.id,
                "compra": "7250",
                "venta": "7350",
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(TasaComercial.objects.count(), 2)
        self.assertEqual(response.json()["tasa"]["version"], 2)
        self.assertEqual(TasaComercial.objects.filter(vigente=True).count(), 1)
        self.assertFalse(TasaComercial.objects.get(pk=tasa.id).vigente)
