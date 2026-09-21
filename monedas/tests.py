import json
import time
from unittest.mock import patch

from django.test import TestCase

from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import Moneda


class MonedaBackendTests(TestCase):
    """
    Pruebas de Backend para HU-36 - Configurar Monedas.
    """

    def setUp(self):
        # Los casos CRUD necesitan un catálogo vacío; la migración de datos
        # iniciales se valida por separado en MonedasInicialesTests.
        Moneda.objects.all().delete()

    def autenticar(self, roles=None):
        """
        Crea una sesión OIDC válida para las pruebas.
        """

        roles = roles or ["ADMINISTRADOR"]

        session = self.client.session

        session[SESSION_AUTENTICADO] = True
        session[SESSION_USUARIO] = {
            "sub": "usuario-prueba-001",
            "preferred_username": "admin.prueba",
        }
        session[SESSION_ROLES] = roles
        session[SESSION_EXPIRA_EN] = time.time() + 3600

        session.save()

    def test_usuario_no_autenticado_recibe_401(self):
        """Un cliente anónimo que consulta el endpoint recibe ``401``.

        Escenario: petición ``GET /api/monedas/`` sin sesión OIDC previa
        (no se llama a ``self.autenticar()``).

        Resultado esperado: ``response.status_code == 401``, porque el
        acceso requiere autenticación OIDC vigente.

        Assertion relevante: ``assertEqual(response.status_code, 401)``.
        """
        response = self.client.get("/api/monedas/")

        self.assertEqual(response.status_code, 401)

    def test_usuario_sin_rol_administrador_recibe_403(self):
        """Un usuario autenticado sin rol de administración recibe ``403``.

        Escenario: sesión OIDC vigente con rol ``USUARIO`` (a través de
        ``self.autenticar(["USUARIO"])``) consultando ``GET /api/monedas/``.

        Resultado esperado: ``response.status_code == 403``, porque el
        catálogo de administración exige rol ``ADMINISTRADOR``.

        Assertion relevante: ``assertEqual(response.status_code, 403)``.
        """
        self.autenticar(["USUARIO"])

        response = self.client.get("/api/monedas/")

        self.assertEqual(response.status_code, 403)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_crear_moneda(self, _mock_sesion):
        """Un administrador registra una moneda nueva y se persiste.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        sesión autenticada con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Acción: ``POST /api/monedas/crear/`` con JSON ``codigo=USD``,
        ``nombre="Dólar estadounidense"``, ``simbolo="$"`` y
        ``estado="ACTIVA"``.

        Resultado esperado: ``201``, ``Moneda.objects.count() == 1`` y el
        registro con ``codigo="USD"``, ``nombre="Dólar estadounidense"``,
        ``simbolo="$"`` y ``estado="ACTIVA"``.

        Assertiones relevantes: ``assertEqual(response.status_code, 201)``,
        ``assertEqual(Moneda.objects.count(), 1)`` y comprobación de cada
        campo (``codigo``, ``nombre``, ``simbolo``, ``estado``).
        """
        self.autenticar()

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": "USD",
                    "nombre": "Dólar estadounidense",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Moneda.objects.count(), 1)

        moneda = Moneda.objects.get()

        self.assertEqual(moneda.codigo, "USD")
        self.assertEqual(moneda.nombre, "Dólar estadounidense")
        self.assertEqual(moneda.simbolo, "$")
        self.assertEqual(moneda.estado, "ACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_codigo_se_normaliza(self, _mock_sesion):
        """Verifica que el código de la moneda se normaliza antes de guardar.

        Escenario: sesión OIDC vigente y usuario autenticado con rol
        ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: ``POST /api/monedas/crear/`` con cuerpo JSON
        ``codigo=" usd "`` (con espacios redundantes),
        ``nombre="Dólar estadounidense"``, ``simbolo="$"`` y
        ``estado="ACTIVA"``.

        Resultado esperado: ``201 Created`` y el ``codigo`` almacenado
        normalizado a ``"USD"`` (sin espacios, en mayúsculas).

        Assertion relevante: ``assertEqual(moneda.codigo, "USD")``.
        """
        self.autenticar()

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": " usd ",
                    "nombre": "Dólar estadounidense",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        moneda = Moneda.objects.get()

        self.assertEqual(moneda.codigo, "USD")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_codigo_duplicado_despues_de_normalizar(self, _mock_sesion):
        """Verifica que un código duplicado tras normalizar devuelve ``409``.

        Escenario: administrador autenticado consulta
        ``POST /api/monedas/crear/``.

        Datos relevantes: ya existe una moneda ``USD``; se intenta crear
        ``" usd "`` que normaliza a ``USD`` duplicado.

        Resultado esperado: ``response.status_code == 409`` y que no se
        persista una segunda moneda (``Moneda.objects.count() == 1``).

        Assertions relevantes: ``assertEqual(response.status_code, 409)``
        y ``assertEqual(Moneda.objects.count(), 1)``.
        """
        self.autenticar()

        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar estadounidense",
            simbolo="$",
            estado="ACTIVA",
        )

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": " usd ",
                    "nombre": "Otra descripción",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Moneda.objects.count(), 1)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_rechaza_datos_obligatorios(self, _mock_sesion):
        """Valida el rechazo de monedas con datos obligatorios vacíos.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Acción: ``POST /api/monedas/crear/`` con JSON que envía ``codigo``,
        ``nombre`` y ``simbolo`` vacíos y ``estado="ACTIVA"``.

        Resultado esperado: ``400 Bad Request`` y que **no** se persista
        ninguna moneda (``Moneda.objects.count() == 0``).

        Assertions relevantes: ``assertEqual(response.status_code, 400)`` y
        ``assertEqual(Moneda.objects.count(), 0)``.
        """
        self.autenticar()

        response = self.client.post(
            "/api/monedas/crear/",
            data=json.dumps(
                {
                    "codigo": "",
                    "nombre": "",
                    "simbolo": "",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Moneda.objects.count(), 0)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_editar_moneda(self, _mock_sesion):
        """Permite que un administrador edite una moneda existente.

        Escenario: sesión OIDC vigente (``sesion_oidc_vigente``) y usuario
        con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: moneda ``USD`` existente; se envía ``POST
        /api/monedas/{id}/editar/`` con JSON ``codigo="EUR"``,
        ``nombre="Euro"``, ``simbolo="€"`` y ``estado="ACTIVA"``.

        Resultado esperado: ``200`` y la moneda en base con ``codigo="EUR"``,
        ``nombre="Euro"`` y ``simbolo="€"`` (verificado con
        ``moneda.refresh_from_db()``).

        Assertions relevantes: ``assertEqual(response.status_code, 200)`` y
        comprobación de ``moneda.codigo``, ``moneda.nombre`` y
        ``moneda.simbolo``.
        """
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/editar/",
            data=json.dumps(
                {
                    "codigo": "EUR",
                    "nombre": "Euro",
                    "simbolo": "€",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.codigo, "EUR")
        self.assertEqual(moneda.nombre, "Euro")
        self.assertEqual(moneda.simbolo, "€")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_desactivar_moneda(self, _mock_sesion):
        """Un administrador desactiva una moneda y su estado pasa a ``INACTIVA``.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: moneda ``USD`` creada en estado ``ACTIVA``; se
        envía ``POST /api/monedas/{id}/estado/`` con JSON
        ``{"estado": "INACTIVA"}``.

        Resultado esperado: ``200`` y la moneda en base con
        ``estado="INACTIVA"`` (verificado con ``moneda.refresh_from_db()``).

        Assertions relevantes: ``assertEqual(response.status_code, 200)`` y
        ``assertEqual(moneda.estado, "INACTIVA")``.
        """
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/estado/",
            data=json.dumps(
                {"estado": "INACTIVA"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.estado, "INACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_desactivar_no_elimina_informacion_historica(self, _mock_sesion):
        """Desactivar una moneda conserva su registro e información histórica.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: moneda ``USD`` creada en estado ``ACTIVA`` y se
        envía ``POST /api/monedas/{id}/estado/`` con JSON
        ``{"estado": "INACTIVA"}``.

        Resultado esperado: ``200`` y el registro sigue existiendo con el
        mismo ``id``, ``codigo="USD"`` y ``nombre="Dólar"`` pero con
        ``estado="INACTIVA"`` (verificado con ``moneda.refresh_from_db()``).

        Assertions relevantes: ``assertEqual(moneda.id, moneda_id)``,
        ``assertEqual(moneda.codigo, "USD")``,
        ``assertEqual(moneda.nombre, "Dólar")`` y
        ``assertEqual(moneda.estado, "INACTIVA")``.
        """
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        moneda_id = moneda.id

        response = self.client.post(
            f"/api/monedas/{moneda_id}/estado/",
            data=json.dumps(
                {"estado": "INACTIVA"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.id, moneda_id)
        self.assertEqual(moneda.codigo, "USD")
        self.assertEqual(moneda.nombre, "Dólar")
        self.assertEqual(moneda.estado, "INACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_administrador_puede_reactivar_moneda(self, _mock_sesion):
        """Un administrador reactiva una moneda y su estado pasa a ``ACTIVA``.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: moneda ``USD`` creada en estado ``INACTIVA``; se
        envía ``POST /api/monedas/{id}/estado/`` con JSON
        ``{"estado": "ACTIVA"}``.

        Resultado esperado: ``200`` y la moneda en base con
        ``estado="ACTIVA"`` (verificado con ``moneda.refresh_from_db()``).

        Assertions relevantes: ``assertEqual(response.status_code, 200)`` y
        ``assertEqual(moneda.estado, "ACTIVA")``.
        """
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="INACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/estado/",
            data=json.dumps(
                {"estado": "ACTIVA"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        moneda.refresh_from_db()

        self.assertEqual(moneda.estado, "ACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_listar_solo_monedas_activas(self, _mock_sesion):
        """El endpoint de monedas activas devuelve sólo las de estado ``ACTIVA``.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: se crean ``USD`` (``ACTIVA``) y ``BRL``
        (``INACTIVA``) y se consulta ``GET /api/monedas/activas/``.

        Resultado esperado: ``200`` y una única moneda en
        ``data["monedas"]`` con ``codigo="USD"`` (la ``BRL`` INACTIVA queda
        fuera del listado).

        Assertion relevante: ``assertEqual(len(data["monedas"]), 1)`` y
        ``assertEqual(data["monedas"][0]["codigo"], "USD")``.
        """
        self.autenticar()

        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        Moneda.objects.create(
            codigo="BRL",
            nombre="Real brasileño",
            simbolo="R$",
            estado="INACTIVA",
        )

        response = self.client.get("/api/monedas/activas/")

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(len(data["monedas"]), 1)
        self.assertEqual(data["monedas"][0]["codigo"], "USD")

    def test_catalogo_activo_es_publico(self):
        """El catálogo de monedas activas es consultable sin autenticación.

        Escenario: petición ``GET /api/monedas/activas/`` sin sesión OIDC
        previa (no se llama a ``self.autenticar()``).

        Datos relevantes: se crea la moneda ``PYG`` con estado ``ACTIVA``.

        Resultado esperado: ``200`` y una única moneda en
        ``data["monedas"]`` con ``codigo="PYG"``; además el listado sólo
        expone los campos ``{"id", "codigo", "nombre", "simbolo",
        "estado"}`` y omite ``fecha_registro`` y ``fecha_actualizacion``.

        Assertions relevantes: ``assertEqual(response.status_code, 200)``,
        ``assertEqual(moneda["codigo"], "PYG")``,
        ``assertEqual(set(moneda), {...})`` y ``assertNotIn`` para
        ``fecha_registro`` y ``fecha_actualizacion``.
        """
        Moneda.objects.create(
            codigo="PYG",
            nombre="Guaraní",
            simbolo="Gs.",
            estado="ACTIVA",
        )

        response = self.client.get("/api/monedas/activas/")

        self.assertEqual(response.status_code, 200)
        moneda = response.json()["monedas"][0]
        self.assertEqual(moneda["codigo"], "PYG")
        self.assertEqual(
            set(moneda),
            {"id", "codigo", "nombre", "simbolo", "estado"},
        )
        self.assertNotIn("fecha_registro", moneda)
        self.assertNotIn("fecha_actualizacion", moneda)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_editar_con_codigo_existente_devuelve_409(self, _mock_sesion):
        """Editar una moneda con un código ya existente devuelve ``409``.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: ya existen las monedas ``USD`` y ``EUR``; se
        edita ``EUR`` enviando ``POST /api/monedas/{id}/editar/`` con JSON
        ``codigo="USD"``.

        Resultado esperado: ``response.status_code == 409`` por conflicto de
        código duplicado.

        Assertion relevante: ``assertEqual(response.status_code, 409)``.
        """
        self.autenticar()

        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        moneda = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
            estado="ACTIVA",
        )

        response = self.client.post(
            f"/api/monedas/{moneda.id}/editar/",
            data=json.dumps(
                {
                    "codigo": "USD",
                    "nombre": "Euro",
                    "simbolo": "€",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    def test_no_se_elimina_moneda_al_desactivar(self, _mock_sesion):
        """Desactivar una moneda no la borra de la base de datos.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``) y
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``).

        Datos relevantes: moneda ``USD`` creada en estado ``ACTIVA``; se
        envía ``POST /api/monedas/{id}/estado/`` con JSON
        ``{"estado": "INACTIVA"}``.

        Resultado esperado: ``200``, el registro sigue existiendo
        (``Moneda.objects.filter(id=moneda_id).exists()`` es ``True``) y su
        estado pasa a ``INACTIVA``.

        Assertions relevantes: ``assertEqual(response.status_code, 200)``,
        ``assertTrue(Moneda.objects.filter(id=moneda_id).exists())`` y
        ``assertEqual(moneda.estado, "INACTIVA")``.
        """
        self.autenticar()

        moneda = Moneda.objects.create(
                codigo="USD",
                nombre="Dólar",
                simbolo="$",
                estado="ACTIVA",
            )

        moneda_id = moneda.id

        response = self.client.post(
                f"/api/monedas/{moneda_id}/estado/",
                data=json.dumps(
                    {
                        "estado": "INACTIVA",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
                Moneda.objects.filter(id=moneda_id).exists()
            )

        moneda.refresh_from_db()

        self.assertEqual(moneda.estado, "INACTIVA")

    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    @patch("monedas.views.MonedaForm.save")
    def test_error_al_guardar_informa_la_situacion(
            self,
            mock_save,
            _mock_sesion,
        ):
        """Un fallo al guardar informa la situación con un mensaje claro.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``),
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``)
        y ``MonedaForm.save`` mockeado para lanzar una excepción.

        Datos relevantes: ``POST /api/monedas/crear/`` con JSON
        ``codigo="USD"``; ``mock_save.side_effect`` lanza
        ``Exception("Error de persistencia")``.

        Resultado esperado: ``500`` y ``response.json()["error"]`` igual a
        ``"No fue posible guardar la moneda."``.

        Assertions relevantes: ``assertEqual(response.status_code, 500)`` y
        ``assertEqual(response.json()["error"], ...)``.
        """
        self.autenticar()

        mock_save.side_effect = Exception("Error de persistencia")

        response = self.client.post(
                "/api/monedas/crear/",
                data=json.dumps(
                    {
                        "codigo": "USD",
                        "nombre": "Dólar",
                        "simbolo": "$",
                        "estado": "ACTIVA",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 500)

        self.assertEqual(
                response.json()["error"],
                "No fue posible guardar la moneda.",
            )


    @patch("usuarios.decorators.sesion_oidc_vigente", return_value=True)
    @patch("monedas.views.MonedaForm.save")
    def test_error_al_actualizar_informa_la_situacion(
        self,
        mock_save,
        _mock_sesion,
    ):
        """Un fallo al actualizar informa la situación con un mensaje claro.

        Escenario: sesión OIDC vigente (mock ``sesion_oidc_vigente``),
        usuario autenticado con rol ``ADMINISTRADOR`` (``self.autenticar()``)
        y ``MonedaForm.save`` mockeado para lanzar una excepción.

        Datos relevantes: moneda ``USD`` existente; ``POST
        /api/monedas/{id}/editar/`` con JSON ``codigo="USD"`` y
        ``mock_save.side_effect`` lanza ``Exception("Error de
        persistencia")``.

        Resultado esperado: ``500`` y ``response.json()["error"]`` igual a
        ``"No fue posible actualizar la moneda."``.

        Assertions relevantes: ``assertEqual(response.status_code, 500)`` y
        ``assertEqual(response.json()["error"], ...)``.
        """
        self.autenticar()

        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar",
            simbolo="$",
            estado="ACTIVA",
        )

        mock_save.side_effect = Exception("Error de persistencia")

        response = self.client.post(
            f"/api/monedas/{moneda.id}/editar/",
            data=json.dumps(
                {
                    "codigo": "USD",
                    "nombre": "Dólar estadounidense",
                    "simbolo": "$",
                    "estado": "ACTIVA",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 500)

        self.assertEqual(
            response.json()["error"],
            "No fue posible actualizar la moneda.",
        )


class MonedasInicialesTests(TestCase):
    """Comprueba el catálogo mínimo instalado por la migración de datos."""

    def test_migracion_carga_las_cinco_monedas_activas(self):
        """La migración de datos carga las cinco monedas activas iniciales.

        Escenario: base de datos sin modificar, con el catálogo instalado
        por la migración de datos iniciales (no se llama a
        ``self.autenticar()`` ni se borra el catálogo).

        Resultado esperado: en la base existen exactamente las cinco monedas
        ``USD``, ``PYG``, ``BRL``, ``EUR`` y ``ARS``, todas con estado
        ``ACTIVA``.

        Assertion relevante: ``assertEqual(set(...), {...})`` comparando los
        pares ``(codigo, estado)``.
        """
        self.assertEqual(
            set(Moneda.objects.values_list("codigo", "estado")),
            {
                ("USD", "ACTIVA"),
                ("PYG", "ACTIVA"),
                ("BRL", "ACTIVA"),
                ("EUR", "ACTIVA"),
                ("ARS", "ACTIVA"),
            },
        )
