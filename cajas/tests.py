import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.services.keycloak import (
    SESSION_AUTENTICADO, SESSION_EXPIRA_EN, SESSION_ROLES, SESSION_USUARIO,
)

from .models import Caja
from .services import cambiar_estado_caja, crear_caja


class CajaTests(TestCase):
    """Protege las reglas de registro y configuración de HU-38 / RF-28."""

    def setUp(self):
        self.identidad = {"usuario_id": "admin-keycloak", "roles": ["ADMINISTRADOR"]}
        sesion = self.client.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_EXPIRA_EN] = time.time() + 3600
        sesion[SESSION_ROLES] = ["ADMINISTRADOR"]
        sesion[SESSION_USUARIO] = {"sub": "admin-keycloak", "preferred_username": "elena"}
        sesion.save()

    def crear(self, **datos):
        """Invoca el servicio con la identidad administradora del escenario."""
        return crear_caja(**{"codigo": " caja-01 ", "nombre": " Principal ", **self.identidad, **datos})

    def test_registro_normalizado_y_autor_desde_sesion(self):
        """Un administrador registra una caja; se normaliza y no acepta autor del formulario."""
        antes = timezone.now()
        respuesta = self.client.post(reverse("cajas:crear"), {
            "codigo": " caja-01 ", "nombre": " Principal ", "estado": "HABILITADA",
            "creado_por_keycloak_id": "suplantado",
            "creado_por_username": "suplantado",
            "actualizado_por_keycloak_id": "suplantado",
            "fecha_registro": "2000-01-01T00:00:00Z",
            "fecha_actualizacion": "2000-01-01T00:00:00Z",
        })
        self.assertRedirects(respuesta, reverse("cajas:inicio"))
        caja = Caja.objects.get()
        self.assertEqual((caja.codigo, caja.nombre), ("CAJA-01", "Principal"))
        self.assertEqual(caja.creado_por_keycloak_id, "admin-keycloak")
        self.assertEqual(caja.creado_por_username, "elena")
        self.assertEqual(caja.actualizado_por_keycloak_id, "admin-keycloak")
        self.assertGreaterEqual(caja.fecha_registro, antes)
        self.assertLessEqual(caja.fecha_actualizacion, timezone.now())

    def test_codigo_duplicado_rechazado(self):
        """Un código equivalente por espacios o mayúsculas no crea una segunda caja."""
        self.crear()
        with self.assertRaises(ValidationError):
            self.crear(codigo="CAJA-01")
        self.assertEqual(Caja.objects.count(), 1)

    def test_codigo_obligatorio_en_formulario(self):
        """Un código compuesto por espacios devuelve errores y no registra una caja."""
        respuesta = self.client.post(reverse("cajas:crear"), {
            "codigo": "   ", "nombre": "Principal", "estado": "HABILITADA",
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("codigo", respuesta.context["form"].errors)
        self.assertFalse(Caja.objects.exists())

    def test_duplicado_web_informa_sin_crear_registro(self):
        """Un identificador equivalente se informa en el formulario sin duplicar la caja."""
        self.crear()
        respuesta = self.client.post(reverse("cajas:crear"), {
            "codigo": " caja-01 ", "nombre": "Otra", "estado": "HABILITADA",
        })
        self.assertContains(respuesta, "Ya existe una caja con ese código.", status_code=400)
        self.assertEqual(Caja.objects.count(), 1)

    def test_longitud_maxima_validada(self):
        """Un identificador fuera de capacidad se rechaza antes de escribir en la BD."""
        with self.assertRaises(ValidationError):
            self.crear(codigo="X" * 31)
        self.assertFalse(Caja.objects.exists())

    def test_creacion_deshabilitada(self):
        """El administrador puede registrar directamente una caja deshabilitada."""
        caja = self.crear(estado="DESHABILITADA")
        self.assertEqual(caja.estado, "DESHABILITADA")
        self.assertFalse(Caja.objects.habilitadas().exists())

    def test_unicidad_protegida_en_base_de_datos(self):
        """La BD impide duplicados incluso cuando se omite la validación del servicio."""
        self.crear()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Caja.objects.create(codigo="CAJA-01", nombre="Otra", creado_por_keycloak_id="admin")

    def test_datos_obligatorios_no_crean_caja(self):
        """Nombre vacío tras quitar espacios invalida el registro sin guardar datos."""
        with self.assertRaises(ValidationError):
            self.crear(nombre="   ")
        self.assertFalse(Caja.objects.exists())

    def test_estado_invalido_rechazado(self):
        """No se aceptan estados operativos como ABIERTO en el catálogo de cajas."""
        with self.assertRaises(ValidationError):
            self.crear(estado="ABIERTO")
        self.assertFalse(Caja.objects.exists())

    def test_identidad_obligatoria(self):
        """Sin identidad Keycloak el servicio rechaza el registro antes de persistir."""
        with self.assertRaises(ValidationError):
            self.crear(usuario_id="")
        self.assertFalse(Caja.objects.exists())

    def test_cajero_no_configura_por_servicio(self):
        """El rol CAJERO no puede crear ni deshabilitar cajas mediante los servicios."""
        caja = self.crear()
        with self.assertRaises(PermissionDenied):
            self.crear(codigo="otra", roles=["CAJERO"])
        with self.assertRaises(PermissionDenied):
            cambiar_estado_caja(caja_id=caja.id, estado="DESHABILITADA", usuario_id="cajero", roles=["CAJERO"])
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "HABILITADA")

    def test_habilitar_y_deshabilitar_conserva_registro(self):
        """Cambiar la habilitación conserva la caja, autor y fecha de registro."""
        caja = self.crear()
        fecha = caja.fecha_registro
        cambiar_estado_caja(caja_id=caja.id, estado="DESHABILITADA", **self.identidad)
        self.assertFalse(Caja.objects.habilitadas().exists())
        cambiar_estado_caja(caja_id=caja.id, estado="HABILITADA", **self.identidad)
        caja.refresh_from_db()
        self.assertEqual(caja.fecha_registro, fecha)
        self.assertEqual(Caja.objects.habilitadas().get().pk, caja.pk)

    def test_catalogo_y_formulario_accesibles_al_administrador(self):
        """El administrador ve el catálogo real y el formulario de creación integrado."""
        caja = self.crear()
        self.assertContains(self.client.get(reverse("cajas:inicio")), caja.codigo)
        self.assertContains(self.client.get(reverse("cajas:crear")), 'name="codigo"')

    def test_estado_invalido_no_altera_caja(self):
        """Un estado enviado fuera de las opciones devuelve 400 y conserva la caja."""
        caja = self.crear()
        respuesta = self.client.post(reverse("cajas:cambiar_estado", args=[caja.id]), {
            "estado": "ABIERTO",
        })
        self.assertEqual(respuesta.status_code, 400)
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "HABILITADA")

    def test_ultimo_cambio_registra_actor_sin_reemplazar_creador(self):
        """Otro administrador cambia habilitación y queda identificado sin alterar el autor inicial."""
        caja = self.crear()
        cambiar_estado_caja(caja_id=caja.id, estado="DESHABILITADA",
                           usuario_id="otro-admin", roles=["ADMINISTRADOR"])
        caja.refresh_from_db()
        self.assertEqual(caja.actualizado_por_keycloak_id, "otro-admin")
        self.assertEqual(caja.creado_por_keycloak_id, "admin-keycloak")

    def test_fallo_despues_de_guardar_revierte_registro(self):
        """Un fallo posterior a la escritura dentro del servicio revierte la creación."""
        guardar = Caja.save

        def guardar_y_fallar(instancia, *args, **kwargs):
            guardar(instancia, *args, **kwargs)
            raise RuntimeError("Fallo simulado después de escribir")

        with mock.patch.object(Caja, "save", guardar_y_fallar):
            with self.assertRaises(RuntimeError):
                self.crear()
        self.assertFalse(Caja.objects.exists())

    def test_acceso_web_cajero_denegado(self):
        """CAJERO recibe 403 en consulta, registro y cambio de estado; no se escribe."""
        self._comprobar_rutas_denegadas(["CAJERO"])

    def test_multirrol_mantiene_prioridad_administrador(self):
        """ADMINISTRADOR sigue gestionando cajas cuando también posee rol CAJERO."""
        sesion = self.client.session
        sesion[SESSION_ROLES] = ["CAJERO", "ADMINISTRADOR"]
        sesion.save()
        self.assertEqual(self.client.get(reverse("cajas:inicio")).status_code, 200)
        respuesta = self.client.post(reverse("cajas:crear"), {
            "codigo": "MULTI", "nombre": "Multirrol", "estado": "HABILITADA",
        })
        self.assertEqual(respuesta.status_code, 302)
        caja = Caja.objects.get(codigo="MULTI")
        self.assertEqual(self.client.post(reverse("cajas:cambiar_estado", args=[caja.id]), {
            "estado": "DESHABILITADA",
        }).status_code, 302)

    def _comprobar_rutas_denegadas(self, roles):
        """Comprueba todas las entradas web, incluyendo ambos cambios de estado."""
        caja = self.crear()
        sesion = self.client.session
        sesion[SESSION_ROLES] = roles
        sesion.save()
        self.assertEqual(self.client.get(reverse("cajas:inicio")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cajas:crear")).status_code, 403)
        self.assertEqual(self.client.post(reverse("cajas:crear"), {
            "codigo": "NO-AUTORIZADA", "nombre": "Otra", "estado": "HABILITADA",
        }).status_code, 403)
        self.assertEqual(self.client.post(reverse("cajas:cambiar_estado", args=[caja.id]), {
            "estado": "DESHABILITADA",
        }).status_code, 403)
        caja.estado = "DESHABILITADA"
        caja.save()
        self.assertEqual(self.client.post(reverse("cajas:cambiar_estado", args=[caja.id]), {
            "estado": "HABILITADA",
        }).status_code, 403)
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "DESHABILITADA")
        self.assertEqual(Caja.objects.count(), 1)

    def test_usuario_sin_autorizacion_en_todas_las_rutas(self):
        """USUARIO no consulta, crea, habilita ni deshabilita por acceso directo."""
        self._comprobar_rutas_denegadas(["USUARIO"])

    def test_analista_sin_autorizacion_en_todas_las_rutas(self):
        """ANALISTA_CAMBIARIO mantiene su ámbito y no configura cajas."""
        self._comprobar_rutas_denegadas(["ANALISTA_CAMBIARIO"])

    def test_multirrol_sin_administrador_no_configura(self):
        """La combinación ANALISTA/CAJERO no concede acceso de administrador."""
        self._comprobar_rutas_denegadas(["CAJERO", "ANALISTA_CAMBIARIO"])

    def test_sesion_expirada_no_registra_caja(self):
        """Una sesión vencida se redirige a login y no ejecuta el registro."""
        sesion = self.client.session
        sesion[SESSION_EXPIRA_EN] = time.time() - 60
        sesion.save()
        self.assertEqual(self.client.post(reverse("cajas:crear"), {
            "codigo": "VENCIDA", "nombre": "Otra", "estado": "HABILITADA",
        }).status_code, 302)
        self.assertFalse(Caja.objects.exists())

    def test_creacion_requiere_csrf(self):
        """Un POST de creación sin token CSRF se rechaza aunque la sesión sea administradora."""
        cliente = Client(enforce_csrf_checks=True)
        cliente.cookies = self.client.cookies
        self.assertEqual(cliente.post(reverse("cajas:crear"), {
            "codigo": "CSRF", "nombre": "Otra", "estado": "HABILITADA",
        }).status_code, 403)
        self.assertFalse(Caja.objects.exists())

    def test_error_registro_informa_y_revierte_sin_exponer_detalles(self):
        """Un fallo después de guardar se revierte y la vista muestra un mensaje seguro."""
        guardar = Caja.save

        def guardar_y_fallar(instancia, *args, **kwargs):
            guardar(instancia, *args, **kwargs)
            raise RuntimeError("DETALLE_INTERNO_PRIVADO")

        with mock.patch.object(Caja, "save", guardar_y_fallar), self.assertLogs("cajas.views", level="ERROR"):
            respuesta = self.client.post(reverse("cajas:crear"), {
                "codigo": "FALLO", "nombre": "Otra", "estado": "HABILITADA",
            })
        self.assertContains(respuesta, "No fue posible registrar la caja.", status_code=500)
        self.assertNotContains(respuesta, "DETALLE_INTERNO_PRIVADO", status_code=500)
        self.assertFalse(Caja.objects.exists())

    def test_error_estado_revierte_y_no_expone_detalles(self):
        """Un fallo después de cambiar estado revierte estado y actor dentro de la transacción."""
        caja = self.crear()
        guardar = Caja.save

        def guardar_y_fallar(instancia, *args, **kwargs):
            guardar(instancia, *args, **kwargs)
            raise RuntimeError("DETALLE_INTERNO_PRIVADO")

        with mock.patch.object(Caja, "save", guardar_y_fallar), self.assertLogs("cajas.views", level="ERROR"):
            respuesta = self.client.post(reverse("cajas:cambiar_estado", args=[caja.id]), {
                "estado": "DESHABILITADA",
            })
        self.assertContains(respuesta, "No fue posible cambiar el estado de la caja.", status_code=500)
        self.assertNotContains(respuesta, "DETALLE_INTERNO_PRIVADO", status_code=500)
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "HABILITADA")

    def test_error_durante_validacion_informa_sin_escribir(self):
        """Una consulta fallida al validar también se informa sin revelar detalles internos."""
        with mock.patch("cajas.views.CajaForm.is_valid", side_effect=RuntimeError("DETALLE_INTERNO_PRIVADO")), self.assertLogs("cajas.views", level="ERROR"):
            respuesta = self.client.post(reverse("cajas:crear"), {
                "codigo": "FALLO", "nombre": "Otra", "estado": "HABILITADA",
            })
        self.assertContains(respuesta, "No fue posible registrar la caja.", status_code=500)
        self.assertNotContains(respuesta, "DETALLE_INTERNO_PRIVADO", status_code=500)
        self.assertFalse(Caja.objects.exists())

    def test_sesion_no_autenticada_redirige_login(self):
        """Un visitante no accede a configuración y es enviado al flujo de login."""
        caja = self.crear()
        self.client.logout()
        respuesta = self.client.get(reverse("cajas:inicio"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta.url)
        self.assertEqual(self.client.get(reverse("cajas:crear")).status_code, 302)
        self.assertEqual(self.client.post(reverse("cajas:crear"), {
            "codigo": "VISITANTE", "nombre": "Otra", "estado": "HABILITADA",
        }).status_code, 302)
        self.assertEqual(self.client.post(reverse("cajas:cambiar_estado", args=[caja.id]), {
            "estado": "DESHABILITADA",
        }).status_code, 302)
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "HABILITADA")
        self.assertEqual(Caja.objects.count(), 1)

    def test_estado_requiere_post_y_csrf(self):
        """El estado no cambia con GET ni mediante un POST sin protección CSRF."""
        caja = self.crear()
        url = reverse("cajas:cambiar_estado", args=[caja.id])
        self.assertEqual(self.client.get(url).status_code, 405)
        cliente = Client(enforce_csrf_checks=True)
        cliente.cookies = self.client.cookies
        self.assertEqual(cliente.post(url, {"estado": "DESHABILITADA"}).status_code, 403)

    def test_cambio_estado_web_y_caja_inexistente(self):
        """El administrador deshabilita vía formulario; una caja ausente devuelve 404."""
        caja = self.crear()
        respuesta = self.client.post(reverse("cajas:cambiar_estado", args=[caja.id]), {
            "estado": "DESHABILITADA",
        })
        self.assertRedirects(respuesta, reverse("cajas:inicio"))
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "DESHABILITADA")
        self.assertEqual(self.client.post(reverse("cajas:cambiar_estado", args=[999999]), {
            "estado": "HABILITADA",
        }).status_code, 404)


