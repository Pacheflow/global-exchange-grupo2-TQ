"""Flujo presencial y liquidación física simulada, exclusivamente con datos aislados."""
from unittest import mock
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from cajas.models import MovimientoCaja, SaldoInicialCaja
from clientes.models import UsuarioCliente
from metodos_pago.models import MetodoPago
from pagos.models import Pago
from usuarios.services.keycloak import SESSION_ROLES, SESSION_USUARIO
from . import tests as escenarios
from . import test_guillermo as interfaz
from .models import LiquidacionEfectivo, Transaccion
from .services import liquidar_transaccion, previsualizar_operacion


class EfectivoTests(escenarios.EscenarioLiquidacion, TestCase):
    """Combina la atención presencial con la misma liquidación usada por la bandeja."""

    def setUp(self):
        """Prepara Caja y cliente registrado sin asociaciones con el cajero autenticado."""
        super().setUp()
        self.efectivo = MetodoPago.objects.create(nombre="Modalidad física QA", naturaleza="EFECTIVO")
        UsuarioCliente.objects.all().delete()
        interfaz.FlujosGuillermoTests.autenticar(self, roles=("CAJERO",))
        sesion = self.client.session
        sesion[SESSION_USUARIO] = {"sub": "cajero-presencial", "username": "Cajero QA"}
        sesion.pop("selected_client", None)
        sesion.save()

    def revision(self, tipo="COMPRA", **cambios):
        """Obtiene la firma real del contexto presencial sin persistir efectos financieros."""
        datos = self.datos_preview(tipo=tipo)
        datos.update(cambios)
        respuesta = self.client.post(reverse("operaciones:preview_presencial"), datos, content_type="application/json")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        preview = respuesta.json()
        return {**datos, "firma_preview": preview["firma_preview"], "clave_idempotencia": str(uuid4()),
                "version_preview": preview["tasa_comercial"]["version"], "tasa_preview": preview["tasa"],
                "categoria_preview_id": preview["categoria_preview_id"], "porcentaje_comision_preview": preview["porcentaje_comision"]}

    def datos_preview(self, tipo="COMPRA"):
        """Datos mínimos del cliente y la obligación, sin actor manipulable en el formulario."""
        return dict(cliente_id=self.cliente.pk, tipo=tipo, moneda_origen_id=self.usd.pk,
                    moneda_destino_id=self.pyg.pk, monto="0.01", metodo_pago_id=self.efectivo.pk)

    def confirmar(self, datos):
        """Confirma creación presencial por HTTP; nunca llama a Stripe."""
        return self.client.post(reverse("operaciones:crear_presencial"), datos, content_type="application/json")

    def operacion_efectivo(self, tipo="COMPRA"):
        """Fixture de operación pendiente que también representa una creada por un cliente online."""
        operacion = self.operacion_liquidacion(tipo)
        operacion.metodo_pago = self.efectivo
        operacion.metodo_pago_nombre = self.efectivo.nombre
        operacion.save()
        return operacion

    def test_cajero_crea_ambos_tipos_sin_asociaciones_y_sin_movimientos_ni_pago(self):
        """Crear COMPRA/VENTA registra cliente y actor real una sola vez, pendientes y sin cobros ni efectos de Caja."""
        with mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as proveedor:
            for tipo in ("COMPRA", "VENTA"):
                datos = self.revision(tipo)
                nueva = self.confirmar({**datos, "creado_por_keycloak_id": "suplantado"})
                self.assertEqual(nueva.status_code, 201, nueva.content)
                tx = Transaccion.objects.get(pk=nueva.json()["transaccion"]["id"])
                self.assertEqual((tx.estado, tx.cliente_id, tx.creado_por_keycloak_id),
                                 ("PENDIENTE", self.cliente.pk, "cajero-presencial"))
                self.assertEqual(self.confirmar(datos).json()["transaccion"]["id"], tx.pk)
                self.assertEqual(self.confirmar({**datos, "monto": "2"}).status_code, 400)
            proveedor.assert_not_called()
        self.assertEqual(Transaccion.objects.count(), 2)
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())
        self.assertFalse(UsuarioCliente.objects.exists())

    def test_busqueda_catalogo_y_permisos_presenciales_sin_ampliar_online(self):
        """Solo cajero efectivo ve la selección mínima y efectivo; roles superiores no crean ni acceden por multirrol."""
        pagina = self.client.get(reverse("operaciones_web:presencial"))
        self.assertContains(pagina, 'id="buscar-cliente-efectivo"')
        self.assertContains(pagina, 'data-operation-form')
        self.assertContains(pagina, 'data-can-pay="false"')
        catalogo = self.client.get(reverse("operaciones:metodos_presenciales")).json()
        self.assertEqual(catalogo["metodo_pago_preferido"]["id"], self.efectivo.pk)
        busqueda = self.client.get(reverse("operaciones:clientes_presenciales"), {"q": self.cliente.nombre_razon_social}).json()
        self.assertEqual(busqueda["clientes"], [{"id": self.cliente.pk, "nombre_razon_social": self.cliente.nombre_razon_social}])
        self.assertEqual(self.client.get(reverse("operaciones:clientes_presenciales"), {"q": "a"}).json()["clientes"], [])
        for roles in (["USUARIO"], ["ADMINISTRADOR", "CAJERO"], ["ANALISTA_CAMBIARIO", "CAJERO"]):
            sesion = self.client.session
            sesion[SESSION_ROLES] = roles
            sesion.save()
            for ruta in ("preview_presencial", "crear_presencial"):
                self.assertEqual(self.client.post(reverse("operaciones:" + ruta), {}, content_type="application/json").status_code, 403)
            self.assertEqual(self.client.get(reverse("operaciones:clientes_presenciales"), {"q": "QA"}).status_code, 403)
        sesion = self.client.session
        sesion[SESSION_ROLES] = ["CAJERO", "USUARIO"]
        sesion.save()
        self.assertEqual(self.client.post(reverse("operaciones:crear_transaccion"), {}, content_type="application/json").status_code, 403)
        estricto = Client(enforce_csrf_checks=True)
        estricto.cookies = self.client.cookies
        self.assertEqual(estricto.post(reverse("operaciones:crear_presencial"), {}, content_type="application/json").status_code, 403)
        for roles in (["USUARIO"], ["ADMINISTRADOR", "CAJERO"]):
            with self.assertRaises(ValidationError):
                previsualizar_operacion(**self.datos_preview(), usuario_id="cajero-presencial", presencial=True, roles=roles)

    def test_firma_cliente_contexto_metodo_y_condiciones_no_son_sustituibles(self):
        """Cambiar identidad, cliente, contexto, método no efectivo o condiciones rechaza sin registros."""
        datos = self.revision()
        for cambio in ({"cliente_id": self.cliente.pk + 1}, {"monto": "10"}, {"metodo_pago_id": self.metodo_activo.pk},
                       {"firma_preview": "inválida"}):
            self.assertEqual(self.confirmar({**datos, **cambio}).status_code, 400)
        from .views import _firmar_condiciones
        self.assertEqual(self.confirmar({**datos, "firma_preview": _firmar_condiciones(datos, "cajero-presencial")}).status_code, 400)
        sesion = self.client.session
        sesion[SESSION_USUARIO] = {"sub": "otro-cajero"}
        sesion.save()
        self.assertEqual(self.confirmar(datos).status_code, 400)
        sesion[SESSION_USUARIO] = {"sub": "cajero-presencial"}
        sesion.save()
        self.efectivo.desactivar()
        self.assertEqual(self.confirmar(datos).json()["codigo"], "METODO_NO_DISPONIBLE")
        self.efectivo.activar()
        self.cliente.dar_de_baja()
        self.assertEqual(self.confirmar(datos).status_code, 400)
        self.assertFalse(Transaccion.objects.exists())

    def test_intercambio_ambos_tipos_guarda_evidencia_exacta_y_repite_sin_duplicar(self):
        """Cash COMPRA/VENTA ingresa origen y egresa destino en un período; repetir reutiliza y otro período rechaza."""
        for tipo in ("COMPRA", "VENTA"):
            tx = self.operacion_efectivo(tipo)
            argumentos = self.argumentos_liquidacion(tx, usuario_id="cajero-presencial")
            with mock.patch("pagos.stripe_provider.StripePaymentProvider._cliente") as proveedor:
                liquidar_transaccion(**argumentos)
                self.assertTrue(liquidar_transaccion(**argumentos).repetida)
                proveedor.assert_not_called()
            evidencia = LiquidacionEfectivo.objects.get(transaccion=tx)
            self.assertEqual(evidencia.confirmado_por_keycloak_id, "cajero-presencial")
            self.assertIsNotNone(evidencia.fecha)
            self.assertEqual(evidencia.periodo_id, self.periodo_liquidacion.pk)
            self.assertEqual((evidencia.ingreso.tipo, evidencia.ingreso.moneda_id, evidencia.ingreso.monto), ("INGRESO", self.usd.pk, tx.monto_origen))
            self.assertEqual((evidencia.egreso.tipo, evidencia.egreso.moneda_id, evidencia.egreso.monto), ("EGRESO", self.pyg.pk, tx.monto_destino))
            self.assertEqual(evidencia.ingreso.periodo_id, evidencia.egreso.periodo_id)
            detalle = self.client.get(reverse("operaciones:detalle_transaccion", args=[tx.pk])).json()["transaccion"]
            self.assertEqual(detalle["liquidacion_efectivo"]["ingreso_id"], evidencia.ingreso_id)
            self.assertEqual(detalle["liquidacion_efectivo"]["egreso_id"], evidencia.egreso_id)
            tx.refresh_from_db()
            self.assertEqual(tx.estado, "COMPLETADA")
            with self.assertRaises(ValidationError):
                liquidar_transaccion(**{**argumentos, "periodo_id": self.periodo_liquidacion.pk + 1})
        self.assertEqual(MovimientoCaja.objects.count(), 4)
        self.assertFalse(Pago.objects.exists())
        historial = self.client.get(reverse("operaciones:historial_transacciones"), {"vista": "historial"}).json()["transacciones"]
        self.assertEqual(len(historial), 2)
        self.assertTrue(all(tx["liquidacion_efectivo"] for tx in historial))

    def test_rechazos_caja_pago_incompatible_y_rollback_no_dejan_parciales(self):
        """Caja inválida, pago incompatible, falta de fondos y errores de evidencia/estado conservan pendiente sin efectos."""
        tx = self.operacion_efectivo()
        argumentos = self.argumentos_liquidacion(tx)
        for entidad, campo, valor in ((self.caja_liquidacion, "estado", "DESHABILITADA"),
                                     (self.periodo_liquidacion, "estado", "CERRADO"),
                                     (self.usd, "estado", "INACTIVA"),
                                     (self.efectivo, "activo", False)):
            previo = getattr(entidad, campo)
            setattr(entidad, campo, valor)
            entidad.save()
            with self.assertRaises(ValidationError): liquidar_transaccion(**argumentos)
            setattr(entidad, campo, previo)
            entidad.save()
        saldo = SaldoInicialCaja.objects.get(periodo=self.periodo_liquidacion, moneda=self.pyg)
        saldo.monto = 0
        saldo.save()
        with self.assertRaises(ValidationError): liquidar_transaccion(**argumentos)
        saldo.monto = 1000
        saldo.save()
        origen = SaldoInicialCaja.objects.get(periodo=self.periodo_liquidacion, moneda=self.usd)
        origen.delete()
        with self.assertRaises(ValidationError): liquidar_transaccion(**argumentos)
        SaldoInicialCaja.objects.create(periodo=self.periodo_liquidacion, moneda=self.usd, monto=1000)
        pago = Pago.objects.create(transaccion=tx, metodo_pago=self.efectivo, proveedor="stripe", estado="EN_PROCESO",
                                   monto=tx.monto_origen, moneda_codigo=self.usd.codigo, base_importe="ORIGEN",
                                   iniciado_por_keycloak_id="fixture")
        with self.assertRaises(ValidationError) as error: liquidar_transaccion(**argumentos)
        self.assertEqual(error.exception.code, "PAGO_INCOMPATIBLE")
        pago.delete()
        for objetivo in ("operaciones.services.LiquidacionEfectivo.objects.create", "operaciones.services.Transaccion.save"):
            with mock.patch(objetivo, side_effect=RuntimeError("fallo local")):
                with self.assertRaises(RuntimeError): liquidar_transaccion(**argumentos)
            self.assertFalse(MovimientoCaja.objects.exists())
            self.assertFalse(LiquidacionEfectivo.objects.exists())
            tx.refresh_from_db()
            self.assertEqual(tx.estado, "PENDIENTE")

    def test_catalogo_indica_disponibilidad_y_post_revalida_luego_de_cambio(self):
        """El catálogo no reserva saldo; consumirlo después rechaza el POST y conserva pendiente sin movimiento parcial."""
        tx = self.operacion_efectivo()
        url = reverse("operaciones:periodos_liquidacion", args=[tx.pk])
        self.assertTrue(self.client.get(url).json()["periodos"][0]["disponible"])
        SaldoInicialCaja.objects.filter(periodo=self.periodo_liquidacion, moneda=self.pyg).update(monto=0)
        self.assertFalse(self.client.get(url).json()["periodos"][0]["disponible"])
        respuesta = self.client.post(reverse("operaciones:liquidar_transaccion", args=[tx.pk]),
                                    {"periodo_id": self.periodo_liquidacion.pk}, content_type="application/json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["codigo"], "SALDO_INSUFICIENTE")
        self.assertFalse(MovimientoCaja.objects.exists())
        self.assertFalse(LiquidacionEfectivo.objects.exists())
