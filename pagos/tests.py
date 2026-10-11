import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from clientes.models import CategoriaCliente, Cliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from operaciones.models import Transaccion
from tasas.models import TasaComercial

from .models import Pago


class PagoModelTests(TestCase):
    """Contrato persistente de pagos; sin proveedor, servicios ni cambio del flujo."""

    @classmethod
    def setUpTestData(cls):
        categoria, _ = CategoriaCliente.objects.get_or_create(nombre="Minorista")
        cls.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente pagos", tipo_persona="FISICA",
            documento="pagos-001", categoria=categoria,
        )
        cls.origen, _ = Moneda.objects.get_or_create(
            codigo="USD", defaults={"nombre": "Dólar", "simbolo": "$"},
        )
        cls.destino, _ = Moneda.objects.get_or_create(
            codigo="PYG", defaults={"nombre": "Guaraní", "simbolo": "Gs"},
        )
        cls.metodo = MetodoPago.objects.create(nombre="Método demo pagos")
        cls.tasa = TasaComercial.objects.create(
            moneda_origen=cls.origen, moneda_destino=cls.destino,
            compra=Decimal("7000"), venta=Decimal("7200"), vigente=True,
            usuario_id="keycloak-pagos", usuario_username="demo",
        )

    def crear_transaccion(self, **cambios):
        datos = {
            "clave_idempotencia": str(uuid.uuid4()), "cliente": self.cliente,
            "creado_por_keycloak_id": "keycloak-pagos", "tipo": "COMPRA",
            "moneda_origen": self.origen, "moneda_destino": self.destino,
            "monto_origen": Decimal("12.345678"), "monto_destino": Decimal("86419.746"),
            "tasa_comercial": self.tasa, "tasa_aplicada": Decimal("7000"),
            "porcentaje_comision": Decimal("0"), "importe_comision": Decimal("0"),
            "metodo_pago": self.metodo, "metodo_pago_nombre": self.metodo.nombre,
            "estado": "PENDIENTE",
        }
        datos.update(cambios)
        return Transaccion.objects.create(**datos)

    def nuevo_pago(self, transaccion=None, **cambios):
        transaccion = transaccion or self.crear_transaccion()
        datos = {
            "transaccion": transaccion, "metodo_pago": self.metodo,
            "proveedor": "stripe", "monto": transaccion.monto_origen,
            "moneda_codigo": self.origen.codigo, "base_importe": Pago.BaseImporte.ORIGEN,
            "iniciado_por_keycloak_id": "keycloak-pagos",
        }
        datos.update(cambios)
        return Pago(**datos)

    def assert_constraint(self, **cambios):
        """La inserción masiva omite save/clean y comprueba el SQL real."""
        pago = self.nuevo_pago(**cambios)
        pago.huella_solicitud = pago.calcular_huella()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pago.objects.bulk_create([pago])

    def test_creacion_uuid_precision_defaults_y_huella_backend(self):
        pago = self.nuevo_pago()
        pago.save()
        pago.refresh_from_db()
        self.assertIsInstance(pago.pk, uuid.UUID)
        self.assertEqual(pago.monto, Decimal("12.345678"))
        self.assertEqual(pago.estado, Pago.Estado.EN_PROCESO)
        self.assertEqual(pago.trazabilidad, [])
        self.assertIsNone(pago.referencia_externa)
        self.assertIsNone(pago.aprobado_en)
        self.assertRegex(pago.huella_solicitud, r"\A[0-9a-f]{64}\Z")
        self.assertEqual(pago.huella_solicitud, pago.calcular_huella())
        self.assertEqual(pago.transaccion.estado, "PENDIENTE")

    def test_proveedor_es_obligatorio_sin_default(self):
        pago = self.nuevo_pago(proveedor="")
        with self.assertRaises(ValidationError):
            pago.save()
        self.assertFalse(Pago._meta.get_field("proveedor").has_default())

    def test_identidad_del_iniciador_no_acepta_espacios(self):
        with self.assertRaises(ValidationError):
            self.nuevo_pago(iniciado_por_keycloak_id="   ").save()

    def test_unico_por_transaccion_en_bd(self):
        pago = self.nuevo_pago()
        pago.save()
        self.assert_constraint(transaccion=pago.transaccion)

    def test_relaciones_protegidas(self):
        pago = self.nuevo_pago()
        pago.save()
        for objeto in (pago.transaccion, self.metodo):
            with self.subTest(modelo=type(objeto).__name__):
                with self.assertRaises(ProtectedError) as error:
                    objeto.delete()
                self.assertIn(pago, error.exception.protected_objects)

    def test_monto_estado_y_base_validos_en_bd(self):
        for cambios in (
            {"monto": Decimal("0")}, {"monto": Decimal("-1")},
            {"estado": "INVALIDO"}, {"base_importe": "OTRA"},
        ):
            with self.subTest(cambios=cambios):
                self.assert_constraint(**cambios)

    def test_monto_nan_rechazado_en_bd(self):
        if connection.vendor != "postgresql":
            self.skipTest("La semántica NUMERIC NaN requiere PostgreSQL.")
        pago = self.nuevo_pago()
        pago.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE pagos_pago SET monto = 'NaN'::numeric WHERE id = %s", [pago.pk])

    def test_monto_invalido_rechazado_por_modelo(self):
        for monto in ("no-decimal", Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("1e10000"), Decimal("12.3456789")):
            with self.subTest(monto=monto), self.assertRaises(ValidationError):
                self.nuevo_pago(monto=monto).save()

    def test_bd_permite_base_destino_sin_cambiar_regla_actual_compra(self):
        pago = self.nuevo_pago(base_importe=Pago.BaseImporte.DESTINO)
        pago.huella_solicitud = pago.calcular_huella()
        Pago.objects.bulk_create([pago])
        pago.refresh_from_db()
        self.assertEqual(pago.base_importe, Pago.BaseImporte.DESTINO)

    def test_aprobacion_exige_referencia_y_fecha_en_bd(self):
        for referencia, fecha in ((None, None), ("pi_demo", None), (None, timezone.now()), ("", timezone.now())):
            with self.subTest(referencia=referencia, fecha=fecha):
                self.assert_constraint(estado=Pago.Estado.APROBADO, referencia_externa=referencia, aprobado_en=fecha)
        pago = self.nuevo_pago(estado=Pago.Estado.APROBADO, referencia_externa="pi_demo", aprobado_en=timezone.now())
        pago.save()
        self.assertTrue(Pago.objects.filter(pk=pago.pk).exists())
        with self.assertRaises(ValidationError):
            self.nuevo_pago(estado=Pago.Estado.APROBADO, referencia_externa="   ", aprobado_en=timezone.now()).save()

    def test_referencia_unica_por_proveedor_y_null_permitido(self):
        primero = self.nuevo_pago(referencia_externa="pi_demo")
        primero.save()
        self.assert_constraint(referencia_externa="pi_demo")
        self.nuevo_pago(proveedor="otro", referencia_externa="pi_demo").save()
        self.nuevo_pago().save()
        self.nuevo_pago(referencia_externa="").save()
        self.assertEqual(Pago.objects.filter(referencia_externa__isnull=True).count(), 2)

    def test_creacion_rechaza_venta_y_transaccion_no_pendiente(self):
        for cambios in ({"tipo": "VENTA"}, {"estado": "COMPLETADA"}):
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                self.nuevo_pago(transaccion=self.crear_transaccion(**cambios)).save()

    def test_creacion_exige_snapshots_coincidentes(self):
        otro = MetodoPago.objects.create(nombre="Otro método")
        for cambios in (
            {"metodo_pago": otro}, {"monto": Decimal("9")},
            {"moneda_codigo": "EUR"}, {"base_importe": Pago.BaseImporte.DESTINO},
            {"huella_solicitud": "0" * 64},
        ):
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                self.nuevo_pago(**cambios).save()

    def test_snapshots_huella_e_iniciador_inmutables(self):
        pago = self.nuevo_pago()
        pago.save()
        otra_transaccion = self.crear_transaccion()
        otro_metodo = MetodoPago.objects.create(nombre="Método alternativo")
        cambios = {
            "transaccion_id": otra_transaccion.pk, "metodo_pago_id": otro_metodo.pk,
            "proveedor": "otro", "monto": Decimal("20"), "moneda_codigo": "EUR",
            "base_importe": "DESTINO", "huella_solicitud": "0" * 64,
            "iniciado_por_keycloak_id": "otro-usuario",
        }
        for campo, valor in cambios.items():
            pago.refresh_from_db()
            setattr(pago, campo, valor)
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                pago.save()

    def test_actualizacion_tecnica_no_revalida_elegibilidad_de_creacion(self):
        pago = self.nuevo_pago()
        pago.save()
        Transaccion.objects.filter(pk=pago.transaccion_id).update(estado="COMPLETADA")
        pago.estado = Pago.Estado.APROBADO
        pago.referencia_externa = "pi_aprobado"
        pago.aprobado_en = timezone.now()
        pago.save()
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)

    def test_estados_terminales_no_se_modifican(self):
        for estado in (Pago.Estado.APROBADO, Pago.Estado.RECHAZADO):
            pago = self.nuevo_pago(
                estado=estado, referencia_externa="pi_" + str(uuid.uuid4()),
                aprobado_en=timezone.now() if estado == Pago.Estado.APROBADO else None,
            )
            pago.save()
            pago.estado = Pago.Estado.EN_PROCESO
            with self.subTest(estado=estado), self.assertRaises(ValidationError):
                pago.save()

    def test_trazabilidad_controlada_persistida(self):
        evento = {"fecha": timezone.now().isoformat(), "estado": "EN_PROCESO", "codigo": "RESERVADO"}
        pago = self.nuevo_pago(trazabilidad=[evento])
        pago.save()
        pago.refresh_from_db()
        self.assertEqual(pago.trazabilidad, [evento])

    def test_trazabilidad_rechaza_texto_libre_secretos_y_exceso(self):
        evento = {"fecha": timezone.now().isoformat(), "estado": "EN_PROCESO", "codigo": "RESERVADO"}
        invalidos = (
            {}, ["respuesta externa"], [{**evento, "token": "valor-ficticio"}],
            [{**evento, "codigo": "texto libre"}], [{**evento, "estado": "desconocido"}],
            [{**evento, "fecha": "no-fecha"}], [{**evento, "fecha": "2026-10-08T12:00:00"}],
            [evento] * 51,
            [{**evento, "fecha": "2026-10-08T12:00:00." + "0" * 300 + "+00:00"}] * 30,
        )
        for trazabilidad in invalidos:
            with self.subTest(trazabilidad=trazabilidad), self.assertRaises(ValidationError):
                self.nuevo_pago(trazabilidad=trazabilidad).save()
