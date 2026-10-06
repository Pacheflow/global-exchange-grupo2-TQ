from decimal import Decimal, InvalidOperation

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from usuarios.services.keycloak import rol_efectivo
from monedas.models import Moneda

from .forms import CajaForm, EstadoCajaForm
from .models import Caja, PeriodoCaja, SaldoInicialCaja

SAL_CATALOGO = "cajas.apertura.catalogo"


def validar_importe_inicial(valor):
    """Acepta importes exactos finitos de (18, 6), sin redondear ni usar float."""
    if not isinstance(valor, (str, Decimal)):
        raise ValidationError("El importe debe ser un decimal explícito.")
    try:
        monto = Decimal(valor)
    except (InvalidOperation, ValueError):
        raise ValidationError("El importe debe ser numérico.")
    if not monto.is_finite() or monto < 0:
        raise ValidationError("El importe debe ser finito y no negativo.")
    if monto.as_tuple().exponent < -6:
        raise ValidationError("El importe no puede tener más de seis decimales.")
    if monto >= Decimal("1000000000000"):
        raise ValidationError("El importe excede la capacidad permitida.")
    return monto


def firmar_catalogo(caja_id, monedas):
    """Firma los pares relevantes mostrados y los vincula a la caja seleccionada."""
    return signing.dumps({"caja": caja_id, "monedas": sorted([[m.id, m.codigo] for m in monedas])}, salt=SAL_CATALOGO)


def leer_catalogo(caja_id, dato_firmado):
    """Verifica el dato mostrado sin depender del orden, nombre o símbolo."""
    if not isinstance(dato_firmado, str):
        raise ValidationError("El catálogo mostrado no es válido. Revisá nuevamente el formulario.", code="catalogo_invalido")
    try:
        datos = signing.loads(dato_firmado, salt=SAL_CATALOGO)
        if datos["caja"] != caja_id:
            raise ValueError
        pares = datos["monedas"]
        if not isinstance(pares, list) or any(
            not isinstance(par, list) or len(par) != 2
            or type(par[0]) is not int or not isinstance(par[1], str) for par in pares
        ):
            raise ValueError
        if len({par[0] for par in pares}) != len(pares):
            raise ValueError
        return sorted(pares)
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise ValidationError("El catálogo mostrado no es válido. Revisá nuevamente el formulario.", code="catalogo_invalido")


def _validar_cajero(roles, usuario_id):
    """Acuerdo del proyecto: CAJERO efectivo opera cualquier caja habilitada.

    No existen asignaciones individuales Cajero–Caja. Se mantiene la prioridad
    multirrol: administrador y analista no operan como cajero por tener otro rol.
    """
    if rol_efectivo(roles) != "CAJERO":
        raise PermissionDenied("Solo el rol efectivo CAJERO puede abrir cajas.")
    if not isinstance(usuario_id, str) or not usuario_id.strip():
        raise ValidationError("No se encontró una identidad Keycloak válida.")


def validar_saldos_iniciales(saldos, pares):
    """Exige una lista completa, sin repeticiones ni ceros añadidos implícitamente."""
    if not pares:
        raise ValidationError("No hay monedas activas configuradas.")
    if not isinstance(saldos, list):
        raise ValidationError("Los saldos iniciales deben enviarse explícitamente.")
    resultado = {}
    for saldo in saldos:
        if not isinstance(saldo, dict) or type(saldo.get("moneda_id")) is not int:
            raise ValidationError("La moneda del saldo inicial no es válida.")
        moneda_id = saldo["moneda_id"]
        if moneda_id in resultado:
            raise ValidationError("No se permite repetir monedas.")
        resultado[moneda_id] = validar_importe_inicial(saldo.get("monto"))
    if set(resultado) != {par[0] for par in pares}:
        raise ValidationError("Ingresá exactamente un saldo por cada moneda activa, sin omisiones ni monedas adicionales.")
    return resultado


