import uuid
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from clientes.models import CategoriaCliente, Cliente, UsuarioCliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from tasas.models import TasaComercial
from tasas.services import actualizar_tasa_comercial

from .models import Transaccion
from .services import (
    crear_transaccion,
    listar_transacciones,
    previsualizar_operacion,
)
from .views import _serializar_transaccion


class BaseOperacionesTests(TestCase):
    """Base común con el escenario de una operación de cambio."""

    def setUp(self):
        self.usuario_id = "usuario-keycloak-123"
        self.usuario_username = "operador"

        self.categoria = CategoriaCliente.objects.get_or_create(
            nombre="Minorista",
        )[0]
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente de prueba",
            tipo_persona="FISICA",
            documento="123456",
            estado="ACTIVO",
            categoria=self.categoria,
        )
        self.asociacion = UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        self.usd = Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar", "simbolo": "$"},
        )[0]
        self.pyg = Moneda.objects.get_or_create(
            codigo="PYG",
            defaults={"nombre": "Guaraní", "simbolo": "Gs."},
        )[0]
        self.otra = Moneda.objects.get_or_create(
            codigo="EUR",
            defaults={"nombre": "Euro", "simbolo": "€"},
        )[0]

        self.metodo_activo = MetodoPago.objects.create(
            nombre="Efectivo",
            activo=True,
        )
        self.metodo_inactivo = MetodoPago.objects.create(
            nombre="Cheque",
            activo=False,
        )

        self.tasa = TasaComercial.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal("7000.000000"),
            venta=Decimal("7250.000000"),
            vigente=True,
            usuario_id=self.usuario_id,
            usuario_username=self.usuario_username,
        )

    def clave_idempotencia(self):
        """Devuelve una clave única de idempotencia para cada ejecución."""
        return str(uuid.uuid4())

    def parametros_preview(self, **datos):
        """Devuelve parámetros válidos para una previsualización."""
        valores = {
            "usuario_id": self.usuario_id,
            "usuario_username": self.usuario_username,
            "cliente_id": self.cliente.id,
            "tipo": "COMPRA",
            "moneda_origen_id": self.usd.id,
            "moneda_destino_id": self.pyg.id,
            "monto": "100",
            "metodo_pago_id": self.metodo_activo.id,
        }
        valores.update(datos)
        return valores

    def previsualizar(self, **datos):
        """Invoca el servicio de previsualización con parámetros base."""
        return previsualizar_operacion(**self.parametros_preview(**datos))

    def parametros_crear(self, **datos):
        """Devuelve parámetros válidos para confirmar una operación."""
        valores = self.parametros_preview(**datos)
        valores.setdefault("clave_idempotencia", self.clave_idempotencia())
        valores.setdefault("version_preview", self.tasa.version)
        return valores

    def crear(self, **datos):
        """Invoca el servicio de confirmación con parámetros base."""
        return crear_transaccion(**self.parametros_crear(**datos))

    def actualizar_cotizacion(self, compra="7600.000000", venta="7800.000000"):
        """Registra una nueva versión vigente de la tasa del par."""
        self.tasa = actualizar_tasa_comercial(
            moneda_origen_id=self.usd.id,
            moneda_destino_id=self.pyg.id,
            usuario_id=self.usuario_id,
            usuario_username=self.usuario_username,
            compra=Decimal(compra),
            venta=Decimal(venta),
        )
        return self.tasa


