import time
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from monedas.models import Moneda
from usuarios.services.keycloak import SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO

from .models import (BaseNotificacionTasa, ConfiguracionNotificacionTasa, EventoNotificacionTasa,
                     ResultadoNotificacionTasa, TasaComercial)
from .notificaciones import configurar_umbral, obtener_destinatarios, procesar_evento
from .services import actualizar_tasa_comercial

CORREO_PRUEBAS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
USUARIO = {"id": "usuario-keycloak", "enabled": True, "emailVerified": True, "email": "usuario@example.test"}


@override_settings(MAILERS=CORREO_PRUEBAS)
class NotificacionesTasasTests(TestCase):
    """Protege RF-10/RN4 y los acuerdos de acumulación sin contactar servicios externos."""

    def setUp(self):
        self.origen = Moneda.objects.get_or_create(codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"})[0]
        self.destino = Moneda.objects.get_or_create(codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"})[0]
        self.origen.activar()
        self.destino.activar()
        ConfiguracionNotificacionTasa.objects.get_or_create(pk=1)
        self.keycloak = mock.patch("tasas.notificaciones.admin_request", return_value=[USUARIO]).start()
        self.addCleanup(mock.patch.stopall)

    def actualizar(self, compra="100", venta="200"):
        """Ejecuta las callbacks capturadas con correo de pruebas y Keycloak simulado."""
        with self.captureOnCommitCallbacks(execute=True):
            return actualizar_tasa_comercial(self.origen.pk, self.destino.pk, "analista", compra=compra, venta=venta)

    def base(self):
        """Obtiene la comparación acumulada del destinatario del escenario."""
        return BaseNotificacionTasa.objects.get(destinatario_id=USUARIO["id"])

    def test_primera_tasa_inicializa_bases_sin_aviso(self):
        """Sin tasa anterior se crean bases para ambos lados y no se envía correo."""
        self.actualizar()
        self.assertEqual((self.base().compra, self.base().venta), (Decimal("100"), Decimal("200")))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ResultadoNotificacionTasa.objects.get().estado, "SIN_CAMBIOS")

    def test_destinatario_nuevo_usa_tasa_anterior_como_base(self):
        """Un usuario incorporado después compara con la tasa vigente anterior y recibe el cambio relevante."""
        self.keycloak.return_value = []
        self.actualizar()
        self.keycloak.return_value = [USUARIO]
        self.actualizar("103")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.base().compra, Decimal("103"))
        self.assertIn("tasa anterior 100", mail.outbox[0].body)

    def test_cambios_pequenos_acumulan_hasta_limite_inclusivo(self):
        """Cambios al 1 y 2 % conservan base 100; exactamente 3 % envía y avanza solo compra."""
        self.actualizar()
        self.actualizar("101")
        self.actualizar("102")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.base().compra, Decimal("100"))
        self.actualizar("103", "201")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual((self.base().compra, self.base().venta), (Decimal("103"), Decimal("200")))
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, [USUARIO["email"]])
        self.assertIn("USD/PYG", mensaje.subject)
        self.assertIn("Compra (subida)", mensaje.body)
        self.assertIn("tasa anterior 100", mensaje.body)
        self.assertIn("tasa nueva 103", mensaje.body)
        self.assertIn("variación 3", mensaje.body)
        self.assertNotIn("Venta", mensaje.body)

    def test_subida_compra_y_bajada_venta_agrupadas(self):
        """Dos lados relevantes de un par generan un solo correo y avanzan ambas bases."""
        self.actualizar()
        self.actualizar("103", "194")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Compra (subida)", mail.outbox[0].body)
        self.assertIn("Venta (bajada)", mail.outbox[0].body)
        self.assertEqual((self.base().compra, self.base().venta), (Decimal("103"), Decimal("194")))

    def test_bajada_compra_y_subida_venta_agrupadas(self):
        """El criterio simétrico también notifica compra descendente y venta ascendente."""
        self.actualizar()
        self.actualizar("97", "206")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Compra (bajada)", mail.outbox[0].body)
        self.assertIn("Venta (subida)", mail.outbox[0].body)
        self.assertEqual((self.base().compra, self.base().venta), (Decimal("97"), Decimal("206")))

    def test_porcentaje_no_se_redondea_para_decidir(self):
        """Una variación apenas inferior al 3 % no cumple aunque su presentación pueda parecer 3."""
        self.actualizar()
        self.actualizar("102.9999999999")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.base().compra, Decimal("100"))

    def test_fallo_destinatario_no_avanza_base_y_continua_con_otros(self):
        """Un fallo SMTP conserva su base, registra error seguro y no impide enviar al siguiente ni guardar tasa."""
        otro = {**USUARIO, "id": "otro", "email": "otro@example.test"}
        self.keycloak.return_value = [USUARIO, otro]
        self.actualizar()
        from .notificaciones import enviar_correo
        enviar = enviar_correo

        def envio_parcial(*args, **kwargs):
            if args[3] == [USUARIO["email"]]:
                raise RuntimeError("SECRETO-no-registrar")
            return enviar(*args, **kwargs)

        with mock.patch("tasas.notificaciones.enviar_correo", side_effect=envio_parcial), self.assertLogs("tasas.notificaciones", level="ERROR") as registro:
            tasa = self.actualizar("103")
        self.assertTrue(TasaComercial.objects.get(pk=tasa.pk).vigente)
        self.assertEqual(self.base().compra, Decimal("100"))
        self.assertEqual(BaseNotificacionTasa.objects.get(destinatario_id="otro").compra, Decimal("103"))
        self.assertEqual(len(mail.outbox), 1)
        resultado = tasa.evento_notificacion.resultados.get(destinatario_id=USUARIO["id"])
        self.assertEqual((resultado.estado, resultado.error), ("FALLIDO", "envio_no_aceptado"))
        self.assertNotIn("SECRETO", " ".join(registro.output))
        self.actualizar("104")
        self.assertEqual(self.base().compra, Decimal("104"))
        self.assertEqual(len(mail.outbox), 2)

    def test_backend_no_acepta_mensaje_es_fallo(self):
        """Un backend que devuelve cero no es éxito: queda fallo y no avanza la base."""
        self.actualizar()
        with mock.patch("tasas.notificaciones.enviar_correo", return_value=0), self.assertLogs("tasas.notificaciones", level="ERROR"):
            tasa = self.actualizar("103")
        self.assertEqual(self.base().compra, Decimal("100"))
        self.assertEqual(tasa.evento_notificacion.resultados.get().estado, "FALLIDO")

    def test_fallo_keycloak_registrado_sin_revertir_tasa(self):
        """No obtener destinatarios registra el evento fallido sin correo ni pérdida de la nueva tasa."""
        self.actualizar()
        self.keycloak.side_effect = RuntimeError("TOKEN-no-exponer")
        with self.assertLogs("tasas.notificaciones", level="ERROR") as registro:
            tasa = self.actualizar("103")
        evento = tasa.evento_notificacion
        evento.refresh_from_db()
        self.assertEqual(evento.error_destinatarios, "consulta_keycloak_fallida")
        self.assertTrue(evento.procesado)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(TasaComercial.objects.get(pk=tasa.pk).vigente)
        self.assertNotIn("TOKEN", " ".join(registro.output))

    def test_rollback_no_envia_ni_persiste_evento(self):
        """Revertir la actualización descarta tasa, evento y callback antes de cualquier consulta o envío."""
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                actualizar_tasa_comercial(self.origen.pk, self.destino.pk, "analista", compra="100", venta="200")
                raise RuntimeError("revertir")
        self.assertFalse(EventoNotificacionTasa.objects.exists())
        self.assertFalse(TasaComercial.objects.exists())
        self.keycloak.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_evento_procesado_no_se_repite_y_bd_impide_resultado_duplicado(self):
        """Procesar otra vez la misma versión no envía; la BD impide repetir destinatario/evento."""
        self.actualizar()
        tasa = self.actualizar("103")
        procesar_evento(tasa.evento_notificacion.pk)
        self.assertEqual(len(mail.outbox), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResultadoNotificacionTasa.objects.create(evento=tasa.evento_notificacion, destinatario_id=USUARIO["id"])

    def test_umbral_nuevo_no_envia_retroactivo(self):
        """Guardar un umbral menor no envía; una actualización posterior usa ese criterio y la base acumulada."""
        self.actualizar()
        self.actualizar("102")
        configurar_umbral(valor="2", roles=["ADMINISTRADOR"])
        self.assertEqual(len(mail.outbox), 0)
        self.actualizar("102")
        self.assertEqual(len(mail.outbox), 1)

    def test_destinatarios_paginados_excluyen_cuentas_no_elegibles(self):
        """Se recorren todas las páginas y se excluyen inactivos, no verificados y emails inválidos."""
        pagina = [{**USUARIO, "id": f"usuario-{i}"} for i in range(100)]
        segunda = [{**USUARIO, "id": "inactivo", "enabled": False},
                   {**USUARIO, "id": "no-verificado", "emailVerified": False},
                   {**USUARIO, "id": "invalido", "email": "sin-arroba"},
                   {**USUARIO, "id": "ultima-pagina"}]
        self.keycloak.side_effect = [pagina, segunda]
        destinatarios = obtener_destinatarios()
        self.assertEqual(len(destinatarios), 101)
        self.assertIn("ultima-pagina", destinatarios)
        self.assertNotIn("inactivo", destinatarios)
        self.assertNotIn("no-verificado", destinatarios)
        self.assertNotIn("invalido", destinatarios)
        self.assertEqual(self.keycloak.call_args_list, [mock.call("/users?first=0&max=100"), mock.call("/users?first=100&max=100")])

    def test_tasas_referencia_no_generan_eventos(self):
        """Actualizar cotizaciones externas conserva el flujo existente y nunca dispara notificaciones comerciales."""
        from datetime import datetime, timezone
        from .providers import RespuestaTasas
        from .services import consultar_tasas_referencia
        Moneda.objects.exclude(pk__in=[self.origen.pk, self.destino.pk]).update(estado="INACTIVA")
        proveedor = mock.Mock()
        proveedor.obtener.return_value = RespuestaTasas(
            fuente="Prueba", moneda_base="USD", fecha_hora=datetime.now(timezone.utc),
            tasas={"PYG": Decimal("7200")}, respuesta_original={},
        )
        consultar_tasas_referencia(proveedor=proveedor)
        self.assertFalse(EventoNotificacionTasa.objects.exists())
        self.keycloak.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)


