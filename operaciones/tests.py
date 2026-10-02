import time
import uuid
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import CategoriaCliente, Cliente, UsuarioCliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from tasas.models import TasaComercial
from tasas.services import actualizar_tasa_comercial
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import Transaccion
from .services import (
    cancelar_transaccion,
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
        valores.setdefault("categoria_preview_id", self.cliente.categoria_id)
        valores.setdefault(
            "porcentaje_comision_preview",
            self.categoria.porcentaje_comision,
        )
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

    def test_tasa_redondeada_es_la_misma_que_se_calcula_y_persiste(self):
        """La tasa visible, calculada y guardada debe ser idéntica."""

        self.tasa.compra = Decimal("5846.292042")
        self.tasa.save(update_fields=["compra"])

        preview = self.previsualizar(monto="1")
        creada = self.crear(monto="1").transaccion

        self.assertEqual(preview.tasa, Decimal("5846"))
        self.assertEqual(preview.monto_convertido, Decimal("5846.000000"))
        self.assertEqual(creada.tasa_aplicada, Decimal("5846"))
        self.assertEqual(creada.monto_destino, preview.monto_destino)

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

    def test_comision_configurada_se_aplica_a_nuevas_operaciones(self):
        """La comisión persistida reemplaza cualquier valor fijo por nombre."""

        self.categoria.porcentaje_comision = Decimal("3.50")
        self.categoria.save(update_fields=["porcentaje_comision"])

        resultado = self.previsualizar()

        self.assertEqual(resultado.porcentaje_comision, Decimal("3.50"))
        self.assertEqual(resultado.importe_comision, Decimal("24500.000000"))


class CrearTransaccionTests(BaseOperacionesTests):
    """Pruebas de la confirmación y persistencia de operaciones."""

    def test_confirmacion_crea_transaccion_completada(self):
        """Comprueba que confirmar una operación cree una transacción COMPLETADA.

        Se espera que la operación válida finalice automáticamente.
        """
        resultado = self.crear()

        self.assertFalse(resultado.repetida)
        self.assertFalse(resultado.cambio_cotizacion)
        self.assertEqual(resultado.transaccion.estado, "COMPLETADA")
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

        Se espera que la transacción quede completada con la tasa de venta.
        """
        resultado = self.crear(tipo="VENTA")

        self.assertEqual(resultado.transaccion.estado, "COMPLETADA")
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

    def test_cambio_cotizacion_rechaza_sin_crear_transaccion(self):
        """Comprueba que un cambio de cotización rechace la operación.

        Si la versión de la tasa cambió desde la previsualización, la
        solicitud debe fallar sin dejar una transacción inválida.
        """
        version_original = self.tasa.version
        self.actualizar_cotizacion()

        with self.assertRaises(ValidationError):
            self.crear(version_preview=version_original)

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_misma_version_no_cancela_aunque_cambie_el_valor(self):
        """Comprueba que con la misma versión la operación continúe.

        Solo la versión de la tasa define el cambio de cotización; un
        cambio de valor con la misma versión no debe cancelar la operación.
        """
        self.tasa.compra = Decimal("7100.000000")
        self.tasa.save(update_fields=["compra"])

        resultado = self.crear(version_preview=self.tasa.version)

        self.assertFalse(resultado.cambio_cotizacion)
        self.assertEqual(resultado.transaccion.estado, "COMPLETADA")
        self.assertEqual(
            resultado.transaccion.tasa_aplicada,
            Decimal("7100.000000"),
        )

    def test_version_distinta_rechaza_aunque_tasa_coincida(self):
        """Comprueba que la decisión dependa de la versión, no del valor.

        Aunque el valor de tasa_preview coincida con la tasa actual, una
        versión distinta debe rechazar la operación.
        """
        version_original = self.tasa.version
        self.actualizar_cotizacion()

        with self.assertRaises(ValidationError):
            self.crear(
                version_preview=version_original,
                tasa_preview=self.tasa.compra,
            )

        self.assertEqual(Transaccion.objects.count(), 0)

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

    def test_cambio_de_porcentaje_desde_preview_rechaza_confirmacion(self):
        """Un cambio de comisión exige generar una nueva previsualización."""

        preview = self.previsualizar()
        self.categoria.porcentaje_comision = Decimal("3.00")
        self.categoria.save(update_fields=["porcentaje_comision"])

        with self.assertRaises(ValidationError):
            self.crear(
                categoria_preview_id=preview.cliente.categoria_id,
                porcentaje_comision_preview=preview.porcentaje_comision,
            )

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_cambio_de_categoria_desde_preview_rechaza_confirmacion(self):
        """Una recategorización exige generar una nueva previsualización."""

        preview = self.previsualizar()
        nueva_categoria = CategoriaCliente.objects.get_or_create(
            nombre="VIP",
            defaults={"porcentaje_comision": Decimal("5.00")},
        )[0]
        self.cliente.categoria = nueva_categoria
        self.cliente.save(update_fields=["categoria"])

        with self.assertRaises(ValidationError):
            self.crear(
                categoria_preview_id=preview.cliente.categoria_id,
                porcentaje_comision_preview=preview.porcentaje_comision,
            )

        self.assertEqual(Transaccion.objects.count(), 0)

    def test_preview_sin_cambios_confirma_con_configuracion_vigente(self):
        """La huella intacta permite recalcular y completar la operación."""

        preview = self.previsualizar()
        resultado = self.crear(
            categoria_preview_id=preview.cliente.categoria_id,
            porcentaje_comision_preview=preview.porcentaje_comision,
        )

        self.assertEqual(resultado.transaccion.estado, "COMPLETADA")
        self.assertEqual(
            resultado.transaccion.porcentaje_comision,
            self.categoria.porcentaje_comision,
        )

    def test_porcentaje_preview_manipulado_no_altera_el_calculo(self):
        """El porcentaje enviado es una huella y nunca una entrada de cálculo."""

        with self.assertRaises(ValidationError):
            self.crear(porcentaje_comision_preview="0.00")

        self.assertEqual(Transaccion.objects.count(), 0)


class CancelarTransaccionTests(BaseOperacionesTests):
    """Pruebas de la cancelación de transacciones pendientes de HU-25."""

    def crear_pendiente(self):
        """Prepara un estado pendiente reservado para flujos futuros."""

        transaccion = self.crear().transaccion
        transaccion.estado = "PENDIENTE"
        transaccion.save(update_fields=["estado"])
        return transaccion

    def test_transaccion_pendiente_se_puede_cancelar(self):
        """Comprueba que una transacción PENDIENTE pueda cancelarse.

        Se espera que pase a CANCELADA, registre la auditoría y conserve
        los valores históricos de la operación.
        """
        transaccion = self.crear_pendiente()

        monto_destino_original = transaccion.monto_destino
        tasa_aplicada_original = transaccion.tasa_aplicada
        comision_original = transaccion.importe_comision

        cancelada = cancelar_transaccion(
            transaccion_id=transaccion.id,
            usuario_id=self.usuario_id,
            usuario_username=self.usuario_username,
        )

        self.assertEqual(cancelada.estado, "CANCELADA")
        self.assertEqual(
            cancelada.cancelado_por_keycloak_id,
            self.usuario_id,
        )
        self.assertEqual(
            cancelada.cancelado_por_username,
            self.usuario_username,
        )
        self.assertIsNotNone(cancelada.cancelado_en)
        self.assertEqual(
            cancelada.motivo_cancelacion,
            "Cancelación solicitada por el usuario.",
        )

        # La cancelación no debe modificar los valores históricos.
        self.assertEqual(
            cancelada.tasa_aplicada,
            tasa_aplicada_original,
        )
        self.assertEqual(
            cancelada.monto_destino,
            monto_destino_original,
        )
        self.assertEqual(
            cancelada.importe_comision,
            comision_original,
        )

        # La transacción se conserva en la base de datos.
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_transaccion_inexistente_no_se_puede_cancelar(self):
        """Comprueba que una transacción inexistente sea rechazada.

        Se espera un error porque el usuario debe seleccionar
        una transacción existente.
        """
        with self.assertRaises(ValidationError):
            cancelar_transaccion(
                transaccion_id=999999,
                usuario_id=self.usuario_id,
                usuario_username=self.usuario_username,
            )

    def test_usuario_sin_acceso_no_puede_cancelar(self):
        """Comprueba que un usuario no pueda cancelar una operación ajena.

        La cancelación debe respetar la asociación entre usuario y cliente.
        """
        transaccion = self.crear_pendiente()

        with self.assertRaises(ValidationError):
            cancelar_transaccion(
                transaccion_id=transaccion.id,
                usuario_id="usuario-sin-acceso",
                usuario_username="otro.usuario",
            )

        transaccion.refresh_from_db()
        self.assertEqual(
            transaccion.estado,
            "PENDIENTE",
        )

    def test_transaccion_cancelada_no_se_cancela_de_nuevo(self):
        """Comprueba que una transacción CANCELADA no pueda cancelarse otra vez.

        Se espera que el segundo intento sea rechazado y se conserve
        la información de la primera cancelación.
        """
        transaccion = self.crear_pendiente()

        primera = cancelar_transaccion(
            transaccion_id=transaccion.id,
            usuario_id=self.usuario_id,
            usuario_username=self.usuario_username,
        )

        fecha_cancelacion = primera.cancelado_en
        motivo_cancelacion = primera.motivo_cancelacion

        with self.assertRaises(ValidationError):
            cancelar_transaccion(
                transaccion_id=transaccion.id,
                usuario_id=self.usuario_id,
                usuario_username=self.usuario_username,
            )

        primera.refresh_from_db()

        self.assertEqual(
            primera.estado,
            "CANCELADA",
        )
        self.assertEqual(
            primera.cancelado_en,
            fecha_cancelacion,
        )
        self.assertEqual(
            primera.motivo_cancelacion,
            motivo_cancelacion,
        )


class IdempotenciaTests(BaseOperacionesTests):
    """Pruebas de la idempotencia por clave idempotencia en confirmación."""

    def test_misma_clave_no_duplica_transaccion(self):
        """Comprueba que repetir la confirmación no duplique transacciones.

        Se espera que la segunda confirmación devuelva la misma transacción.
        """
        clave = self.clave_idempotencia()
        primera = self.crear(clave_idempotencia=clave)
        segunda = self.crear(clave_idempotencia=clave, monto="100.000000")

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
        self.assertEqual(original.transaccion.estado, "COMPLETADA")

        version_original = original.transaccion.tasa_comercial.version

        self.actualizar_cotizacion()
        reintento = self.crear(
            clave_idempotencia=clave,
            version_preview=version_original,
        )

        self.assertTrue(reintento.repetida)
        self.assertFalse(reintento.cambio_cotizacion)
        self.assertEqual(reintento.transaccion.id, original.transaccion.id)
        self.assertEqual(original.transaccion.estado, "COMPLETADA")
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_clave_otro_usuario_es_rechazada_sin_revelar_operacion(self):
        """La clave no autoriza a otra identidad aunque comparta cliente."""

        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        UsuarioCliente.objects.create(
            cliente=self.cliente,
            keycloak_user_id="otro-usuario",
            username="otro.usuario",
            activo=True,
        )

        with self.assertRaises(ValidationError) as error:
            self.crear(
                clave_idempotencia=clave,
                usuario_id="otro-usuario",
                usuario_username="otro.usuario",
            )

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_clave_otro_cliente_es_rechazada(self):
        """La clave no puede reutilizarse en otro cliente autorizado."""

        clave = self.clave_idempotencia()
        self.crear(clave_idempotencia=clave)
        otro_cliente = Cliente.objects.create(
            nombre_razon_social="Otro cliente idempotente",
            tipo_persona="JURIDICA",
            documento="IDEMP-OTRO-CLIENTE",
            categoria=self.categoria,
        )
        UsuarioCliente.objects.create(
            cliente=otro_cliente,
            keycloak_user_id=self.usuario_id,
            username=self.usuario_username,
            activo=True,
        )

        with self.assertRaises(ValidationError):
            self.crear(
                clave_idempotencia=clave,
                cliente_id=otro_cliente.id,
                categoria_preview_id=otro_cliente.categoria_id,
            )

        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_clave_payload_distinto_es_rechazada(self):
        """La clave no puede identificar una solicitud financiera diferente."""

        clave = self.clave_idempotencia()
        self.crear(clave_idempotencia=clave)

        for cambio in (
            {"monto": "101"},
            {"tipo": "VENTA"},
            {"moneda_destino_id": self.otra.id},
            {"version_preview": self.tasa.version + 1},
            {"porcentaje_comision_preview": "9.00"},
            {"metodo_pago_id": self.metodo_inactivo.id},
        ):
            if cambio.get("metodo_pago_id") == self.metodo_inactivo.id:
                otro_metodo = MetodoPago.objects.create(
                    nombre="Transferencia idempotente",
                    activo=True,
                )
                cambio = {"metodo_pago_id": otro_metodo.id}
            with self.assertRaises(ValidationError):
                self.crear(clave_idempotencia=clave, **cambio)

        self.assertEqual(Transaccion.objects.count(), 1)

    def test_misma_clave_categoria_distinta_con_igual_porcentaje_es_rechazada(self):
        """La categoría del preview integra el payload aunque la comisión coincida."""

        categoria_alternativa = CategoriaCliente.objects.create(
            nombre="Minorista alternativo",
            porcentaje_comision=self.categoria.porcentaje_comision,
        )
        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        self.cliente.categoria = categoria_alternativa
        self.cliente.save(update_fields=["categoria"])

        with self.assertRaises(ValidationError) as error:
            self.crear(
                clave_idempotencia=clave,
                categoria_preview_id=categoria_alternativa.id,
                porcentaje_comision_preview=(
                    categoria_alternativa.porcentaje_comision
                ),
            )

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_transaccion_historica_sin_huella_rechaza_reintento(self):
        """Una fila histórica sin huella nunca se presume equivalente."""

        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        Transaccion.objects.filter(pk=original.pk).update(
            huella_idempotencia=None
        )

        with self.assertRaises(ValidationError) as error:
            self.crear(clave_idempotencia=clave)

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
        self.assertEqual(Transaccion.objects.count(), 1)

    def test_carrera_rechaza_categoria_distinta_con_igual_porcentaje(self):
        """La carrera de unicidad aplica la misma huella que el reintento normal."""

        categoria_alternativa = CategoriaCliente.objects.create(
            nombre="VIP alternativo",
            porcentaje_comision=self.categoria.porcentaje_comision,
        )
        clave = self.clave_idempotencia()
        original = self.crear(clave_idempotencia=clave).transaccion
        self.cliente.categoria = categoria_alternativa
        self.cliente.save(update_fields=["categoria"])

        with mock.patch(
            "operaciones.services.Transaccion.objects.filter",
            side_effect=lambda *args, **kwargs: Transaccion.objects.none(),
        ):
            with self.assertRaises(ValidationError) as error:
                self.crear(
                    clave_idempotencia=clave,
                    categoria_preview_id=categoria_alternativa.id,
                    porcentaje_comision_preview=(
                        categoria_alternativa.porcentaje_comision
                    ),
                )

        self.assertIn("clave_idempotencia", error.exception.message_dict)
        self.assertNotIn(str(original.id), str(error.exception))
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
        self.assertEqual(transaccion.estado, "COMPLETADA")

    def test_cambio_de_comision_solo_afecta_operaciones_nuevas(self):
        """Una nueva configuración no altera el snapshot histórico."""

        anterior = self.crear().transaccion
        self.categoria.porcentaje_comision = Decimal("3.00")
        self.categoria.save(update_fields=["porcentaje_comision"])
        nueva = self.crear().transaccion

        anterior.refresh_from_db()
        self.assertEqual(anterior.porcentaje_comision, Decimal("10.00"))
        self.assertEqual(anterior.importe_comision, Decimal("70000.000000"))
        self.assertEqual(nueva.porcentaje_comision, Decimal("3.00"))
        self.assertEqual(nueva.importe_comision, Decimal("21000.000000"))


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

    def test_api_administrador_expone_detalle_global_sin_asociacion(self):
        """El supervisor recibe los datos esenciales de una operación ajena."""

        cliente_ajeno = Cliente.objects.create(
            nombre_razon_social="Cliente global",
            tipo_persona="JURIDICA",
            documento="GLOBAL-001",
            estado="ACTIVO",
            categoria=self.categoria,
        )
        transaccion = self._transaccion_manual(cliente_ajeno, estado="COMPLETADA")
        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = int(time.time()) + 600
        session[SESSION_ROLES] = ["ADMINISTRADOR"]
        session[SESSION_USUARIO] = {"sub": "admin-global", "username": "admin"}
        session.save()

        response = self.client.get(reverse("operaciones:historial_transacciones"))

        self.assertEqual(response.status_code, 200)
        detalle = next(
            item
            for item in response.json()["transacciones"]
            if item["id"] == transaccion.id
        )
        self.assertEqual(detalle["cliente"]["categoria"], "Minorista")
        self.assertEqual(detalle["estado"], "COMPLETADA")
        for campo in (
            "tipo",
            "monto_origen",
            "monto_destino",
            "tasa_aplicada",
            "porcentaje_comision",
            "importe_comision",
            "metodo_pago",
            "fecha_creacion",
            "fecha_actualizacion",
        ):
            self.assertIn(campo, detalle)

        response_detalle = self.client.get(
            reverse("operaciones:detalle_transaccion", args=[transaccion.id])
        )
        self.assertEqual(response_detalle.status_code, 200)
        self.assertEqual(
            response_detalle.json()["transaccion"]["id"],
            transaccion.id,
        )

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
        self.assertEqual(serializada["tasa_aplicada"], "7000")
        self.assertEqual(serializada["monto_convertido"], "700000.000000")

    def test_historial_usa_la_tasa_redondeada_aplicada(self):
        """Comprueba que el historial use la misma tasa aplicada.

        La cotización comercial se normaliza antes de calcular y persistir.
        """
        self.tasa.compra = Decimal("7000.000001")
        self.tasa.save(update_fields=["compra"])

        self.crear(monto="1.000003")
        historial = listar_transacciones(usuario_id=self.usuario_id)
        serializada = _serializar_transaccion(historial[0])

        self.assertEqual(serializada["monto_origen"], "1.000003")
        self.assertEqual(serializada["monto_convertido"], "7000.021000")
        self.assertEqual(serializada["tasa_aplicada"], "7000")


class OperacionesUrlTests(TestCase):
    """Pruebas del registro de las rutas del núcleo de operaciones."""

    def test_rutas_operaciones_registradas(self):
        """Comprueba que las tres rutas del núcleo estén registradas.

        Se espera que los nombres de ruta resuelvan bajo el prefijo API.
        """
        self.assertEqual(
            reverse("operaciones:previsualizar_operacion"),
            "/api/operaciones/previsualizar/",
        )
        self.assertEqual(
            reverse("operaciones:crear_transaccion"),
            "/api/operaciones/crear/",
        )
        self.assertEqual(
            reverse("operaciones:cancelar_transaccion"),
            "/api/operaciones/cancelar/",
        )
        self.assertEqual(
            reverse("operaciones:historial_transacciones"),
            "/api/operaciones/historial/",
        )
        self.assertEqual(reverse("operaciones_web:inicio"), "/operaciones/")


class OperacionesFrontendTests(BaseOperacionesTests):
    """Pruebas esenciales de integración de la pantalla de operaciones."""

    def autenticar(self):
        """Crea una sesión web vigente para el usuario asociado del escenario."""

        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = int(time.time()) + 600
        session[SESSION_ROLES] = ["USUARIO"]
        session[SESSION_USUARIO] = {
            "sub": self.usuario_id,
            "username": self.usuario_username,
        }
        session["selected_client"] = {
            "id": self.cliente.id,
            "name": self.cliente.nombre_razon_social,
        }
        session.save()

    def autenticar_con_roles(self, roles):
        """Crea una sesión válida con los roles indicados y sin cliente."""

        session = self.client.session
        session[SESSION_AUTENTICADO] = True
        session[SESSION_EXPIRA_EN] = int(time.time()) + 600
        session[SESSION_ROLES] = roles
        session[SESSION_USUARIO] = {
            "sub": self.usuario_id,
            "username": self.usuario_username,
        }
        session.pop("selected_client", None)
        session.save()

    def test_pantalla_presenta_cliente_y_catalogos_activos(self):
        """Muestra el contexto autorizado y excluye opciones inactivas."""

        self.cliente.metodo_pago_preferido = self.metodo_activo
        self.cliente.save(update_fields=["metodo_pago_preferido"])
        self.autenticar()

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/operaciones.html")
        self.assertEqual(response.context["cliente_operacion"], self.cliente)
        self.assertIn(self.metodo_activo, response.context["metodos_activos"])
        self.assertNotIn(self.metodo_inactivo, response.context["metodos_activos"])
        self.assertContains(response, "Preferido")
        self.assertContains(
            response,
            f'data-methods-url="{reverse("operaciones:metodos_pago_operacion")}"',
        )
        self.assertContains(
            response,
            f'data-detail-url="{reverse("operaciones:detalle_transaccion", args=[0])}"',
        )

    def test_pantalla_no_expone_cliente_sin_asociacion_activa(self):
        """No habilita el formulario si el cliente dejó de estar asociado."""

        self.asociacion.activo = False
        self.asociacion.save(update_fields=["activo"])
        self.autenticar()

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["cliente_operacion"])
        self.assertContains(response, "Seleccioná un cliente para operar")

    def test_administrador_supervisa_sin_cliente_y_sin_formulario(self):
        """El administrador accede al historial global, no a crear operaciones."""

        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["es_supervisor"])
        self.assertContains(response, "Modo supervisor global")
        self.assertNotContains(response, "data-operation-form")

    def test_administrador_no_puede_confirmar_operaciones(self):
        """La API financiera no amplía permisos por el rol administrador."""

        self.autenticar_con_roles(["ADMINISTRADOR"])

        response = self.client.post(
            reverse("operaciones:crear_transaccion"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_administrador_cajero_conserva_modo_supervisor(self):
        """La prioridad multirrol impide operar con un rol inferior."""

        self.autenticar_con_roles(["ADMINISTRADOR", "CAJERO"])

        pantalla = self.client.get(reverse("operaciones_web:inicio"))
        preview = self.client.post(
            reverse("operaciones:previsualizar_operacion"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(pantalla.status_code, 200)
        self.assertTrue(pantalla.context["es_supervisor"])
        self.assertEqual(preview.status_code, 403)

    def test_analista_no_accede_al_modulo_operativo(self):
        """El analista permanece limitado a tasas y referencia."""

        self.autenticar_con_roles(["ANALISTA_CAMBIARIO"])

        response = self.client.get(reverse("operaciones_web:inicio"))

        self.assertEqual(response.status_code, 403)