class PrevisualizarOperacionTests(BaseOperacionesTests):
    """Pruebas del servicio de previsualización de operaciones."""

    def test_compra_utiliza_tasa_de_compra(self):
        """Comprueba que una operación de compra utilice la tasa de compra.

        Se espera que el cálculo aplique el valor de compra vigente del par.
        """
        resultado = self.previsualizar()

        self.assertEqual(resultado.tasa, Decimal("7000.000000"))
        self.assertEqual(resultado.monto_convertido, Decimal("700000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("630000.000000"))

    def test_venta_utiliza_tasa_de_venta(self):
        """Comprueba que una operación de venta utilice la tasa de venta.

        Se espera que el cálculo aplique el valor de venta vigente del par.
        """
        resultado = self.previsualizar(tipo="VENTA")

        self.assertEqual(resultado.tasa, Decimal("7250.000000"))
        self.assertEqual(resultado.monto_convertido, Decimal("725000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("652500.000000"))

    def test_preview_expone_version_de_tasa(self):
        """Comprueba que la previsualización exponga la versión de la tasa.

        Se espera que la versión mostrada para confirmar sea la vigente.
        """
        resultado = self.previsualizar()

        self.assertIsInstance(resultado.tasa_comercial.version, int)
        self.assertEqual(resultado.tasa_comercial.version, self.tasa.version)

    def test_calculo_utiliza_decimal_exacto(self):
        """Comprueba que el cálculo de la conversión utilice Decimal.

        Se espera que los montos calculados sean Decimal y exactos.
        """
        resultado = self.previsualizar(monto="100.50")

        self.assertIsInstance(resultado.monto_origen, Decimal)
        self.assertIsInstance(resultado.tasa, Decimal)
        self.assertIsInstance(resultado.monto_convertido, Decimal)
        self.assertIsInstance(resultado.monto_destino, Decimal)
        self.assertEqual(resultado.monto_convertido, Decimal("703500.000000"))
        self.assertEqual(resultado.importe_comision, Decimal("70350.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("633150.000000"))

    def test_cliente_inexistente_es_rechazado(self):
        """Comprueba que un cliente inexistente sea rechazado.

        Se espera que la operación sea rechazada.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(cliente_id=999999)

    def test_cliente_inactivo_es_rechazado(self):
        """Comprueba que un cliente inactivo no admita operaciones.

        Se espera que la operación sea rechazada.
        """
        self.cliente.estado = "INACTIVO"
        self.cliente.save(update_fields=["estado"])

        with self.assertRaises(ValidationError):
            self.previsualizar()

    def test_usuario_sin_clientes_es_rechazado(self):
        """Comprueba que un usuario sin clientes no pueda operar.

        Se espera que la operación sea rechazada por falta de autorización.

        Requisito relacionado: RNF-02.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(
                usuario_id="usuario-keycloak-sin-clientes",
            )

    def test_cliente_no_autorizado_es_rechazado(self):
        """Comprueba que un usuario no pueda operar con un cliente no autorizado.

        Se espera que la operación sea rechazada.

        Requisito relacionado: RNF-02.
        """
        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente ajeno",
            tipo_persona="JURIDICA",
            documento="654321",
            estado="ACTIVO",
            categoria=self.categoria,
        )

        with self.assertRaises(ValidationError):
            self.previsualizar(cliente_id=cliente_ajeno.id)

    def test_asociacion_inactiva_es_rechazada(self):
        """Comprueba que una asociación desactivada no admita operaciones.

        Se espera que la operación sea rechazada.

        Requisito relacionado: RNF-02.
        """
        self.asociacion.activo = False
        self.asociacion.save(update_fields=["activo"])

        with self.assertRaises(ValidationError):
            self.previsualizar()

    def test_moneda_inactiva_es_rechazada(self):
        """Comprueba que una moneda inactiva no admita operaciones.

        Se espera que la operación sea rechazada.
        """
        self.pyg.estado = "INACTIVA"
        self.pyg.save(update_fields=["estado"])

        with self.assertRaises(ValidationError):
            self.previsualizar()

    def test_metodo_pago_inactivo_es_rechazado(self):
        """Comprueba que un método de pago inactivo sea rechazado.

        Se espera que la operación sea rechazada.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(metodo_pago_id=self.metodo_inactivo.id)

    def test_metodo_preferido_inactivo_obliga_elegir_otro(self):
        """Comprueba que el método preferido inactivo no sea usable.

        Se espera que la operación con el preferido inactivo sea rechazada
        y que elegir otro método activo sea válido.
        """
        self.cliente.metodo_pago_preferido = self.metodo_inactivo
        self.cliente.save(update_fields=["metodo_pago_preferido"])

        with self.assertRaises(ValidationError):
            self.previsualizar(metodo_pago_id=self.metodo_inactivo.id)

        resultado = self.previsualizar()
        self.assertEqual(resultado.metodo_pago.id, self.metodo_activo.id)

    def test_tasa_no_disponible_impide_preview(self):
        """Comprueba que sin tasa comercial vigente la operación sea rechazada.

        Se espera que la previsualización no se realice.
        """
        with self.assertRaises(ValidationError):
            self.previsualizar(moneda_destino_id=self.otra.id)

    def test_preview_no_crea_transaccion(self):
        """Comprueba que la previsualización no registre transacciones.

        Se espera que no exista ninguna transacción tras la previsualización.
        """
        self.previsualizar()

        self.assertEqual(Transaccion.objects.count(), 0)


class ComisionPorCategoriaTests(BaseOperacionesTests):
    """Pruebas de la comisión según la categoría del cliente."""

    def _previsualizar_con_categoria(self, nombre_categoria, documento, monto="100"):
        """Previsualiza una compra para un cliente de la categoría indicada."""
        categoria = CategoriaCliente.objects.get_or_create(
            nombre=nombre_categoria,
        )[0]
        cliente = Cliente.objects.create(
            nombre_razon_social=f"Cliente {nombre_categoria}",
            tipo_persona="JURIDICA",
            documento=documento,
            estado="ACTIVO",
            categoria=categoria,
        )
        UsuarioCliente.objects.create(
            cliente=cliente,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        return self.previsualizar(cliente_id=cliente.id, monto=monto)

    def test_comision_minorista_diez_porciento(self):
        """Comprueba que la categoría Minorista aplique 10 por ciento.

        Con 100 unidades a tasa 7000 el importe de comisión debe ser 70000.
        """
        resultado = self._previsualizar_con_categoria(
            "Minorista",
            documento="111111",
        )

        self.assertEqual(resultado.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(resultado.importe_comision, Decimal("70000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("630000.000000"))

    def test_comision_corporativo_siete_porciento(self):
        """Comprueba que la categoría Corporativo aplique 7 por ciento.

        Con 100 unidades a tasa 7000 el importe de comisión debe ser 49000.
        """
        resultado = self._previsualizar_con_categoria(
            "Corporativo",
            documento="222222",
        )

        self.assertEqual(resultado.porcentaje_comision, Decimal("7.00"))
        self.assertEqual(resultado.importe_comision, Decimal("49000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("651000.000000"))

    def test_comision_vip_cinco_porciento(self):
        """Comprueba que la categoría VIP aplique 5 por ciento.

        Con 100 unidades a tasa 7000 el importe de comisión debe ser 35000.
        """
        resultado = self._previsualizar_con_categoria(
            "VIP",
            documento="333333",
        )

        self.assertEqual(resultado.porcentaje_comision, Decimal("5.00"))
        self.assertEqual(resultado.importe_comision, Decimal("35000.000000"))
        self.assertEqual(resultado.monto_destino, Decimal("665000.000000"))

    def test_comision_se_descunta_del_monto_convertido(self):
        """Comprueba que el monto destino reste la comisión del convertido.

        Se espera que monto_destino sea monto_convertido menos la comisión.
        """
        resultado = self.previsualizar()

        self.assertTrue(
            resultado.monto_destino
            == resultado.monto_convertido - resultado.importe_comision
        )
        self.assertEqual(
            resultado.porcentaje_comision,
            Decimal("10.00"),
        )

    def test_cliente_sin_categoria_es_rechazado(self):
        """Comprueba que un cliente sin categoría no admita operaciones.

        Se espera que la operación sea rechazada sin aplicar comisión 0.
        """
        cliente_sin_categoria = Cliente.objects.create(
            nombre_razon_social="Cliente sin categoría",
            tipo_persona="FISICA",
            documento="444444",
            estado="ACTIVO",
        )
        UsuarioCliente.objects.create(
            cliente=cliente_sin_categoria,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        with self.assertRaises(ValidationError):
            self.previsualizar(cliente_id=cliente_sin_categoria.id)


class CrearTransaccionTests(BaseOperacionesTests):
    """Pruebas de la confirmación y persistencia de operaciones."""

    def test_confirmacion_crea_transaccion_pendiente(self):
        """Comprueba que confirmar una operación cree una transacción PENDIENTE.

        Se espera que la transacción quede pendiente y no cancelada.
        """
        resultado = self.crear()

        self.assertFalse(resultado.repetida)
        self.assertFalse(resultado.cambio_cotizacion)
        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_confirmacion_guarda_snapshots(self):
        """Comprueba que la transacción guarde los snapshots de la operación.

        Se espera que monto, tasas, comisión y método queden persistidos.
        """
        resultado = self.crear()
        transaccion = resultado.transaccion

        self.assertEqual(transaccion.cliente_id, self.cliente.id)
        self.assertEqual(transaccion.moneda_origen_id, self.usd.id)
        self.assertEqual(transaccion.moneda_destino_id, self.pyg.id)
        self.assertEqual(transaccion.monto_origen, Decimal("100.000000"))
        self.assertEqual(transaccion.monto_destino, Decimal("630000.000000"))
        self.assertEqual(transaccion.tasa_comercial_id, self.tasa.id)
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7000.000000"))
        self.assertEqual(transaccion.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(transaccion.importe_comision, Decimal("70000.000000"))
        self.assertEqual(transaccion.metodo_pago_id, self.metodo_activo.id)
        self.assertEqual(transaccion.metodo_pago_nombre, "Efectivo")
        self.assertEqual(transaccion.creado_por_keycloak_id, self.usuario_id)
        self.assertEqual(transaccion.creado_por_username, self.usuario_username)

    def test_confirmacion_venta_utiliza_tasa_de_venta(self):
        """Comprueba que confirmar una venta aplique la tasa de venta.

        Se espera que la transacción quede pendiente con la tasa de venta.
        """
        resultado = self.crear(tipo="VENTA")

        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")
        self.assertEqual(
            resultado.transaccion.tasa_aplicada,
            Decimal("7250.000000"),
        )

    def test_metodo_pago_inactivo_es_rechazado(self):
        """Comprueba que confirmar con método inactivo sea rechazado.

        Se espera que no se cree ninguna transacción.
        """
        with self.assertRaises(ValidationError):
            self.crear(metodo_pago_id=self.metodo_inactivo.id)

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_cambio_cotizacion_cancela_transaccion(self):
        """Comprueba que un cambio de cotización cancele la operación.

        Si la versión de la tasa cambió desde la previsualización, la
        transacción debe quedar CANCELADA con motivo y datos de cancelación.
        """
        version_original = self.tasa.version
        self.actualizar_cotizacion()

        resultado = self.crear(version_preview=version_original)
        transaccion = resultado.transaccion

        self.assertTrue(resultado.cambio_cotizacion)
        self.assertEqual(transaccion.estado, "CANCELADA")
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7600.000000"))
        self.assertEqual(
            transaccion.motivo_cancelacion,
            "La cotización cambió antes de confirmar la operación.",
        )
        self.assertEqual(
            transaccion.cancelado_por_keycloak_id,
            self.usuario_id,
        )
        self.assertEqual(
            transaccion.cancelado_por_username,
            self.usuario_username,
        )
        self.assertIsNotNone(transaccion.cancelado_en)
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_version_no_cancela_aunque_cambie_el_valor(self):
        """Comprueba que con la misma versión la operación continúe.

        Solo la versión de la tasa define el cambio de cotización; un
        cambio de valor con la misma versión no debe cancelar la operación.
        """
        self.tasa.compra = Decimal("7100.000000")
        self.tasa.save(update_fields=["compra"])

        resultado = self.crear(version_preview=self.tasa.version)

        self.assertFalse(resultado.cambio_cotizacion)
        self.assertEqual(resultado.transaccion.estado, "PENDIENTE")
        self.assertEqual(
            resultado.transaccion.tasa_aplicada,
            Decimal("7100.000000"),
        )

    def test_version_distinta_cancela_aunque_tasa_coincida(self):
        """Comprueba que la decisión dependa de la versión, no del valor.

        Aunque el valor de tasa_preview coincida con la tasa actual, una
        versión distinta debe cancelar la operación.
        """
        version_original = self.tasa.version
        self.actualizar_cotizacion()

        resultado = self.crear(
            version_preview=version_original,
            tasa_preview=self.tasa.compra,
        )

        self.assertTrue(resultado.cambio_cotizacion)
        self.assertEqual(resultado.transaccion.estado, "CANCELADA")
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_version_invalida_es_rechazada(self):
        """Comprueba que una versión de preview inválida sea rechazada.

        Sin una versión de la tasa no se puede decidir el cambio de
        cotización; la operación debe ser rechazada sin registrar nada.
        """
        for invalida in (None, "", "abc", "0"):
            with self.assertRaises(ValidationError):
                self.crear(version_preview=invalida)

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_cotizacion_no_disponible_no_crea_transaccion(self):
        """Comprueba que sin cotización vigente no se cree la transacción.

        Se espera que la operación sea rechazada sin registrar nada.
        """
        self.tasa.vigente = False
        self.tasa.save(update_fields=["vigente"])

        with self.assertRaises(ValidationError):
            self.crear()

        self.assertEqual(Transaccion.objects.count(), 0)


class IdempotenciaTests(BaseOperacionesTests):
    """Pruebas de la idempotencia por clave idempotencia en confirmación."""

    def test_misma_clave_no_duplica_transaccion(self):
        """Comprueba que repetir la confirmación no duplique transacciones.

        Se espera que la segunda confirmación devuelva la misma transacción.
        """
        clave = self.clave_idempotencia()
        primera = self.crear(clave_idempotencia=clave)
        segunda = self.crear(clave_idempotencia=clave)

        self.assertFalse(primera.repetida)
        self.assertTrue(segunda.repetida)
        self.assertEqual(primera.transaccion.id, segunda.transaccion.id)
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_reintento_devuelve_transaccion_original(self):
        """Comprueba que el reintento devuelva la transacción original.

        Aunque la cotización cambie después, repetir la misma clave debe
        devolver la transacción ya registrada sin crear otra.
        """
        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave)
        self.assertEqual(original.transaccion.estado, "PENDIENTE")

        self.actualizar_cotizacion()
        reintento = self.crear(clave_idempotencia=clave)

        self.assertTrue(reintento.repetida)
        self.assertFalse(reintento.cambio_cotizacion)
        self.assertEqual(reintento.transaccion.id, original.transaccion.id)
        self.assertEqual(original.transaccion.estado, "PENDIENTE")
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_carrera_por_unicidad_se_resuelve_como_repetida(self):
        """Comprueba que una carrera de unicidad se resuelva como repetida.

        Si el chequeo previo no detecta el duplicado y el INSERT choca con
        la unicidad de la clave, la operación debe devolverse como repetida.
        """
        primera = self.crear()
        clave = primera.transaccion.clave_idempotencia

        with mock.patch(
            "operaciones.services.Transaccion.objects.filter",
            side_effect=lambda *args, **kwargs: Transaccion.objects.none(),
        ):
            reintento = self.crear(clave_idempotencia=clave)

        self.assertTrue(reintento.repetida)
        self.assertEqual(reintento.transaccion.id, primera.transaccion.id)
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_integrity_error_ajeno_no_es_tratado_como_repetida(self):
        """Comprueba que un IntegrityError ajeno se propague.

        Una violación de una restricción distinta a la clave de
        idempotencia no debe interpretarse como repetición de la operación.
        """
        diag = type(
            "Diag",
            (),
            {"constraint_name": "transaccion_algun_check"},
        )()
        causa = type("Causa", (Exception,), {"diag": diag})()

        def save_que_falla(*args, **kwargs):
            raise IntegrityError("viola transaccion_algun_check") from causa

        with mock.patch(
            "operaciones.services.Transaccion.save",
            side_effect=save_que_falla,
        ):
            with self.assertRaises(IntegrityError):
                self.crear()

        self.assertEqual(Transaccion.objects.count(), 0)


class PersistenciaSnapshotsTests(BaseOperacionesTests):
    """Pruebas de persistencia de snapshots ante cambios posteriores."""

    def test_cambios_de_cotizacion_no_alteran_snapshots(self):
        """Comprueba que cambios posteriores no alteren los snapshots.

        Se espera que los valores guardados permanezcan invariantes.
        """
        resultado = self.crear()
        transaccion = Transaccion.objects.get(pk=resultado.transaccion.pk)

        self.actualizar_cotizacion()

        transaccion.refresh_from_db()
        self.assertEqual(transaccion.tasa_aplicada, Decimal("7000.000000"))
        self.assertEqual(transaccion.monto_destino, Decimal("630000.000000"))
        self.assertEqual(transaccion.importe_comision, Decimal("70000.000000"))
        self.assertEqual(transaccion.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(transaccion.metodo_pago_nombre, "Efectivo")
        self.assertEqual(transaccion.estado, "PENDIENTE")


class HistorialTransaccionesTests(BaseOperacionesTests):
    """Pruebas del historial autorizado de transacciones."""

    def _transaccion_manual(self, cliente, *, estado="PENDIENTE", cancelacion=False):
        """Crea directamente una transacción para completar el historial."""
        campos = {
            "estado": estado,
            "cancelado_por_keycloak_id": None,
            "cancelado_por_username": None,
            "cancelado_en": None,
            "motivo_cancelacion": None,
        }
        if cancelacion:
            campos.update(
                {
                    "estado": "CANCELADA",
                    "cancelado_por_keycloak_id": self.usuario_id,
                    "cancelado_por_username": self.usuario_username,
                    "cancelado_en": timezone.now(),
                    "motivo_cancelacion": "Motivo de prueba.",
                }
            )

        return Transaccion.objects.create(
            clave_idempotencia=self.clave_idempotencia(),
            cliente=cliente,
            creado_por_keycloak_id=self.usuario_id,
            creado_por_username=self.usuario_username,
            tipo="COMPRA",
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            monto_origen=Decimal("100.000000"),
            monto_destino=Decimal("630000.000000"),
            tasa_comercial=self.tasa,
            tasa_aplicada=Decimal("7000.000000"),
            porcentaje_comision=Decimal("10.00"),
            importe_comision=Decimal("70000.000000"),
            metodo_pago=self.metodo_activo,
            metodo_pago_nombre=self.metodo_activo.nombre,
            estado=campos["estado"],
            cancelado_por_keycloak_id=campos["cancelado_por_keycloak_id"],
            cancelado_por_username=campos["cancelado_por_username"],
            cancelado_en=campos["cancelado_en"],
            motivo_cancelacion=campos["motivo_cancelacion"],
        )

    def test_historial_solo_muestra_clientes_autorizados(self):
        """Comprueba que el historial filtre por clientes autorizados.

        Se espera que un usuario vea solo transacciones de sus clientes.

        Requisito relacionado: RNF-02.
        """
        propia = self._transaccion_manual(self.cliente)

        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente no autorizado",
            tipo_persona="JURIDICA",
            documento="555555",
            estado="ACTIVO",
            categoria=self.categoria,
        )
        ajena = self._transaccion_manual(cliente_ajeno)

        historial = listar_transacciones(usuario_id=self.usuario_id)

        self.assertIn(propia, historial)
        self.assertNotIn(ajena, historial)

    def test_historial_administrador_ve_todas(self):
        """Comprueba que el administrador consulte todas las transacciones.

        Se espera que el usuario administrador no posea filtros.
        """
        propia = self._transaccion_manual(self.cliente)
        otra = self._transaccion_manual(
            Cliente.objects.create(
                nombre_razon_social="Cliente sin asociación",
                tipo_persona="FISICA",
                documento="666666",
                estado="ACTIVO",
                categoria=self.categoria,
            )
        )

        historial = listar_transacciones(
            usuario_id=self.usuario_id,
            es_admin=True,
        )

        self.assertIn(propia, historial)
        self.assertIn(otra, historial)

    def test_historial_incluye_transacciones_canceladas(self):
        """Comprueba que el historial incluya transacciones canceladas.

        Se espera que la transacción cancelada conserve su motivo.
        """
        cancelada = self._transaccion_manual(
            self.cliente,
            cancelacion=True,
        )

        historial = listar_transacciones(usuario_id=self.usuario_id)

        self.assertIn(cancelada, historial)
        self.assertEqual(cancelada.estado, "CANCELADA")
        self.assertEqual(cancelada.motivo_cancelacion, "Motivo de prueba.")

    def test_historial_no_recalcula_valores(self):
        """Comprueba que el historial no recalcule con la cotización actual.

        Se espera que los snapshots devuelvan los valores persistidos.
        """
        self.crear()
        self.actualizar_cotizacion()

        historial = listar_transacciones(usuario_id=self.usuario_id)
        serializada = _serializar_transaccion(historial[0])

        self.assertEqual(len(historial), 1)
        self.assertEqual(historial[0].tasa_aplicada, Decimal("7000.000000"))
        self.assertEqual(historial[0].monto_destino, Decimal("630000.000000"))
        self.assertEqual(serializada["tasa_aplicada"], "7000.000000")
        self.assertEqual(serializada["monto_convertido"], "700000.000000")

    def test_historial_conserva_precision_de_seis_decimales(self):
        """Comprueba que el historial conserve seis decimales de precisión.

        Se espera que monto_convertido se serialice con la misma precisión
        de seis decimales usada al crear, sin truncamientos ni redondeos
        adicionales.
        """
        self.tasa.compra = Decimal("7000.000001")
        self.tasa.save(update_fields=["compra"])

        self.crear(monto="1.000003")
        historial = listar_transacciones(usuario_id=self.usuario_id)
        serializada = _serializar_transaccion(historial[0])

        self.assertEqual(serializada["monto_origen"], "1.000003")
        self.assertEqual(serializada["monto_convertido"], "7000.021001")


class OperacionesUrlTests(TestCase):
    """Pruebas del registro de las rutas del núcleo de operaciones."""

    def test_rutas_operaciones_registradas(self):
        """Comprueba que las tres rutas del núcleo estén registradas.

        Se espera que los nombres de ruta resuelvan bajo el prefijo API.
        """
        from django.urls import reverse

        self.assertEqual(
            reverse("operaciones:previsualizar_operacion"),
            "/api/operaciones/previsualizar/",
        )
        self.assertEqual(
            reverse("operaciones:crear_transaccion"),
            "/api/operaciones/crear/",
        )
        self.assertEqual(
            reverse("operaciones:historial_transacciones"),
            "/api/operaciones/historial/",
        )