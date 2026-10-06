import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from monedas.models import Moneda

from .models import Caja, PeriodoCaja, SaldoInicialCaja
from .services import abrir_caja, cambiar_estado_caja, firmar_catalogo, leer_catalogo
from .templatetags.importes_caja import importe_inicial
from usuarios.services.keycloak import SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO


class RestriccionesAperturaTests(TestCase):
    """Protege las invariantes estructurales de HU-39 directamente en PostgreSQL."""

    def setUp(self):
        self.caja = Caja.objects.create(
            codigo="ESTRUCTURA", nombre="Caja de prueba",
            creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin",
        )
        self.moneda = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"},
        )[0]
        self.periodo = PeriodoCaja.objects.create(caja=self.caja, responsable_keycloak_id="cajero")

    def test_base_de_datos_impide_dos_periodos_abiertos(self):
        """La misma caja no admite una segunda apertura activa incluso sin usar el servicio."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodoCaja.objects.create(caja=self.caja, responsable_keycloak_id="otro")
        self.assertEqual(PeriodoCaja.objects.filter(caja=self.caja).count(), 1)

    def test_base_de_datos_impide_moneda_repetida_en_periodo(self):
        """Cada período conserva un único saldo inicial por moneda."""
        SaldoInicialCaja.objects.create(periodo=self.periodo, moneda=self.moneda, monto=Decimal("0"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaldoInicialCaja.objects.create(periodo=self.periodo, moneda=self.moneda, monto=Decimal("1"))
        self.assertEqual(self.periodo.saldos_iniciales.count(), 1)

    def test_base_de_datos_impide_saldo_negativo(self):
        """Un monto negativo se rechaza en la BD aunque se omita la validación del formulario."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaldoInicialCaja.objects.create(periodo=self.periodo, moneda=self.moneda, monto=Decimal("-1"))
        self.assertFalse(self.periodo.saldos_iniciales.exists())

    def test_saldo_historico_se_conserva_al_desactivar_moneda(self):
        """Desactivar una moneda no modifica el saldo inicial y las relaciones impiden borrados."""
        saldo = SaldoInicialCaja.objects.create(
            periodo=self.periodo, moneda=self.moneda, monto=Decimal("123.456789"),
        )
        self.moneda.desactivar()
        saldo.refresh_from_db()
        self.assertEqual(saldo.monto, Decimal("123.456789"))
        with self.assertRaises(ProtectedError):
            self.moneda.delete()
        with self.assertRaises(ProtectedError):
            self.periodo.delete()
        with self.assertRaises(ProtectedError):
            self.caja.delete()