def abrir_caja(*, caja_id, catalogo, saldos, usuario_id, username="", roles):
    """Crea el período y todos sus importes bajo el bloqueo compartido de Caja.

    El instante de validación del catálogo es su consulta dentro de la
    transacción. Cambios posteriores no invalidan la apertura ni sus saldos
    históricos. No se bloquea la tabla de monedas hasta el commit.
    """
    _validar_cajero(roles, usuario_id)
    mostrados = leer_catalogo(caja_id, catalogo)
    try:
        with transaction.atomic():
            caja = Caja.objects.select_for_update().get(pk=caja_id)
            if caja.estado != "HABILITADA":
                raise ValidationError("La caja se encuentra deshabilitada.")
            if caja.periodos.filter(estado="ABIERTO").exists():
                raise ValidationError("La caja ya tiene un período abierto.", code="caja_abierta")
            monedas = list(Moneda.objects.activas())
            actuales = sorted([[m.id, m.codigo] for m in monedas])
            if not actuales:
                raise ValidationError("No hay monedas activas configuradas.")
            if mostrados != actuales:
                raise ValidationError("Las monedas disponibles cambiaron. Revisa los saldos y confirma nuevamente.", code="catalogo_cambiado")
            importes = validar_saldos_iniciales(saldos, actuales)
            periodo = PeriodoCaja(
                caja=caja, responsable_keycloak_id=usuario_id.strip(),
                responsable_username=username,
            )
            periodo.full_clean(validate_constraints=False)
            periodo.save()
            for moneda in monedas:
                SaldoInicialCaja.objects.create(periodo=periodo, moneda=moneda, monto=importes[moneda.id])
            return periodo
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == "caja_unico_periodo_abierto":
            raise ValidationError("La caja ya tiene un período abierto.", code="caja_abierta") from error
        raise


def _validar_administrador(roles, usuario_id):
    """Aplica la prioridad multirrol y exige identidad externa válida."""
    if rol_efectivo(roles) != "ADMINISTRADOR":
        raise PermissionDenied("Solo ADMINISTRADOR puede configurar cajas.")
    if not isinstance(usuario_id, str) or not usuario_id.strip():
        raise ValidationError("No se encontró una identidad Keycloak válida.")


def crear_caja(*, codigo, nombre, estado="HABILITADA", usuario_id, username="", roles):
    """Registra una caja normalizada con trazabilidad y unicidad en la BD."""
    _validar_administrador(roles, usuario_id)
    formulario = CajaForm({"codigo": codigo, "nombre": nombre, "estado": estado})
    if not formulario.is_valid():
        raise ValidationError(formulario.errors.as_data())
    caja = formulario.save(commit=False)
    caja.creado_por_keycloak_id = usuario_id.strip()
    caja.creado_por_username = username
    caja.actualizado_por_keycloak_id = usuario_id.strip()
    caja.full_clean()
    try:
        with transaction.atomic():
            caja.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == "caja_codigo_unico":
            raise ValidationError("Ya existe una caja con ese código.", code="duplicate") from error
        raise
    return caja


def cambiar_estado_caja(*, caja_id, estado, usuario_id, roles):
    """Comparte bloqueo con apertura y no deshabilita cajas con período abierto."""
    _validar_administrador(roles, usuario_id)
    formulario = EstadoCajaForm({"estado": estado})
    if not formulario.is_valid():
        raise ValidationError(formulario.errors.as_data())
    with transaction.atomic():
        caja = Caja.objects.select_for_update().get(pk=caja_id)
        if estado == "DESHABILITADA" and caja.periodos.filter(estado="ABIERTO").exists():
            raise ValidationError("No se puede deshabilitar la caja porque tiene un período abierto.", code="caja_abierta")
        caja.estado = formulario.cleaned_data["estado"]
        caja.actualizado_por_keycloak_id = usuario_id.strip()
        caja.save(update_fields=["estado", "actualizado_por_keycloak_id", "fecha_actualizacion"])
    return caja
