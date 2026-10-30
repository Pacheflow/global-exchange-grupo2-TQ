"""Contrato fiscal exclusivo del emisor TEST habilitado para el equipo 2 TQ.

Los valores tributarios son configuración explícita. Este módulo no debe usarse
contra producción sin validación contable y una configuración propia.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from facturacion.models import Factura, NumeroFiscalAsignado, RangoNumeracionFiscal


RUC_RE = re.compile(r"^(?P<ruc>[0-9]{5,20})-(?P<dv>[0-9])$")


def _texto(nombre, valor, *, patron=None):
    if not isinstance(valor, str) or not valor.strip():
        raise ImproperlyConfigured(f"{nombre} no está configurado.")
    valor = valor.strip()
    if patron and not re.fullmatch(patron, valor):
        raise ImproperlyConfigured(f"{nombre} tiene un formato inválido.")
    return valor


def _entero(nombre, valor):
    try:
        numero = int(valor)
    except (TypeError, ValueError) as error:
        raise ImproperlyConfigured(f"{nombre} debe ser un entero.") from error
    if numero < 1:
        raise ImproperlyConfigured(f"{nombre} debe ser positivo.")
    return numero


def _dato(nombre, valor, *, patron=None):
    if not isinstance(valor, str) or not valor.strip():
        raise ValidationError(f"{nombre} es obligatorio.")
    valor = valor.strip()
    if patron and not re.fullmatch(patron, valor):
        raise ValidationError(f"{nombre} tiene un formato inválido.")
    return valor


def _decimal(nombre, valor):
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError(f"{nombre} no es un importe válido.") from error
    if not numero.is_finite() or numero <= 0:
        raise ValidationError(f"{nombre} debe ser mayor que cero.")
    return numero


def _entero_dato(nombre, valor):
    try:
        numero = int(valor)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{nombre} debe ser un entero.") from error
    if numero < 1:
        raise ValidationError(f"{nombre} debe ser positivo.")
    return numero


def _decimal_esi(valor):
    """Representación decimal sin notación científica ni ceros sobrantes."""
    texto = format(valor, "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


class ContratoFacturaSeguraTest:
    """Construye facturas TEST de contado por la comisión cambiaria.

    COMPRA/VENTA se mapean a los tipos SIFEN 6/5. El ítem fiscal es la
    comisión convertida y congelada en PYG al preparar la factura. La factura,
    su pago y su único ítem siempre se expresan en guaraníes.
    """

    def __init__(self):
        self.ruc = _texto("FACTURA_SEGURA_RUC", settings.FACTURA_SEGURA_RUC, patron=r"[0-9]{5,20}")
        self.dv = _texto("FACTURA_EMISOR_DV", settings.FACTURA_EMISOR_DV, patron=r"[0-9]")
        self.timbrado = _texto("FACTURA_TIMBRADO", settings.FACTURA_TIMBRADO, patron=r"[0-9]{8}")
        self.fecha_inicio = _texto(
            "FACTURA_TIMBRADO_FECHA_INICIO", settings.FACTURA_TIMBRADO_FECHA_INICIO,
            patron=r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
        )
        try:
            date.fromisoformat(self.fecha_inicio)
        except ValueError as error:
            raise ImproperlyConfigured("FACTURA_TIMBRADO_FECHA_INICIO no es una fecha válida.") from error
        self.establecimiento = _texto("FACTURA_ESTABLECIMIENTO", settings.FACTURA_ESTABLECIMIENTO, patron=r"[0-9]{3}")
        self.punto = _texto("FACTURA_PUNTO_EXPEDICION", settings.FACTURA_PUNTO_EXPEDICION, patron=r"[0-9]{3}")
        self.desde = _entero("FACTURA_NUMERO_DESDE", settings.FACTURA_NUMERO_DESDE)
        self.hasta = _entero("FACTURA_NUMERO_HASTA", settings.FACTURA_NUMERO_HASTA)
        if self.desde > self.hasta or self.hasta > 9_999_999:
            raise ImproperlyConfigured("El rango fiscal configurado no es válido.")

    def _reservar_numero(self, transaccion_id):
        factura = Factura.objects.get(transaccion_id=transaccion_id)
        existente = NumeroFiscalAsignado.objects.filter(factura=factura).first()
        if existente:
            return existente.numero_formateado

        identidad = {
            "tipo_documento": "1", "timbrado": self.timbrado,
            "establecimiento": self.establecimiento, "punto_expedicion": self.punto,
        }
        try:
            with transaction.atomic():
                rango, _ = RangoNumeracionFiscal.objects.get_or_create(
                    **identidad,
                    defaults={
                        "numero_desde": self.desde, "numero_hasta": self.hasta,
                        "siguiente_numero": self.desde,
                    },
                )
                rango = RangoNumeracionFiscal.objects.select_for_update().get(pk=rango.pk)
                asignacion = NumeroFiscalAsignado.objects.filter(factura=factura).first()
                if asignacion:
                    return asignacion.numero_formateado
                if not rango.activo:
                    raise ValidationError("El rango fiscal se encuentra inactivo.")
                if (rango.numero_desde, rango.numero_hasta) != (self.desde, self.hasta):
                    raise ImproperlyConfigured("El rango persistido no coincide con la configuración.")
                if rango.siguiente_numero > rango.numero_hasta:
                    raise ValidationError("El rango de facturas TEST se encuentra agotado.")
                numero = rango.siguiente_numero
                asignacion = NumeroFiscalAsignado.objects.create(
                    factura=factura, rango=rango, numero=numero,
                )
                rango.siguiente_numero = numero + 1
                rango.save(update_fields=["siguiente_numero", "actualizado_en"])
                return asignacion.numero_formateado
        except IntegrityError:
            asignacion = NumeroFiscalAsignado.objects.filter(factura=factura).first()
            if asignacion:
                return asignacion.numero_formateado
            raise

    @staticmethod
    def _receptor(snapshot):
        nombre = _dato("El nombre del receptor", snapshot.get("cliente"))
        documento = _dato("El documento del receptor", snapshot.get("documento"))
        correo = _dato("El correo de facturación del receptor", snapshot.get("correo_facturacion"))
        try:
            validate_email(correo)
        except ValidationError as error:
            raise ValidationError("El cliente necesita un correo de facturación válido.") from error

        tipo_persona = snapshot.get("tipo_persona")
        ruc = str(snapshot.get("ruc") or "").strip()
        dv = str(snapshot.get("dv") or "").strip()

        # Las altas actuales guardan RUC y DV por separado. Las facturas
        # históricas pueden conservar el formato anterior ``RUC-DV`` en el
        # snapshot; se admite únicamente como compatibilidad de lectura.
        ruc_legacy = RUC_RE.fullmatch(documento)
        if ruc_legacy and not dv and (not ruc or ruc == documento):
            ruc, dv = ruc_legacy.group("ruc"), ruc_legacy.group("dv")

        if tipo_persona == "JURIDICA":
            if not re.fullmatch(r"[0-9]{5,20}", ruc):
                raise ValidationError("El cliente jurídico necesita un RUC válido, sin guion ni DV.")
            if not re.fullmatch(r"[0-9]", dv):
                raise ValidationError("El cliente jurídico necesita un DV válido.")
            return {
                "iNatRec": "1", "iTiOpe": "1", "cPaisRec": "PRY",
                "iTiContRec": "2", "dRucRec": ruc, "dDVRec": dv,
                "iTipIDRec": "0", "dNumIDRec": "0",
                "dNomRec": nombre, "dEmailRec": correo,
            }
        if ruc_legacy:
            return {
                "iNatRec": "1", "iTiOpe": "1", "cPaisRec": "PRY",
                "iTiContRec": "1", "dRucRec": ruc_legacy.group("ruc"),
                "dDVRec": ruc_legacy.group("dv"), "iTipIDRec": "0",
                "dNumIDRec": "0", "dNomRec": nombre, "dEmailRec": correo,
            }
        if not re.fullmatch(r"[A-Za-z0-9.-]{3,20}", documento):
            raise ValidationError("El documento del receptor no tiene un formato fiscal admitido.")
        return {
            "iNatRec": "2", "iTiOpe": "2", "cPaisRec": "PRY",
            "iTiContRec": "1",
            "dRucRec": "0", "dDVRec": "0", "iTipIDRec": "1",
            "dNumIDRec": documento, "dNomRec": nombre, "dEmailRec": correo,
        }

    def construir_de(self, snapshot):
        if not isinstance(snapshot, dict):
            raise ValidationError("El snapshot comercial no es válido.")
        moneda = "PYG"
        if snapshot.get("importe_comision_pyg") is None:
            raise ValidationError("No existe una tasa persistida para convertir la comisión a PYG.")
        comision = _decimal("importe de comisión en PYG", snapshot.get("importe_comision_pyg"))
        transaccion_id = _entero_dato("La transacción", snapshot.get("transaccion_id"))
        tipo = snapshot.get("tipo")
        if tipo not in {"COMPRA", "VENTA"}:
            raise ValidationError("El tipo de operación no es facturable.")
        naturaleza = snapshot.get("naturaleza_metodo")
        if naturaleza not in {"EFECTIVO", "ELECTRONICO"}:
            raise ValidationError("El método de pago no tiene clasificación fiscal.")

        receptor = self._receptor(snapshot)
        numero = self._reservar_numero(transaccion_id)
        ahora = timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S")
        monto = _decimal_esi(comision)
        pago = {
            "iTiPago": "1" if naturaleza == "EFECTIVO" else "3",
            "dMonTiPag": monto, "cMoneTiPag": moneda, "dTiCamTiPag": "1",
        }
        if naturaleza == "ELECTRONICO":
            pago.update({"iDenTarj": "1", "iForProPa": "1"})

        return {
            "iTipEmi": "1", "iTiDE": "1", "dNumTim": self.timbrado,
            "dFeIniT": self.fecha_inicio, "dEst": self.establecimiento,
            "dPunExp": self.punto, "dNumDoc": numero, "dFeEmiDE": ahora,
            "iTipTra": "6" if tipo == "COMPRA" else "5",
            "iTImp": settings.FACTURA_TIPO_IMPUESTO,
            "cMoneOpe": moneda, "dCondTiCam": "1", "dTiCam": "1",
            "dRucEm": self.ruc, "dDVEmi": self.dv,
            "iTipCont": settings.FACTURA_EMISOR_TIPO_CONTRIBUYENTE,
            "dNomEmi": _texto("FACTURA_EMISOR_NOMBRE", settings.FACTURA_EMISOR_NOMBRE),
            "dDirEmi": _texto("FACTURA_EMISOR_DIRECCION", settings.FACTURA_EMISOR_DIRECCION),
            "dNumCas": _texto("FACTURA_EMISOR_NUMERO_CASA", settings.FACTURA_EMISOR_NUMERO_CASA),
            "cDepEmi": _texto("FACTURA_EMISOR_DEPARTAMENTO_CODIGO", settings.FACTURA_EMISOR_DEPARTAMENTO_CODIGO),
            "dDesDepEmi": _texto("FACTURA_EMISOR_DEPARTAMENTO", settings.FACTURA_EMISOR_DEPARTAMENTO),
            "cCiuEmi": _texto("FACTURA_EMISOR_CIUDAD_CODIGO", settings.FACTURA_EMISOR_CIUDAD_CODIGO),
            "dDesCiuEmi": _texto("FACTURA_EMISOR_CIUDAD", settings.FACTURA_EMISOR_CIUDAD),
            "dTelEmi": _texto("FACTURA_EMISOR_TELEFONO", settings.FACTURA_EMISOR_TELEFONO),
            "dEmailE": _texto("FACTURA_EMISOR_EMAIL", settings.FACTURA_EMISOR_EMAIL),
            "gActEco": [{
                "cActEco": _texto("FACTURA_EMISOR_ACTIVIDAD_CODIGO", settings.FACTURA_EMISOR_ACTIVIDAD_CODIGO),
                "dDesActEco": _texto(
                    "FACTURA_EMISOR_ACTIVIDAD_DESCRIPCION", settings.FACTURA_EMISOR_ACTIVIDAD_DESCRIPCION,
                ),
            }],
            **receptor, "iIndPres": "1", "iCondOpe": "1",
            "gPaConEIni": [pago],
            "gCamItem": [{
                "dCodInt": f"CAMBIO-{transaccion_id}",
                "dDesProSer": f"Servicio de cambio de divisas - operación {transaccion_id}",
                "cUniMed": "77", "dCantProSer": "1", "dPUniProSer": monto,
                "dDescItem": "0", "dDescGloItem": "0", "dAntPreUniIt": "0",
                "dAntGloPreUniIt": "0", "iAfecIVA": settings.FACTURA_AFECTACION_IVA,
                "dPropIVA": settings.FACTURA_PROPORCION_IVA, "dTasaIVA": settings.FACTURA_TASA_IVA,
            }],
            "CDC": "0", "dCodSeg": "0", "dDVId": "0", "dSisFact": "1",
            "dInfAdic": (
                f"Global Exchange TEST - transacción {transaccion_id}; "
                f"conversión PYG {snapshot.get('tasa_conversion_pyg')} "
                f"({snapshot.get('fuente_conversion_pyg')})"
            ),
        }

    @staticmethod
    def extraer_de_calculado(resultado):
        if not getattr(resultado, "resultados", None) or not isinstance(resultado.resultados[0], dict):
            raise ValidationError("Factura Segura no devolvió resultados de cálculo.")
        de = resultado.resultados[0].get("DE")
        if not isinstance(de, dict) or not de:
            raise ValidationError("Factura Segura no devolvió un DE calculado válido.")
        return de