class AperturaCajaTests(TestCase):
    """Reglas de HU-39 con importes exactos, identidad externa y catálogo firmado."""

    def setUp(self):
        self.caja = Caja.objects.create(
            codigo="APERTURA", nombre="Caja de prueba",
            creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin",
        )
        Moneda.objects.all().update(estado="INACTIVA")
        self.usd = Moneda.objects.get_or_create(codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"})[0]
        self.pyg = Moneda.objects.get_or_create(codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"})[0]
        self.usd.activar()
        self.pyg.activar()
        self.parametros = {
            "caja_id": self.caja.id,
            "catalogo": firmar_catalogo(self.caja.id, [self.usd, self.pyg]),
            "saldos": [{"moneda_id": self.usd.id, "monto": "100.123456"}, {"moneda_id": self.pyg.id, "monto": "2000"}],
            "usuario_id": "cajero-keycloak", "username": "elena", "roles": ["CAJERO"],
        }
        sesion = self.client.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = time.time() + 3600
        sesion[SESSION_ROLES] = ["CAJERO"]
        sesion[SESSION_USUARIO] = {"sub": "cajero-keycloak", "username": "elena"}
        sesion.save()

    def abrir(self, **cambios):
        """Invoca el servicio con la captura explícita del escenario."""
        return abrir_caja(**{**self.parametros, **cambios})

    def rechazar_monto(self, monto):
        """Verifica rechazo monetario sin período ni importes persistidos."""
        saldos = [{"moneda_id": self.usd.id, "monto": monto}, self.parametros["saldos"][1]]
        with self.assertRaises(ValidationError):
            self.abrir(saldos=saldos)
        self.assertFalse(PeriodoCaja.objects.exists())
        self.assertFalse(SaldoInicialCaja.objects.exists())

    def datos_post(self, **cambios):
        """Construye el POST que confirma, conservando el dato firmado mostrado."""
        return {"catalogo": self.parametros["catalogo"], "accion": "confirmar",
                f"monto_{self.usd.id}": "100.123456", f"monto_{self.pyg.id}": "2000", **cambios}

    def test_todos_saldos_cero_permitidos(self):
        """Importes explícitos en cero para todas las monedas permiten iniciar un período."""
        periodo = self.abrir(saldos=[{"moneda_id": self.usd.id, "monto": "0"}, {"moneda_id": self.pyg.id, "monto": "0"}])
        self.assertEqual(list(periodo.saldos_iniciales.values_list("monto", flat=True)), [Decimal("0"), Decimal("0")])

    def test_caja_deshabilitada_no_abre(self):
        """Una caja deshabilitada no se lista y su apertura directa se rechaza sin registros."""
        self.caja.estado = "DESHABILITADA"
        self.caja.save()
        with self.assertRaisesMessage(ValidationError, "deshabilitada"):
            self.abrir()
        self.assertNotContains(self.client.get(reverse("cajas:operar")), self.caja.codigo)
        respuesta = self.client.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post(), follow=True)
        self.assertContains(respuesta, "La caja se encuentra deshabilitada.", status_code=400)
        self.assertFalse(PeriodoCaja.objects.exists())
        self.assertFalse(SaldoInicialCaja.objects.exists())

    def test_segunda_apertura_rechazada(self):
        """Una caja abierta no admite otra apertura y conserva sus saldos originales."""
        periodo = self.abrir()
        originales = list(periodo.saldos_iniciales.values_list("moneda_id", "monto"))
        with self.assertRaisesMessage(ValidationError, "período abierto"):
            self.abrir()
        self.assertEqual(PeriodoCaja.objects.count(), 1)
        self.assertEqual(SaldoInicialCaja.objects.count(), 2)
        self.assertEqual(list(periodo.saldos_iniciales.values_list("moneda_id", "monto")), originales)

    def test_sin_monedas_activas_no_abre(self):
        """Sin monedas activas se informa el problema y no se crea un período vacío."""
        Moneda.objects.all().update(estado="INACTIVA")
        with self.assertRaisesMessage(ValidationError, "No hay monedas activas"):
            self.abrir(catalogo=firmar_catalogo(self.caja.id, []), saldos=[])
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_monto_negativo(self):
        """Un saldo negativo se rechaza sin persistir apertura."""
        self.rechazar_monto("-0.000001")

    def test_monto_no_finito(self):
        """NaN e infinito incumplen la finitud exigida: ninguno crea período ni saldos."""
        self.rechazar_monto("NaN")
        self.rechazar_monto("Infinity")

    def test_monto_fuera_rango(self):
        """Un importe con trece dígitos enteros excede DecimalField(18, 6)."""
        self.rechazar_monto("1000000000000")

    def test_monto_exceso_decimales_no_redondeado(self):
        """Siete posiciones decimales se rechazan incluso si la última es cero."""
        self.rechazar_monto("1.1234560")

    def test_monto_maximo_exacto_y_presentacion_completa(self):
        """El máximo representable conserva sus seis decimales sin pérdida por float."""
        periodo = self.abrir(saldos=[{"moneda_id": self.usd.id, "monto": "999999999999.999999"}, self.parametros["saldos"][1]])
        saldo = periodo.saldos_iniciales.get(moneda=self.usd)
        self.assertEqual(saldo.monto, Decimal("999999999999.999999"))
        self.assertEqual(importe_inicial(saldo.monto), "999.999.999.999,999999")

    def test_moneda_omitida_no_completa_cero(self):
        """Omitir una moneda activa invalida la apertura, sin completar cero implícito."""
        with self.assertRaises(ValidationError):
            self.abrir(saldos=self.parametros["saldos"][:1])
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_moneda_repetida_rechazada(self):
        """Un saldo duplicado por moneda invalida toda la apertura."""
        with self.assertRaisesMessage(ValidationError, "repetir"):
            self.abrir(saldos=self.parametros["saldos"] + [self.parametros["saldos"][0]])
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_moneda_inactiva_no_se_acepta(self):
        """Añadir una moneda inactiva a una captura válida no permite persistir."""
        inactiva = Moneda.objects.create(codigo="ZZZ", nombre="Inactiva", simbolo="Z", estado="INACTIVA")
        with self.assertRaises(ValidationError):
            self.abrir(saldos=self.parametros["saldos"] + [{"moneda_id": inactiva.id, "monto": "0"}])
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_firma_manipulada_rechazada(self):
        """Alterar la firma del catálogo no permite guardar apertura o saldos."""
        with self.assertRaises(ValidationError):
            self.abrir(catalogo=self.parametros["catalogo"] + "manipulado")
        self.assertFalse(PeriodoCaja.objects.exists())
        self.assertFalse(SaldoInicialCaja.objects.exists())

    def test_cambio_conjunto_activo_rechazado(self):
        """Activar una moneda después de mostrar el formulario exige nueva revisión."""
        Moneda.objects.create(codigo="ZZZ", nombre="Nueva", simbolo="Z")
        with self.assertRaisesMessage(ValidationError, "Las monedas disponibles cambiaron. Revisa los saldos y confirma nuevamente."):
            self.abrir()
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_cambio_codigo_rechazado(self):
        """Cambiar un código mostrado invalida el dato relevante del catálogo."""
        self.usd.codigo = "USX"
        self.usd.save()
        with self.assertRaisesMessage(ValidationError, "Las monedas disponibles cambiaron. Revisa los saldos y confirma nuevamente."):
            self.abrir()
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_nombre_simbolo_y_orden_no_invalidan(self):
        """Los pares coincidentes permiten abrir aunque cambien presentación y orden del dato firmado."""
        self.usd.nombre = "Nombre actualizado"
        self.usd.simbolo = "US$"
        self.usd.save()
        from django.core import signing
        from .services import SAL_CATALOGO
        token = signing.dumps({"caja": self.caja.id, "monedas": [[self.pyg.id, self.pyg.codigo], [self.usd.id, self.usd.codigo]]}, salt=SAL_CATALOGO)
        self.assertEqual(self.abrir(catalogo=token).saldos_iniciales.count(), 2)

    def test_cambio_revertido_no_invalida(self):
        """Desactivar y reactivar antes de confirmar no invalida pares nuevamente coincidentes."""
        self.usd.desactivar()
        self.usd.activar()
        self.assertEqual(self.abrir().saldos_iniciales.count(), 2)

    def test_cambio_posterior_a_consulta_no_invalida(self):
        """Un cambio posterior al instante acordado no modifica los saldos históricos guardados."""
        guardar = PeriodoCaja.save

        def guardar_tras_cambio(instancia, *args, **kwargs):
            Moneda.objects.filter(pk=self.usd.id).update(estado="INACTIVA")
            return guardar(instancia, *args, **kwargs)

        with mock.patch.object(PeriodoCaja, "save", guardar_tras_cambio):
            periodo = self.abrir()
        self.assertEqual(periodo.saldos_iniciales.get(moneda=self.usd).monto, Decimal("100.123456"))

    def test_integrityerror_ajeno_no_se_convierte_en_caja_abierta(self):
        """Un error de integridad ajeno se propaga y revierte sin inventar otra apertura."""
        with mock.patch.object(SaldoInicialCaja, "save", side_effect=IntegrityError("otro error")):
            with self.assertRaises(IntegrityError):
                self.abrir()
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_deshabilitacion_con_periodo_abierto_rechazada(self):
        """El administrador no deshabilita una caja abierta y conserva estado y período."""
        self.abrir()
        with self.assertRaisesMessage(ValidationError, "período abierto"):
            cambiar_estado_caja(caja_id=self.caja.id, estado="DESHABILITADA", usuario_id="admin", roles=["ADMINISTRADOR"])
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.estado, "HABILITADA")
        self.assertEqual(PeriodoCaja.objects.count(), 1)

    def test_cajero_usuario_multirrol_puede_operar(self):
        """CAJERO prevalece sobre USUARIO y puede abrir según el acuerdo global."""
        self.assertEqual(self.abrir(roles=["USUARIO", "CAJERO"]).estado, "ABIERTO")

    def _rechazar_roles(self, roles):
        """Comprueba servicio y rutas directas sin persistencia para roles no operativos."""
        with self.assertRaises(PermissionDenied):
            self.abrir(roles=roles)
        sesion = self.client.session
        sesion[SESSION_ROLES] = roles
        sesion.save()
        self.assertEqual(self.client.get(reverse("cajas:operar")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cajas:apertura", args=[self.caja.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post()).status_code, 403)
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_usuario_no_abre(self):
        """USUARIO no tiene autorización de cajero en vistas ni servicio."""
        self._rechazar_roles(["USUARIO"])

    def test_administrador_cajero_no_actua_como_cajero(self):
        """ADMINISTRADOR prevalece sobre CAJERO y no abre cajas en modo operativo."""
        self._rechazar_roles(["CAJERO", "ADMINISTRADOR"])

    def test_analista_cajero_no_actua_como_cajero(self):
        """ANALISTA prevalece sobre CAJERO y no abre cajas en modo operativo."""
        self._rechazar_roles(["CAJERO", "ANALISTA_CAMBIARIO"])

    def test_identidad_vacia_rechazada(self):
        """El servicio exige identidad Keycloak aunque se indiquen roles permitidos."""
        with self.assertRaises(ValidationError):
            self.abrir(usuario_id="")
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_revision_edicion_y_apertura_exacta_con_identidad_del_servidor(self):
        """Capturar, revisar y editar no escriben; confirmar guarda saldos e identidad y fecha no suplantables."""
        url = reverse("cajas:apertura", args=[self.caja.id])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertFalse(PeriodoCaja.objects.exists())
        respuesta = self.client.post(url, self.datos_post(accion="revisar"))
        self.assertContains(respuesta, "100,123456")
        self.assertFalse(PeriodoCaja.objects.exists())
        respuesta = self.client.post(url, self.datos_post(accion="editar"))
        self.assertContains(respuesta, 'value="100.123456"')
        self.assertContains(respuesta, 'value="2000"')
        self.assertFalse(PeriodoCaja.objects.exists())
        self.assertFalse(SaldoInicialCaja.objects.exists())
        antes = timezone.now()
        respuesta = self.client.post(url, self.datos_post(
            responsable_keycloak_id="suplantado", responsable_username="suplantado",
            fecha_apertura="2000-01-01T00:00:00Z",
        ))
        periodo = PeriodoCaja.objects.get()
        self.assertRedirects(respuesta, reverse("cajas:apertura_confirmada", args=[periodo.id]))
        self.assertEqual(periodo.responsable_keycloak_id, "cajero-keycloak")
        self.assertEqual(periodo.responsable_username, "elena")
        self.assertEqual(periodo.estado, "ABIERTO")
        self.assertGreaterEqual(periodo.fecha_apertura, antes)
        self.assertLessEqual(periodo.fecha_apertura, timezone.now())
        self.assertEqual(dict(periodo.saldos_iniciales.values_list("moneda_id", "monto")), {
            self.usd.id: Decimal("100.123456"), self.pyg.id: Decimal("2000"),
        })
        self.assertContains(self.client.get(respuesta.url), "100,123456")

    def test_post_sin_csrf_rechazado(self):
        """La sesión permitida no basta para confirmar sin token CSRF."""
        cliente = Client(enforce_csrf_checks=True)
        cliente.cookies = self.client.cookies
        self.assertEqual(cliente.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post()).status_code, 403)
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_omision_web_informa_sin_completar_importe(self):
        """El formulario rechaza el importe omitido en vez de convertirlo en cero."""
        datos = self.datos_post()
        del datos[f"monto_{self.usd.id}"]
        respuesta = self.client.post(reverse("cajas:apertura", args=[self.caja.id]), datos)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn(f"monto_{self.usd.id}", respuesta.context["form"].errors)
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_campo_moneda_repetido_en_post_rechazado(self):
        """Dos valores para la misma moneda en POST no se reducen silenciosamente al último."""
        respuesta = self.client.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post(**{
            f"monto_{self.usd.id}": ["1", "2"],
        }))
        self.assertContains(respuesta, "No se permite repetir monedas", status_code=400)
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_dato_firmado_manipulado_web_actualiza_formulario(self):
        """Un dato alterado muestra error y formulario revisable sin guardar registros."""
        respuesta = self.client.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post(catalogo="alterado"))
        self.assertContains(respuesta, "El catálogo mostrado no es válido", status_code=400)
        self.assertEqual(
            leer_catalogo(self.caja.id, respuesta.context["form"].initial["catalogo"]),
            sorted([[self.usd.id, self.usd.codigo], [self.pyg.id, self.pyg.codigo]]),
        )
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_sin_sesion_no_accede_a_apertura(self):
        """Sin identidad autenticada las rutas redirigen a login y no ejecutan apertura."""
        self.client.logout()
        self.assertEqual(self.client.get(reverse("cajas:operar")).status_code, 302)
        self.assertEqual(self.client.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post()).status_code, 302)
        self.assertFalse(PeriodoCaja.objects.exists())

    def test_deshabilitacion_web_rechazada_con_periodo_abierto(self):
        """Deshabilitar una caja abierta redirige a GET con aviso único; recargar conserva caja y período."""
        self.abrir()
        sesion = self.client.session
        sesion[SESSION_ROLES] = ["ADMINISTRADOR"]
        sesion.save()
        respuesta = self.client.post(reverse("cajas:cambiar_estado", args=[self.caja.id]), {"estado": "DESHABILITADA"}, follow=True)
        self.assertRedirects(respuesta, reverse("cajas:inicio"))
        self.assertEqual(respuesta.request["REQUEST_METHOD"], "GET")
        aviso = "No se puede deshabilitar la caja porque tiene un período abierto."
        self.assertContains(respuesta, aviso, count=1)
        self.assertContains(respuesta, 'class="message error"')
        recarga = self.client.get(reverse("cajas:inicio"))
        self.assertEqual(recarga.status_code, 200)
        self.assertNotContains(recarga, aviso)
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.estado, "HABILITADA")
        self.assertEqual(PeriodoCaja.objects.get().estado, "ABIERTO")
        self.assertEqual(SaldoInicialCaja.objects.count(), 2)

    def test_catalogo_cambiado_web_pide_revision_actualizada(self):
        """El formulario obsoleto se sustituye por el catálogo actual sin abrir la caja."""
        nueva = Moneda.objects.create(codigo="ZZZ", nombre="Nueva", simbolo="Z")
        respuesta = self.client.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post(), follow=True)
        self.assertContains(respuesta, '<div class="ge-error-banner" role="alert">Las monedas disponibles cambiaron. Revisa los saldos y confirma nuevamente.</div>', status_code=400, html=True)
        self.assertContains(respuesta, f'name="monto_{nueva.id}"', status_code=400)
        self.assertContains(respuesta, 'up-submit="false"', status_code=400)
        self.assertFalse(respuesta.context["confirmar"])
        self.assertEqual(leer_catalogo(self.caja.id, respuesta.context["form"].initial["catalogo"]),
                         sorted([[self.usd.id, self.usd.codigo], [self.pyg.id, self.pyg.codigo], [nueva.id, nueva.codigo]]))
        self.assertFalse(PeriodoCaja.objects.exists())
        self.assertFalse(SaldoInicialCaja.objects.exists())

    def test_error_web_seguro_y_sin_parciales(self):
        """Fallar tras escribir un saldo revierte todo en servicio y vista; HTTP informa sin detalles internos."""
        guardar = SaldoInicialCaja.save

        def guardar_y_fallar(instancia, *args, **kwargs):
            guardar(instancia, *args, **kwargs)
            raise RuntimeError("PRIVADO")

        with mock.patch.object(SaldoInicialCaja, "save", guardar_y_fallar):
            with self.assertRaises(RuntimeError):
                self.abrir()
            self.assertFalse(PeriodoCaja.objects.exists())
            self.assertFalse(SaldoInicialCaja.objects.exists())
            with self.assertLogs("cajas.views", level="ERROR"):
                respuesta = self.client.post(reverse("cajas:apertura", args=[self.caja.id]), self.datos_post())
        self.assertContains(respuesta, "No fue posible abrir la caja", status_code=500)
        self.assertNotContains(respuesta, "PRIVADO", status_code=500)
        self.assertFalse(PeriodoCaja.objects.exists())
        self.assertFalse(SaldoInicialCaja.objects.exists())

    def test_confirmacion_no_expone_periodo_de_otro_cajero(self):
        """La confirmación permite consultar solo el período del cajero responsable."""
        periodo = self.abrir(usuario_id="otro-cajero")
        self.assertEqual(self.client.get(reverse("cajas:apertura_confirmada", args=[periodo.id])).status_code, 404)


