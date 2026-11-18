"""Pruebas del reporte administrativo de solo consulta."""

import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cajas.models import Caja, MovimientoCaja, PeriodoCaja
from clientes.models import Cliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from tasas.models import TasaComercial
from usuarios.services.keycloak import (
    SESSION_AUTENTICADO,
    SESSION_EXPIRA_EN,
    SESSION_ROLES,
    SESSION_USUARIO,
)

from .models import LiquidacionEfectivo, Transaccion


class ReporteAdministrativoTransaccionesTests(TestCase):
    """Escenarios aislados del reporte y de su detalle protegido."""

    def setUp(self):
        self.url = reverse("operaciones_web:reporte_administrativo_transacciones")
        self.pdf = reverse("operaciones_web:exportar_transacciones_pdf")
        self.cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Histórico QA",
            tipo_persona="FISICA",
            documento="QA-REPORTE-1",
        )
        self.otro_cliente = Cliente.objects.create(
            nombre_razon_social="Cliente Alternativo QA",
            tipo_persona="JURIDICA",
            documento="QA-REPORTE-2",
            estado="INACTIVO",
        )
        self.usd = Moneda.objects.create(codigo="QAUSD", nombre="Dólar QA", simbolo="$", estado="ACTIVA")
        self.pyg = Moneda.objects.create(codigo="QAPYG", nombre="Guaraní QA", simbolo="Gs.", estado="ACTIVA")
        self.eur = Moneda.objects.create(codigo="QAEUR", nombre="Euro QA", simbolo="€", estado="INACTIVA")
        self.metodo = MetodoPago.objects.create(
            nombre="Tarjeta histórica QA", naturaleza="ELECTRONICO", activo=False,
        )
        self.tasa = TasaComercial.objects.create(
            moneda_origen=self.usd,
            moneda_destino=self.pyg,
            compra=Decimal("7000"),
            venta=Decimal("7100"),
            vigente=False,
            usuario_id="analista-qa",
        )
        self.admin = Client()
        self.autenticar(self.admin, ["ADMINISTRADOR"])

    @staticmethod
    def autenticar(cliente_http, roles):
        """Establece una sesión OIDC vigente de prueba con los roles indicados."""
        sesion = cliente_http.session
        sesion[SESSION_AUTENTICADO] = True
        sesion[SESSION_USUARIO] = {"sub": "admin-keycloak-qa", "preferred_username": "admin_qa"}
        sesion[SESSION_EXPIRA_EN] = time.time() + 3600
        sesion[SESSION_ROLES] = roles
        sesion.save()

    def crear_transaccion(
        self, *, cliente=None, tipo="COMPRA", estado="PENDIENTE", origen=None,
        destino=None, naturaleza="ELECTRONICO", version_flujo=1,
        canal="ONLINE", nombre_metodo="Tarjeta histórica QA", fecha=None,
        usuario="operador_qa",
    ):
        """Crea una transacción mínima con snapshots comerciales explícitos."""
        datos_cancelacion = ({
            "cancelado_por_keycloak_id": "admin-keycloak-qa",
            "cancelado_por_username": "admin_qa",
            "cancelado_en": timezone.now(),
            "motivo_cancelacion": "Cancelación de prueba",
        } if estado == "CANCELADA" else {})
        transaccion = Transaccion.objects.create(
            version_flujo=version_flujo,
            canal=canal,
            naturaleza_metodo=naturaleza,
            clave_idempotencia=str(uuid.uuid4()),
            cliente=cliente or self.cliente,
            creado_por_keycloak_id="usuario-keycloak-qa",
            creado_por_username=usuario,
            tipo=tipo,
            moneda_origen=origen or self.usd,
            moneda_destino=destino or self.pyg,
            monto_origen=Decimal("125.500000"),
            monto_destino=Decimal("840000.000000"),
            tasa_comercial=self.tasa,
            tasa_aplicada=Decimal("7000.1234567890"),
            porcentaje_comision=Decimal("4.50"),
            importe_comision=Decimal("39500.000000"),
            metodo_pago=self.metodo,
            metodo_pago_nombre=nombre_metodo,
            estado=estado,
            **datos_cancelacion,
        )
        if fecha:
            Transaccion.objects.filter(pk=transaccion.pk).update(fecha_creacion=fecha)
            transaccion.refresh_from_db()
        return transaccion

    def ids_resultado(self, respuesta):
        """Extrae los identificadores de la página renderizada."""
        return [item.pk for item in respuesta.context["pagina"].object_list]

    def test_administrador_consulta_reporte_y_detalle_sin_escrituras(self):
        """El administrador abre listado y detalle; ambas consultas conservan los registros sin efectos secundarios."""
        transaccion = self.crear_transaccion()
        antes = Transaccion.objects.count()
        with CaptureQueriesContext(connection) as consultas:
            listado = self.admin.get(self.url)
            detalle = self.admin.get(reverse("operaciones_web:detalle_reporte_transaccion", args=[transaccion.pk]))

        self.assertEqual(listado.status_code, 200)
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(listado, "Reporte de transacciones")
        self.assertContains(detalle, f"Detalle de transacción #{transaccion.pk}")
        self.assertNotContains(detalle, "Iniciar pago")
        self.assertEqual(Transaccion.objects.count(), antes)
        self.assertFalse(
            any(re.match(r"\s*(INSERT|UPDATE|DELETE)\b", query["sql"], re.IGNORECASE) for query in consultas.captured_queries)
        )

    def test_visitante_y_roles_no_administrativos_son_rechazados(self):
        """Visitantes, usuarios, cajeros y analistas no consultan el reporte ni su detalle."""
        transaccion = self.crear_transaccion()
        detalle_url = reverse("operaciones_web:detalle_reporte_transaccion", args=[transaccion.pk])
        visitante = Client()
        self.assertEqual(visitante.get(self.url).status_code, 302)
        self.assertEqual(visitante.get(self.pdf).status_code, 302)
        for roles in (["USUARIO"], ["CAJERO"], ["ANALISTA_CAMBIARIO"]):
            with self.subTest(roles=roles):
                cliente_http = Client()
                self.autenticar(cliente_http, roles)
                self.assertEqual(cliente_http.get(self.url).status_code, 403)
                self.assertEqual(cliente_http.get(detalle_url).status_code, 403)
                self.assertEqual(cliente_http.get(self.pdf).status_code, 403)

    def test_reporte_y_detalle_son_solo_get(self):
        """Las rutas de consulta rechazan POST y no cambian la transacción."""
        transaccion = self.crear_transaccion()
        antes = Transaccion.objects.get(pk=transaccion.pk).estado

        listado = self.admin.post(self.url, {"estado": "COMPLETADA"})
        detalle = self.admin.post(reverse("operaciones_web:detalle_reporte_transaccion", args=[transaccion.pk]))

        self.assertEqual(listado.status_code, 405)
        self.assertEqual(detalle.status_code, 405)
        transaccion.refresh_from_db()
        self.assertEqual(transaccion.estado, antes)

    def test_multirrol_respeta_la_prioridad_efectiva(self):
        """ADMINISTRADOR efectivo accede y ANALISTA efectivo no accede aunque tenga rol CAJERO adicional."""
        admin_cajero = Client()
        self.autenticar(admin_cajero, ["CAJERO", "ADMINISTRADOR"])
        analista_cajero = Client()
        self.autenticar(analista_cajero, ["CAJERO", "ANALISTA_CAMBIARIO"])

        self.assertEqual(admin_cajero.get(self.url).status_code, 200)
        self.assertEqual(analista_cajero.get(self.url).status_code, 403)
        self.assertEqual(analista_cajero.get(self.pdf).status_code, 403)
        self.assertEqual(admin_cajero.get(self.pdf).status_code, 200)

    def test_descarga_pdf_es_de_solo_lectura(self):
        """El administrador descarga un PDF con nombre fechado sin escribir en la base."""
        self.crear_transaccion(nombre_metodo="Débito <prueba> & crédito")
        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.admin.get(self.pdf)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertRegex(respuesta["Content-Disposition"], r'^attachment; filename="reporte-transacciones-\d{8}-\d{6}\.pdf"$')
        self.assertTrue(respuesta.content.startswith(b"%PDF-"))
        self.assertFalse(any(re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q["sql"], re.I) for q in consultas))
        self.assertEqual(self.admin.post(self.pdf).status_code, 405)

    @patch("operaciones.reportes.generar_pdf", return_value=b"pdf")
    def test_exporta_todas_las_filas_filtradas_en_orden(self, generar):
        """La descarga ignora la página y conserva filtros, orden de desempate y snapshots."""
        fecha = timezone.now()
        ids = [self.crear_transaccion(fecha=fecha, nombre_metodo="Nombre original").pk for _ in range(26)]
        otra = self.crear_transaccion(cliente=self.otro_cliente, tipo="VENTA", fecha=fecha)
        for filtros, esperados in [
            ({}, [otra.pk, *reversed(ids)]),
            ({"tipo": "VENTA"}, [otra.pk]),
            ({"cliente": self.cliente.pk, "tipo": "COMPRA", "page": 2}, list(reversed(ids))),
        ]:
            with self.subTest(filtros=filtros):
                self.admin.get(self.pdf, filtros)
                filas = generar.call_args.args[0]
                self.assertEqual([fila[0] for fila in filas], [f"#{pk}" for pk in esperados])
        self.assertEqual(filas[0][8], "Nombre original")
        self.assertEqual(Decimal(filas[0][6]), Decimal("7000.1234567890"))

    def test_exportacion_invalida_vacia_o_fallida_informa_en_pantalla(self):
        """La exportación distingue filtros inválidos, cero coincidencias y fallo de generación."""
        self.crear_transaccion()
        with patch("operaciones.reportes.generar_pdf", side_effect=RuntimeError("detalle interno")) as generar:
            self.assertContains(self.admin.get(self.pdf, {"tipo": "INVALIDO"}), "Corrige los filtros")
            self.assertContains(self.admin.get(self.pdf, {"tipo": "VENTA"}),
                                "No se encontraron transacciones con los filtros seleccionados.")
            generar.assert_not_called()
            respuesta = self.admin.get(self.pdf)
            self.assertContains(respuesta, "No se pudo generar el PDF", status_code=500)
            self.assertNotContains(respuesta, "detalle interno", status_code=500)

    def test_filtros_combinados_se_aplican_con_and(self):
        """La combinación cliente, tipo, estado y naturaleza devuelve solo la operación coincidente."""
        coincide = self.crear_transaccion()
        self.crear_transaccion(cliente=self.otro_cliente, estado="COMPLETADA")
        self.crear_transaccion(tipo="VENTA", estado="COMPLETADA", naturaleza="EFECTIVO", canal="PRESENCIAL")

        respuesta = self.admin.get(self.url, {
            "cliente": self.cliente.pk,
            "tipo": "COMPRA",
            "estado": "PENDIENTE",
            "naturaleza": "ELECTRONICO",
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.ids_resultado(respuesta), [coincide.pk])

    def test_filtros_individuales_por_cliente_tipo_estado_y_naturaleza(self):
        """Cada filtro individual limita el queryset al valor seleccionado y no altera operaciones."""
        compra = self.crear_transaccion()
        venta = self.crear_transaccion(
            cliente=self.otro_cliente, tipo="VENTA", estado="COMPLETADA",
            naturaleza="EFECTIVO", canal="PRESENCIAL",
        )
        cancelada = self.crear_transaccion(estado="CANCELADA")
        casos = (
            ({"cliente": self.otro_cliente.pk}, [venta.pk]),
            ({"tipo": "COMPRA"}, [cancelada.pk, compra.pk]),
            ({"estado": "COMPLETADA"}, [venta.pk]),
            ({"estado": "CANCELADA"}, [cancelada.pk]),
            ({"naturaleza": "EFECTIVO"}, [venta.pk]),
        )
        for filtros, esperados in casos:
            with self.subTest(filtros=filtros):
                respuesta = self.admin.get(self.url, filtros)
                self.assertTrue(respuesta.context["filtros_validos"])
                self.assertEqual(self.ids_resultado(respuesta), esperados)

    def test_filtro_moneda_busca_en_origen_o_destino_sin_duplicar(self):
        """La moneda seleccionada encuentra ambas posiciones y cada transacción aparece una sola vez."""
        origen = self.crear_transaccion(origen=self.usd, destino=self.pyg)
        destino = self.crear_transaccion(origen=self.eur, destino=self.usd)
        self.crear_transaccion(origen=self.eur, destino=self.pyg)

        respuesta = self.admin.get(self.url, {"moneda": self.usd.pk})

        self.assertCountEqual(self.ids_resultado(respuesta), [origen.pk, destino.pk])
        self.assertEqual(len(self.ids_resultado(respuesta)), 2)

    def test_fechas_incluyen_el_dia_completo_en_zona_horaria_del_proyecto(self):
        """El rango incluye desde la medianoche hasta el último instante local de fecha hasta."""
        zona = ZoneInfo("America/Asuncion")
        inicio = timezone.make_aware(datetime(2026, 5, 10, 0, 0), zona)
        fin = timezone.make_aware(datetime(2026, 5, 10, 23, 59, 59), zona)
        antes = timezone.make_aware(datetime(2026, 5, 9, 23, 59, 59), zona)
        despues = timezone.make_aware(datetime(2026, 5, 11, 0, 0), zona)
        incluido_inicio = self.crear_transaccion(fecha=inicio)
        incluido_fin = self.crear_transaccion(fecha=fin)
        self.crear_transaccion(fecha=antes)
        self.crear_transaccion(fecha=despues)

        respuesta = self.admin.get(self.url, {"fecha_desde": "2026-05-10", "fecha_hasta": "2026-05-10"})

        self.assertEqual(set(self.ids_resultado(respuesta)), {incluido_inicio.pk, incluido_fin.pk})

    def test_fechas_desde_y_hasta_se_pueden_usar_por_separado(self):
        """Cada extremo de fecha puede filtrar solo sin exigir el otro extremo."""
        zona = ZoneInfo("America/Asuncion")
        fecha_9 = timezone.make_aware(datetime(2026, 5, 9, 12, 0), zona)
        fecha_10 = timezone.make_aware(datetime(2026, 5, 10, 12, 0), zona)
        fecha_11 = timezone.make_aware(datetime(2026, 5, 11, 12, 0), zona)
        nueve = self.crear_transaccion(fecha=fecha_9)
        diez = self.crear_transaccion(fecha=fecha_10)
        once = self.crear_transaccion(fecha=fecha_11)

        desde = self.admin.get(self.url, {"fecha_desde": "2026-05-10"})
        hasta = self.admin.get(self.url, {"fecha_hasta": "2026-05-10"})

        self.assertEqual(set(self.ids_resultado(desde)), {diez.pk, once.pk})
        self.assertEqual(set(self.ids_resultado(hasta)), {nueve.pk, diez.pk})

    def test_fecha_invalida_o_rango_invertido_no_devuelve_listado_global(self):
        """Las fechas inválidas y los rangos invertidos muestran errores y omiten todas las filas."""
        self.crear_transaccion()
        for filtros in (
            {"fecha_desde": "ayer"},
            {"fecha_desde": "2026-06-20", "fecha_hasta": "2026-06-01"},
        ):
            with self.subTest(filtros=filtros):
                respuesta = self.admin.get(self.url, filtros)
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(respuesta.context["filtros_validos"])
                self.assertEqual(self.ids_resultado(respuesta), [])
                self.assertContains(respuesta, "Corrige los filtros indicados")

    def test_parametros_cliente_tipo_estado_naturaleza_y_moneda_invalidos_no_consultan_global(self):
        """Los identificadores y valores no admitidos se validan en backend y no caen al listado global."""
        self.crear_transaccion()
        for filtros in (
            {"cliente": "no-es-id"},
            {"cliente": "999999"},
            {"tipo": "CAMBIO"},
            {"estado": "BORRADO"},
            {"naturaleza": "OTRA"},
            {"moneda": "XYZ"},
        ):
            with self.subTest(filtros=filtros):
                respuesta = self.admin.get(self.url, filtros)
                self.assertFalse(respuesta.context["filtros_validos"])
                self.assertEqual(self.ids_resultado(respuesta), [])

    def test_opciones_de_cliente_y_moneda_incluyen_registros_inactivos(self):
        """Los filtros permiten seleccionar clientes y monedas inactivas vinculados al historial."""
        respuesta = self.admin.get(self.url)

        self.assertContains(respuesta, f'<option value="{self.otro_cliente.pk}">', html=False)
        self.assertContains(respuesta, f'<option value="{self.eur.pk}">', html=False)

    def test_naturaleza_y_metodo_usan_snapshots_aunque_cambie_el_catalogo(self):
        """Cambiar la clasificación y nombre actuales del método no altera los valores históricos mostrados."""
        transaccion = self.crear_transaccion(naturaleza="ELECTRONICO", nombre_metodo="Transferencia registrada")
        MetodoPago.objects.filter(pk=self.metodo.pk).update(naturaleza="EFECTIVO", nombre="Nombre actual")

        respuesta = self.admin.get(self.url)

        fila = respuesta.context["pagina"].object_list[0]
        self.assertEqual(fila.pk, transaccion.pk)
        self.assertEqual(fila.reporte_naturaleza, "Electrónico")
        self.assertEqual(fila.reporte_metodo, "Transferencia registrada")
        self.assertContains(respuesta, "Resultados")
        self.assertContains(respuesta, "1 transacción encontrada.")
        self.assertNotContains(respuesta, "Los importes, la tasa y la comisión se leen del registro de la operación.")

    def test_montos_tasa_y_comision_se_leen_de_la_transaccion(self):
        """Cambios posteriores de la tasa no recalculan los valores persistidos del reporte."""
        transaccion = self.crear_transaccion()
        TasaComercial.objects.filter(pk=self.tasa.pk).update(compra=Decimal("1"), venta=Decimal("2"))

        respuesta = self.admin.get(self.url)
        fila = respuesta.context["pagina"].object_list[0]

        self.assertEqual(fila.pk, transaccion.pk)
        self.assertEqual(fila.monto_origen, Decimal("125.500000"))
        self.assertEqual(fila.monto_destino, Decimal("840000.000000"))
        self.assertEqual(fila.tasa_aplicada, Decimal("7000.1234567890"))
        self.assertEqual(fila.importe_comision, Decimal("39500.000000"))

    def test_operacion_heredada_sin_clasificacion_se_identifica_sin_inferir(self):
        """Una transacción heredada sin naturaleza se etiqueta como no clasificada sin consultar el método actual."""
        transaccion = self.crear_transaccion(
            version_flujo=0, canal="", naturaleza="", nombre_metodo="",
        )
        MetodoPago.objects.filter(pk=self.metodo.pk).update(naturaleza="EFECTIVO")

        respuesta = self.admin.get(self.url, {"naturaleza": "SIN_CLASIFICACION"})

        self.assertEqual(self.ids_resultado(respuesta), [transaccion.pk])
        self.assertContains(respuesta, "Sin clasificación histórica")
        self.assertContains(respuesta, "Sin registro histórico")

    def test_paginacion_conserva_filtros_y_orden_estable_por_fecha_e_id(self):
        """La página contiene 25 filas, mantiene filtros y ordena fechas empatadas por ID descendente."""
        transacciones = [self.crear_transaccion() for _ in range(27)]
        fecha_igual = timezone.make_aware(datetime(2026, 7, 1, 12, 0), ZoneInfo("America/Asuncion"))
        Transaccion.objects.filter(pk__in=[tx.pk for tx in transacciones]).update(fecha_creacion=fecha_igual)

        primera = self.admin.get(self.url, {"tipo": "COMPRA"})
        segunda = self.admin.get(self.url, {"tipo": "COMPRA", "page": "2"})
        fuera_de_rango = self.admin.get(self.url, {"tipo": "COMPRA", "page": "999"})

        self.assertEqual(len(self.ids_resultado(primera)), 25)
        self.assertEqual(self.ids_resultado(primera), sorted([tx.pk for tx in transacciones], reverse=True)[:25])
        self.assertEqual(self.ids_resultado(segunda), sorted([tx.pk for tx in transacciones], reverse=True)[25:])
        self.assertContains(primera, "?tipo=COMPRA&amp;page=2", html=False)
        self.assertEqual(fuera_de_rango.context["pagina"].number, 2)

    def test_pagina_no_numerica_se_resuelve_de_forma_controlada(self):
        """Una página no numérica no falla ni elimina los filtros del listado."""
        transaccion = self.crear_transaccion()

        respuesta = self.admin.get(self.url, {"tipo": "COMPRA", "page": "invalida"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.ids_resultado(respuesta), [transaccion.pk])
        self.assertEqual(respuesta.context["pagina"].number, 1)

    def test_estado_sin_resultados_es_distinto_de_error_de_validacion(self):
        """Un filtro válido sin coincidencias muestra el mensaje vacío y conserva filtros válidos."""
        respuesta = self.admin.get(self.url, {"tipo": "VENTA"})

        self.assertTrue(respuesta.context["filtros_validos"])
        self.assertEqual(respuesta.context["total_resultados"], 0)
        self.assertContains(respuesta, "No se encontraron transacciones con los filtros seleccionados.")
        self.assertNotContains(respuesta, "Corrige los filtros indicados")

    def test_detalle_muestra_actor_de_liquidacion_efectiva(self):
        """El detalle prioriza el cajero vinculado explícitamente a una liquidación en efectivo."""
        transaccion = self.crear_transaccion(naturaleza="EFECTIVO", canal="PRESENCIAL")
        caja = Caja.objects.create(
            codigo="REPORTE-QA", nombre="Caja reporte QA",
            creado_por_keycloak_id="admin", actualizado_por_keycloak_id="admin",
        )
        periodo = PeriodoCaja.objects.create(caja=caja, responsable_keycloak_id="apertura")
        ingreso = MovimientoCaja.objects.create(
            periodo=periodo, moneda=self.usd, tipo="INGRESO", monto=transaccion.monto_origen,
            motivo="Recepción QA", registrado_por_keycloak_id="cajero", registrado_por_username="cajero_qa",
        )
        egreso = MovimientoCaja.objects.create(
            periodo=periodo, moneda=self.pyg, tipo="EGRESO", monto=transaccion.monto_destino,
            motivo="Entrega QA", registrado_por_keycloak_id="cajero", registrado_por_username="cajero_qa",
        )
        LiquidacionEfectivo.objects.create(
            transaccion=transaccion, periodo=periodo, ingreso=ingreso, egreso=egreso,
            confirmado_por_keycloak_id="cajero", confirmado_por_username="cajero_qa",
        )

        respuesta = self.admin.get(reverse("operaciones_web:detalle_reporte_transaccion", args=[transaccion.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cajero: cajero_qa")
        self.assertContains(respuesta, "Caja vinculada")