@override_settings(MAILERS=CORREO_PRUEBAS)
class ConfiguracionNotificacionesTests(TestCase):
    """Umbral global protegido por rol efectivo, validación backend y CSRF."""

    def setUp(self):
        ConfiguracionNotificacionTasa.objects.get_or_create(pk=1)
        self.url = reverse("tasas_web:configurar_notificaciones")
        self.autenticar(["ADMINISTRADOR"])

    def autenticar(self, roles):
        """Prepara una sesión externa vigente sin crear usuarios Django."""
        sesion = self.client.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = time.time() + 3600
        sesion[SESSION_ROLES] = roles
        sesion[SESSION_USUARIO] = {"sub": "admin-keycloak"}
        sesion.save()

    def test_administrador_guarda_por_post_y_recarga_sin_repetir(self):
        """ADMINISTRADOR multirrol cambia el umbral por POST y termina en GET con valor persistido."""
        self.autenticar(["CAJERO", "ADMINISTRADOR"])
        self.assertEqual(self.client.get(self.url).status_code, 200)
        respuesta = self.client.post(self.url, {"umbral_porcentaje": "2.5"}, follow=True)
        self.assertRedirects(respuesta, self.url)
        self.assertEqual(ConfiguracionNotificacionTasa.objects.get().umbral_porcentaje, Decimal("2.5"))

    def test_umbral_invalido_no_modifica_configuracion(self):
        """Vacío, texto, cero, negativo, no finito o precisión excesiva se rechazan sin guardar."""
        for valor in ("", "texto", "0", "-1", "NaN", "Infinity", "1.12345678901"):
            with self.subTest(valor=valor):
                respuesta = self.client.post(self.url, {"umbral_porcentaje": valor})
                self.assertEqual(respuesta.status_code, 400)
                self.assertTrue(respuesta.context["form"].errors)
        self.assertEqual(ConfiguracionNotificacionTasa.objects.get().umbral_porcentaje, Decimal("3"))

    def test_roles_no_autorizados_rechazados_en_vista_y_servicio(self):
        """USUARIO, CAJERO y ANALISTA/CAJERO no configuran por acceso directo ni servicio."""
        for roles in (["USUARIO"], ["CAJERO"], ["ANALISTA_CAMBIARIO", "CAJERO"]):
            with self.subTest(roles=roles):
                self.autenticar(roles)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, {"umbral_porcentaje": "1"}).status_code, 403)
                with self.assertRaises(PermissionDenied):
                    configurar_umbral(valor="1", roles=roles)
        self.assertEqual(ConfiguracionNotificacionTasa.objects.get().umbral_porcentaje, Decimal("3"))

    def test_sin_sesion_y_sin_csrf_no_guardan(self):
        """Sin sesión se redirige a login; una sesión autorizada sin CSRF no puede guardar."""
        cliente = Client(enforce_csrf_checks=True)
        cliente.cookies = self.client.cookies
        self.assertEqual(cliente.post(self.url, {"umbral_porcentaje": "1"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(ConfiguracionNotificacionTasa.objects.get().umbral_porcentaje, Decimal("3"))


@override_settings(MAILERS=CORREO_PRUEBAS)
class ConcurrenciaNotificacionesTests(TransactionTestCase):
    """Deduplicación real entre conexiones PostgreSQL, sin SMTP ni Keycloak externos."""

    def test_smtp_detenido_responde_guardado_y_no_reintenta_al_restaurar(self):
        """SMTP inaccesible se intenta una vez, falla para todos sin avanzar bases y responde 201 con advertencia."""
        origen = Moneda.objects.create(codigo="ERR", nombre="Error", simbolo="E")
        destino = Moneda.objects.create(codigo="ERU", nombre="Otra", simbolo="U")
        ConfiguracionNotificacionTasa.objects.get_or_create(pk=1)
        usuarios = [USUARIO, {**USUARIO, "id": "otro", "email": "otro@example.test"}]
        sesion = self.client.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = time.time() + 3600
        sesion[SESSION_ROLES] = ["ANALISTA_CAMBIARIO"]
        sesion[SESSION_USUARIO] = {"sub": "analista"}
        sesion.save()
        conexion = mock.Mock()
        conexion.open.side_effect = ConnectionError("dato-privado")
        with mock.patch("tasas.notificaciones.admin_request", return_value=usuarios):
            actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="100", venta="200")
            with mock.patch("tasas.notificaciones.mailers.create_connection", return_value=conexion) as crear, self.assertLogs("tasas.notificaciones", level="ERROR"):
                respuesta = self.client.post(reverse("tasas:administrar_tasa_comercial"),
                    json.dumps({"moneda_origen_id": origen.pk, "moneda_destino_id": destino.pk,
                                "compra": "103", "venta": "200"}), content_type="application/json")
                self.assertEqual(respuesta.status_code, 201)
                self.assertTrue(respuesta.json()["advertencia_notificaciones"])
                self.assertIn("La tasa se guardó", respuesta.json()["mensaje"])
                self.assertEqual(TasaComercial.objects.get(vigente=True).compra, Decimal("103"))
                evento = EventoNotificacionTasa.objects.get(tasa__vigente=True)
                self.assertEqual(evento.resultados.filter(estado="FALLIDO").count(), 2)
                self.assertEqual(list(BaseNotificacionTasa.objects.values_list("compra", flat=True)),
                                 [Decimal("100"), Decimal("100")])
                crear.assert_called_once()
                conexion.open.assert_called_once()
                # Restaurar el backend y consultar/reprocesar no envía el evento fallido.
                conexion.open.side_effect = None
                procesar_evento(evento.pk)
                self.client.get(reverse("tasas:historial_tasas_comerciales"))
                crear.assert_called_once()
                conexion.send_messages.assert_not_called()

    def test_callbacks_invertidas_respetan_orden_y_acumulacion(self):
        """Aunque llegue primero la última callback, las versiones confirmadas se evalúan en orden sin duplicar."""
        origen = Moneda.objects.create(codigo="ORD", nombre="Orden", simbolo="O")
        destino = Moneda.objects.create(codigo="ORU", nombre="Otra", simbolo="U")
        ConfiguracionNotificacionTasa.objects.get_or_create(pk=1)
        with mock.patch("tasas.notificaciones.procesar_evento"):
            actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="100", venta="200")
            intermedia = actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="102", venta="200")
            ultima = actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="103", venta="200")
        with mock.patch("tasas.notificaciones.admin_request", return_value=[USUARIO]):
            procesar_evento(ultima.evento_notificacion.pk)
            procesar_evento(intermedia.evento_notificacion.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(BaseNotificacionTasa.objects.get().compra, Decimal("103"))
        self.assertEqual(ResultadoNotificacionTasa.objects.filter(estado="SIN_CAMBIOS").count(), 2)

    def test_envio_ve_tasa_confirmada_y_no_bloquea_sus_filas(self):
        """Durante SMTP otra conexión puede leer y bloquear la nueva tasa: el commit ya ocurrió sin locks de tasas."""
        origen = Moneda.objects.create(codigo="LCK", nombre="Bloqueo", simbolo="L")
        destino = Moneda.objects.create(codigo="LCU", nombre="Otra", simbolo="U")
        ConfiguracionNotificacionTasa.objects.get_or_create(pk=1)

        def leer_tasa_confirmada():
            close_old_connections()
            try:
                with transaction.atomic():
                    tasa = TasaComercial.objects.select_for_update(nowait=True).get(vigente=True)
                    self.assertEqual(tasa.compra, Decimal("103"))
            finally:
                connections["default"].close()

        def enviar(*args, **kwargs):
            with ThreadPoolExecutor(max_workers=1) as ejecutor:
                ejecutor.submit(leer_tasa_confirmada).result(timeout=5)
            return 1

        with mock.patch("tasas.notificaciones.admin_request", return_value=[USUARIO]):
            actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="100", venta="200")
            with mock.patch("tasas.notificaciones.enviar_correo", side_effect=enviar) as correo:
                actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="103", venta="200")
        correo.assert_called_once()
        self.assertEqual(ResultadoNotificacionTasa.objects.get(estado="ENVIADO").error, "")

    def test_dos_callbacks_del_mismo_evento_envian_una_vez(self):
        """Dos procesos compiten por la misma actualización; solo uno envía y avanza su base."""
        origen = Moneda.objects.create(codigo="TST", nombre="Prueba", simbolo="T")
        destino = Moneda.objects.create(codigo="TSU", nombre="Otra", simbolo="U")
        ConfiguracionNotificacionTasa.objects.get_or_create(pk=1)
        with mock.patch("tasas.notificaciones.procesar_evento"):
            actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="100", venta="200")
            tasa = actualizar_tasa_comercial(origen.pk, destino.pk, "analista", compra="103", venta="200")
        evento = tasa.evento_notificacion
        barrera = Barrier(2)

        def procesar():
            close_old_connections()
            try:
                barrera.wait(timeout=5)
                procesar_evento(evento.pk)
            finally:
                connections["default"].close()

        with mock.patch("tasas.notificaciones.admin_request", return_value=[USUARIO]), mock.patch("tasas.notificaciones.enviar_correo", return_value=1) as envio:
            with ThreadPoolExecutor(max_workers=2) as ejecutor:
                futuros = [ejecutor.submit(procesar), ejecutor.submit(procesar)]
                for futuro in futuros:
                    futuro.result(timeout=10)
        envio.assert_called_once()
        self.assertEqual(ResultadoNotificacionTasa.objects.get(evento=evento).estado, "ENVIADO")
        self.assertEqual(BaseNotificacionTasa.objects.get().compra, Decimal("103"))