class BloqueoCajaTests(TransactionTestCase):
    """Comprueba el bloqueo real en PostgreSQL con dos conexiones independientes."""

    def test_cambio_estado_espera_bloqueo_de_caja(self):
        """Otro cambio espera el bloqueo de fila y termina solo después de liberar la transacción."""
        self.assertEqual(connection.vendor, "postgresql", "Ejecutar en el entorno oficial Docker/PostgreSQL.")
        identidad = {"usuario_id": "admin-bloqueo", "roles": ["ADMINISTRADOR"]}
        caja = crear_caja(codigo="BLOQUEO", nombre="Caja concurrente", **identidad)
        listo = Event()
        pid = []

        def cambiar_en_otra_conexion():
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    pid.append(cursor.fetchone()[0])
                listo.set()
                return cambiar_estado_caja(caja_id=caja.id, estado="DESHABILITADA", **identidad).estado
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=1) as ejecutor:
            with transaction.atomic():
                Caja.objects.select_for_update().get(pk=caja.id)
                resultado = ejecutor.submit(cambiar_en_otra_conexion)
                self.assertTrue(listo.wait(5), "La segunda conexión no inició.")
                limite = time.monotonic() + 5
                bloqueado = False
                while time.monotonic() < limite:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [pid[0]])
                        fila = cursor.fetchone()
                    if fila and fila[0] == "Lock":
                        bloqueado = True
                        break
                    if resultado.done():
                        break
                    time.sleep(0.01)
                self.assertTrue(bloqueado, "El cambio debe esperar el bloqueo de la fila.")
                self.assertFalse(resultado.done())
            self.assertEqual(resultado.result(timeout=5), "DESHABILITADA")
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "DESHABILITADA")