class ConcurrenciaAperturaTests(TransactionTestCase):
    """Prueba carreras reales con conexiones independientes del entorno PostgreSQL."""

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        Moneda.objects.all().update(estado="INACTIVA")
        self.caja = Caja.objects.create(codigo="CARRERA", nombre="Caja concurrente", creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin")
        self.moneda = Moneda.objects.create(codigo="TST", nombre="Prueba", simbolo="T")
        self.datos = {"caja_id": self.caja.id, "catalogo": firmar_catalogo(self.caja.id, [self.moneda]),
                      "saldos": [{"moneda_id": self.moneda.id, "monto": "10"}],
                      "usuario_id": "cajero", "roles": ["CAJERO"]}

    def _abrir(self):
        """Confirma la captura preparada en la conexión de quien invoque."""
        return abrir_caja(**self.datos)

    def _deshabilitar(self):
        """Solicita el cambio administrativo sobre la misma caja."""
        return cambiar_estado_caja(caja_id=self.caja.id, estado="DESHABILITADA", usuario_id="admin", roles=["ADMINISTRADOR"])

    def test_dos_aperturas_concurrentes_solo_una_exitosa(self):
        """Dos solicitudes compiten: una abre y la otra se rechaza por período abierto."""
        barrera = Barrier(2)

        def competir():
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                barrera.wait(timeout=5)
                try:
                    self._abrir()
                    return "abierta"
                except ValidationError as error:
                    return error.code
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            primero = ejecutor.submit(competir)
            segundo = ejecutor.submit(competir)
            resultados = [primero.result(timeout=10), segundo.result(timeout=10)]
        self.assertCountEqual(resultados, ["abierta", "caja_abierta"])
        self.assertEqual(PeriodoCaja.objects.count(), 1)
        self.assertEqual(SaldoInicialCaja.objects.count(), 1)

    def _carrera_ordenada(self, primera_accion, segunda_accion):
        """Fuerza ambos órdenes manteniendo la segunda conexión realmente bloqueada."""
        listo = Event()
        pid = []

        def segunda_conexion():
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pid.append(cursor.fetchone()[0])
                listo.set()
                try:
                    segunda_accion()
                    return "aceptada"
                except ValidationError:
                    return "rechazada"
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=1) as ejecutor:
            with transaction.atomic():
                Caja.objects.select_for_update().get(pk=self.caja.id)
                futuro = ejecutor.submit(segunda_conexion)
                self.assertTrue(listo.wait(5))
                bloqueado = False
                limite = time.monotonic() + 4
                while time.monotonic() < limite:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [pid[0]])
                        fila = cursor.fetchone()
                    if fila and fila[0] == "Lock":
                        bloqueado = True
                        break
                    if futuro.done():
                        break
                    time.sleep(0.01)
                self.assertTrue(bloqueado)
                primera_accion()
            self.assertEqual(futuro.result(timeout=10), "rechazada")

    def test_apertura_primero_impide_deshabilitacion_concurrente(self):
        """Si apertura obtiene el bloqueo primero, la deshabilitación posterior es rechazada."""
        self._carrera_ordenada(self._abrir, self._deshabilitar)
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.estado, "HABILITADA")
        self.assertEqual(PeriodoCaja.objects.filter(estado="ABIERTO").count(), 1)

    def test_deshabilitacion_primero_impide_apertura_concurrente(self):
        """Si deshabilitación obtiene el bloqueo primero, la apertura posterior no guarda nada."""
        self._carrera_ordenada(self._deshabilitar, self._abrir)
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.estado, "DESHABILITADA")
        self.assertFalse(PeriodoCaja.objects.exists())
        self.assertFalse(SaldoInicialCaja.objects.exists())
