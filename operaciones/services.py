from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from clientes.models import Cliente, UsuarioCliente
from metodos_pago.models import MetodoPago
from monedas.models import Moneda
from tasas.models import TasaComercial

from .models import Transaccion


PRECISION_MONTO = Decimal("0.000001")

COMISION_POR_CATEGORIA = {
    "MINORISTA": Decimal("10.00"),
    "CORPORATIVO": Decimal("7.00"),
    "VIP": Decimal("5.00"),
}

MOTIVO_CAMBIO_COTIZACION = "La cotización cambió antes de confirmar la operación."
MOTIVO_CANCELACION_CAMBIO_COTIZACION = (
    "La cotización cambió o dejó de estar disponible."
)


@dataclass(frozen=True)
class ResultadoPreviewOperacion:
    """Resultado de una previsualización de operación de cambio.

    Contiene los datos validados y los valores calculados de la operación
    sin persistir ninguna entidad.

    Attributes:
        tipo (str): Tipo de operación (COMPRA o VENTA).
        cliente (Cliente): Cliente en cuyo nombre se realiza la operación.
        moneda_origen (Moneda): Moneda que se entrega.
        moneda_destino (Moneda): Moneda que se recibe.
        monto_origen (Decimal): Monto de la operación en moneda origen.
        tasa (Decimal): Tasa comercial aplicada.
        monto_convertido (Decimal): Monto convertido antes de comisión.
        importe_comision (Decimal): Importe de comisión descontado.
        monto_destino (Decimal): Monto final después de la comisión.
        porcentaje_comision (Decimal): Porcentaje según la categoría del cliente.
        tasa_comercial (TasaComercial): Registro vigente de la tasa utilizada.
        metodo_pago (MetodoPago): Método de pago seleccionado.
    """

    tipo: str
    cliente: Cliente
    moneda_origen: Moneda
    moneda_destino: Moneda
    monto_origen: Decimal
    tasa: Decimal
    monto_convertido: Decimal
    importe_comision: Decimal
    monto_destino: Decimal
    porcentaje_comision: Decimal
    tasa_comercial: TasaComercial
    metodo_pago: MetodoPago


@dataclass(frozen=True)
class ResultadoCrearTransaccion:
    """Resultado de la confirmación de una operación de cambio.

    Attributes:
        transaccion (Transaccion): Transacción creada o ya existente.
        repetida (bool): Indica si la clave de idempotencia ya existía.
        cambio_cotizacion (bool): Indica si la cotización cambió desde la preview.
    """

    transaccion: Transaccion
    repetida: bool = False
    cambio_cotizacion: bool = False


def _validar_identidad(usuario_id):
    """Comprueba que exista una identidad Keycloak válida."""

    if not isinstance(usuario_id, str) or not usuario_id.strip():
        raise ValidationError(
            {"usuario": "No se encontró una identidad Keycloak válida."}
        )
    return usuario_id.strip()


def _obtener_cliente_activo(cliente_id):
    """Obtiene un cliente activo o rechaza la operación."""

    try:
        cliente = Cliente.objects.get(pk=cliente_id)
    except (Cliente.DoesNotExist, ValueError, TypeError):
        raise ValidationError(
            {"cliente": "El cliente seleccionado no existe."}
        )

    if cliente.estado != "ACTIVO":
        raise ValidationError(
            {"cliente": "El cliente se encuentra inactivo."}
        )

    return cliente


def _validar_acceso_usuario_cliente(cliente, usuario_id):
    """Comprueba la asociación activa entre un usuario Keycloak y su cliente.

    Requisito relacionado: RNF-02.
    """

    if not UsuarioCliente.objects.filter(
        cliente=cliente,
        keycloak_user_id=usuario_id,
        activo=True,
    ).exists():
        raise ValidationError(
            {"cliente": "El usuario no tiene acceso a este cliente."}
        )


def _obtener_moneda_activa(moneda_id, campo):
    """Obtiene una moneda y verifica que se encuentre activa."""

    try:
        moneda = Moneda.objects.get(pk=moneda_id)
    except (Moneda.DoesNotExist, ValueError, TypeError):
        raise ValidationError(
            {campo: "La moneda seleccionada no existe."}
        )

    if moneda.estado != "ACTIVA":
        raise ValidationError(
            {campo: "La moneda seleccionada se encuentra inactiva."}
        )

    return moneda


def _convertir_monto(monto):
    """Convierte y valida el monto ingresado."""

    try:
        monto_decimal = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({"monto": "El monto debe ser numérico."})

    if not monto_decimal.is_finite() or monto_decimal <= 0:
        raise ValidationError({"monto": "El monto debe ser mayor que cero."})

    return monto_decimal


def _obtener_tasa_comercial_vigente(moneda_origen, moneda_destino):
    """Obtiene la tasa comercial vigente del par o rechaza la operación."""

    tasa = _buscar_tasa_comercial_vigente(moneda_origen, moneda_destino)

    if tasa is None:
        raise ValidationError(
            {"tasa": "No existe una tasa comercial vigente para el par indicado."}
        )

    return tasa


def _buscar_tasa_comercial_vigente(moneda_origen, moneda_destino, *, bloquear=False):
    """Busca la tasa comercial vigente del par o devuelve None.

    Se utiliza para diferenciar la ausencia de cotización del resto de
    validaciones al confirmar una operación.

    Si ``bloquear`` es True, la o las filas vigentes del par se bloquean
    con ``select_for_update()`` dentro de la transacción vigente, de forma
    coherente con tasas.services.actualizar_tasa_comercial(), para reducir
    condiciones de carrera durante la confirmación.

    Args:
        moneda_origen (Moneda): Moneda de origen del par.
        moneda_destino (Moneda): Moneda de destino del par.
        bloquear (bool): Indica si la consulta debe bloquear las filas.

    Returns:
        TasaComercial | None: Tasa vigente del par o None si no existe.
    """

    consulta = TasaComercial.objects.filter(
        moneda_origen=moneda_origen,
        moneda_destino=moneda_destino,
        vigente=True,
    )

    if bloquear:
        consulta = consulta.select_for_update()

    return consulta.first()


def _es_conflicto_de_idempotencia(causa):
    """Indica si un IntegrityError corresponde a clave_idempotencia.

    La causa raíz de psycopg expone el nombre de la restricción violada
    en ``diag.constraint_name``; solo la unicidad de la clave de
    idempotencia se interpreta como una repetición de la operación.

    Args:
        causa (Exception | None): Causa raíz del error (__cause__).

    Returns:
        bool: True solo cuando la violación corresponde a la clave de idempotencia.
    """

    if causa is None:
        return False

    diag = getattr(causa, "diag", None)
    if diag is None:
        return False

    nombre_restriccion = getattr(diag, "constraint_name", None) or ""
    return nombre_restriccion.endswith("_clave_idempotencia_key")


def _tasa_segun_tipo(tipo, tasa_comercial):
    """Devuelve el valor de compra o venta según el tipo de operación.

    La selección de la tasa es única y compartida por compra y venta.

    Args:
        tipo (str): Tipo de operación (COMPRA o VENTA).
        tasa_comercial (TasaComercial): Tasa comercial vigente del par.

    Returns:
        Decimal: Valor de compra o venta correspondiente al tipo.
    """

    if tipo == "COMPRA":
        return tasa_comercial.compra

    if tipo == "VENTA":
        return tasa_comercial.venta

    raise ValidationError(
        {"tipo": "El tipo de operación debe ser COMPRA o VENTA."}
    )


def _obtener_metodo_pago_activo(metodo_pago_id):
    """Obtiene un método de pago activo del catálogo global."""

    try:
        metodo = MetodoPago.objects.get(pk=metodo_pago_id)
    except (MetodoPago.DoesNotExist, ValueError, TypeError):
        raise ValidationError(
            {"metodo_pago": "El método de pago seleccionado no existe."}
        )

    if not metodo.activo:
        raise ValidationError(
            {"metodo_pago": "El método de pago seleccionado está inactivo."}
        )

    return metodo


def _porcentaje_comision_para_cliente(cliente):
    """Determina el porcentaje de comisión según la categoría del cliente.

    La comisión depende exclusivamente de la categoría comercial del
    cliente; la ausencia o el desconocimiento de la categoría se rechaza
    en lugar de aplicar una comisión por defecto.

    Args:
        cliente (Cliente): Cliente de la operación.

    Returns:
        Decimal: Porcentaje de comisión configurado para la categoría.

    Raises:
        ValidationError: Si el cliente no posee categoría o esta no tiene
        una comisión configurada.
    """

    categoria = cliente.categoria
    if categoria is None:
        raise ValidationError(
            {"cliente": "El cliente no posee una categoría comercial."}
        )

    porcentaje = COMISION_POR_CATEGORIA.get(
        categoria.nombre.strip().upper()
    )

    if porcentaje is None:
        raise ValidationError(
            {"cliente": "La categoría del cliente no posee una comisión configurada."}
        )

    return porcentaje


def _calcular_operacion(monto_origen, tasa_aplicada, porcentaje_comision):
    """Calcula los valores monetarios de una operación de cambio.

    monto_convertido = monto_origen × tasa_aplicada
    importe_comision = monto_convertido × porcentaje_comision / 100
    monto_destino = monto_convertido − importe_comision

    Args:
        monto_origen (Decimal): Monto en moneda origen.
        tasa_aplicada (Decimal): Tasa comercial aplicada.
        porcentaje_comision (Decimal): Porcentaje de comisión de la categoría.

    Returns:
        tuple: (monto_convertido, importe_comision, monto_destino).
    """

    monto_convertido = (monto_origen * tasa_aplicada).quantize(
        PRECISION_MONTO,
        rounding=ROUND_HALF_UP,
    )
    importe_comision = (
        monto_convertido * porcentaje_comision / Decimal("100")
    ).quantize(
        PRECISION_MONTO,
        rounding=ROUND_HALF_UP,
    )
    monto_destino = (monto_convertido - importe_comision).quantize(
        PRECISION_MONTO,
        rounding=ROUND_HALF_UP,
    )
    return monto_convertido, importe_comision, monto_destino


def previsualizar_operacion(
    *,
    usuario_id,
    usuario_username="",
    cliente_id,
    tipo,
    moneda_origen_id,
    moneda_destino_id,
    monto,
    metodo_pago_id,
):
    """Calcula la previsualización de una operación de compra o venta.

    Valida la identidad, el cliente, la asociación UsuarioCliente, las
    monedas, la tasa comercial vigente, el método de pago y la categoría
    del cliente, y calcula la conversión y la comisión con Decimal sin
    persistir ninguna entidad.

    Args:
        usuario_id (str): Identidad Keycloak del usuario que opera.
        usuario_username (str): Nombre del usuario Keycloak que opera.
        cliente_id (int): Cliente en cuyo nombre se realiza la operación.
        tipo (str): Tipo de operación (COMPRA o VENTA).
        moneda_origen_id (int): Moneda que se entrega.
        moneda_destino_id (int): Moneda que se recibe.
        monto (str | int | Decimal): Monto de la operación en moneda origen.
        metodo_pago_id (int): Método de pago del catálogo global seleccionado.

    Returns:
        ResultadoPreviewOperacion: Datos validados y valores calculados.

    Requisito relacionado: RF-11 y RF-12.
    """

    usuario_id = _validar_identidad(usuario_id)

    if tipo not in dict(Transaccion.TIPOS_TRANSACCION):
        raise ValidationError(
            {"tipo": "El tipo de operación debe ser COMPRA o VENTA."}
        )

    cliente = _obtener_cliente_activo(cliente_id)
    _validar_acceso_usuario_cliente(cliente, usuario_id)

    moneda_origen = _obtener_moneda_activa(
        moneda_origen_id,
        "moneda_origen",
    )
    moneda_destino = _obtener_moneda_activa(
        moneda_destino_id,
        "moneda_destino",
    )

    if moneda_origen.pk == moneda_destino.pk:
        raise ValidationError(
            {"monedas": "La moneda de origen y destino deben ser diferentes."}
        )

    monto_origen = _convertir_monto(monto)
    tasa_comercial = _obtener_tasa_comercial_vigente(
        moneda_origen,
        moneda_destino,
    )
    tasa_aplicada = _tasa_segun_tipo(tipo, tasa_comercial)

    if tasa_aplicada <= 0:
        raise ValidationError(
            {"tasa": "La tasa comercial debe ser mayor que cero."}
        )

    porcentaje_comision = _porcentaje_comision_para_cliente(cliente)
    monto_convertido, importe_comision, monto_destino = _calcular_operacion(
        monto_origen,
        tasa_aplicada,
        porcentaje_comision,
    )

    metodo_pago = _obtener_metodo_pago_activo(metodo_pago_id)

    return ResultadoPreviewOperacion(
        tipo=tipo,
        cliente=cliente,
        moneda_origen=moneda_origen,
        moneda_destino=moneda_destino,
        monto_origen=monto_origen,
        tasa=tasa_aplicada,
        monto_convertido=monto_convertido,
        importe_comision=importe_comision,
        monto_destino=monto_destino,
        porcentaje_comision=porcentaje_comision,
        tasa_comercial=tasa_comercial,
        metodo_pago=metodo_pago,
    )


def crear_transaccion(
    *,
    usuario_id,
    usuario_username="",
    cliente_id,
    tipo,
    moneda_origen_id,
    moneda_destino_id,
    monto,
    metodo_pago_id,
    clave_idempotencia,
    version_preview,
    tasa_preview=None,
):
    """Crea y persiste una operación validando cotización y comisión.

    Revalida identidad, cliente, monedas, método de pago y categoría,
    vuelve a obtener la tasa comercial vigente (bloqueando las filas del
    par), verifica si la cotización cambió comparando la versión de la
    tasa mostrada durante la previsualización contra la versión vigente y
    guarda los snapshots al crear una única Transaccion de forma atómica
    e idempotente.

    La decisión de cambio de cotización se basa exclusivamente en la
    versión de la tasa; el valor de tasa_preview se conserva solo como
    dato informativo y de compatibilidad, no para decidir la cancelación.

    Si la cotización cambió, la operación se registra como CANCELADA
    guardando el motivo y conservando el historial.

    Args:
        usuario_id (str): Identidad Keycloak del usuario que confirma.
        usuario_username (str): Nombre del usuario Keycloak que confirma.
        cliente_id (int): Cliente en cuyo nombre se realiza la operación.
        tipo (str): Tipo de operación (COMPRA o VENTA).
        moneda_origen_id (int): Moneda que se entrega.
        moneda_destino_id (int): Moneda que se recibe.
        monto (str | int | Decimal): Monto de la operación en moneda origen.
        metodo_pago_id (int): Método de pago del catálogo global seleccionado.
        clave_idempotencia (str): Clave única para evitar duplicados.
        version_preview (int): Versión de la tasa mostrada en la previsualización.
        tasa_preview (str | int | Decimal | None): Valor de tasa mostrado en la
            previsualización; solo informativo y de compatibilidad.

    Returns:
        ResultadoCrearTransaccion: Transacción creada o ya existente.

    Requisito relacionado: RF-11 y RF-12.
    """

    usuario_id = _validar_identidad(usuario_id)

    if tipo not in dict(Transaccion.TIPOS_TRANSACCION):
        raise ValidationError(
            {"tipo": "El tipo de operación debe ser COMPRA o VENTA."}
        )

    if not clave_idempotencia or not str(clave_idempotencia).strip():
        raise ValidationError(
            {"clave_idempotencia": "Debe indicar una clave de idempotencia."}
        )

    try:
        version_esperada = int(version_preview)
    except (TypeError, ValueError):
        raise ValidationError(
            {"version_preview": "Debe indicar la versión de la tasa de la previsualización."}
        )

    if version_esperada < 1:
        raise ValidationError(
            {"version_preview": "La versión de la tasa de la previsualización no es válida."}
        )

    existente = Transaccion.objects.filter(
        clave_idempotencia=clave_idempotencia
    ).first()

    if existente is not None:
        return ResultadoCrearTransaccion(
            transaccion=existente,
            repetida=True,
        )

    cliente = _obtener_cliente_activo(cliente_id)
    _validar_acceso_usuario_cliente(cliente, usuario_id)
    moneda_origen = _obtener_moneda_activa(
        moneda_origen_id,
        "moneda_origen",
    )
    moneda_destino = _obtener_moneda_activa(
        moneda_destino_id,
        "moneda_destino",
    )

    if moneda_origen.pk == moneda_destino.pk:
        raise ValidationError(
            {"monedas": "La moneda de origen y destino deben ser diferentes."}
        )

    monto_origen = _convertir_monto(monto)
    metodo_pago = _obtener_metodo_pago_activo(metodo_pago_id)
    porcentaje_comision = _porcentaje_comision_para_cliente(cliente)

    if _buscar_tasa_comercial_vigente(
        moneda_origen,
        moneda_destino,
    ) is None:
        raise ValidationError(
            {"tasa": "No existe una tasa comercial vigente para el par indicado."}
        )

    try:
        with transaction.atomic():
            tasa_comercial = _buscar_tasa_comercial_vigente(
                moneda_origen,
                moneda_destino,
                bloquear=True,
            )

            if tasa_comercial is None:
                raise ValidationError(
                    {"tasa": "No existe una tasa comercial vigente para el par indicado."}
                )

            tasa_aplicada = _tasa_segun_tipo(tipo, tasa_comercial)

            if tasa_aplicada <= 0:
                raise ValidationError(
                    {"tasa": "La tasa comercial debe ser mayor que cero."}
                )

            cambio_cotizacion = tasa_comercial.version != version_esperada

            monto_convertido, importe_comision, monto_destino = _calcular_operacion(
                monto_origen,
                tasa_aplicada,
                porcentaje_comision,
            )

            transaccion = Transaccion(
                clave_idempotencia=clave_idempotencia,
                cliente=cliente,
                creado_por_keycloak_id=usuario_id,
                creado_por_username=usuario_username,
                tipo=tipo,
                moneda_origen=moneda_origen,
                moneda_destino=moneda_destino,
                monto_origen=monto_origen,
                monto_destino=monto_destino,
                tasa_comercial=tasa_comercial,
                tasa_aplicada=tasa_aplicada,
                porcentaje_comision=porcentaje_comision,
                importe_comision=importe_comision,
                metodo_pago=metodo_pago,
                metodo_pago_nombre=metodo_pago.nombre,
                estado="CANCELADA" if cambio_cotizacion else "PENDIENTE",
            )

            if cambio_cotizacion:
                transaccion.cancelado_por_keycloak_id = usuario_id
                transaccion.cancelado_por_username = usuario_username
                transaccion.cancelado_en = timezone.now()
                transaccion.motivo_cancelacion = MOTIVO_CAMBIO_COTIZACION

            transaccion.full_clean()
            transaccion.save()

    except IntegrityError as exc:
        if not _es_conflicto_de_idempotencia(exc.__cause__):
            raise

        transaccion = Transaccion.objects.get(
            clave_idempotencia=clave_idempotencia,
        )
        return ResultadoCrearTransaccion(
            transaccion=transaccion,
            repetida=True,
        )

    return ResultadoCrearTransaccion(
        transaccion=transaccion,
        cambio_cotizacion=cambio_cotizacion,
    )


def cancelar_transaccion(
    *,
    transaccion_id,
    usuario_id,
    usuario_username="",
):
    """Cancela una transacción que se encuentre pendiente.

    La transacción se conserva en el historial y solamente cambia
    su estado a CANCELADA, registrando los datos de la cancelación.

    Requisito relacionado: HU-25.
    """

    usuario_id = _validar_identidad(usuario_id)

    with transaction.atomic():
        try:
            transaccion_obj = (
                Transaccion.objects
                .select_for_update()
                .select_related(
                    "cliente",
                    "moneda_origen",
                    "moneda_destino",
                )
                .get(pk=transaccion_id)
            )
        except (Transaccion.DoesNotExist, ValueError, TypeError):
            raise ValidationError(
                {"transaccion": "La transacción seleccionada no existe."}
            )

        _validar_acceso_usuario_cliente(
            transaccion_obj.cliente,
            usuario_id,
        )

        # Solo una transaccion pendiente puede cancelarse.
        if transaccion_obj.estado != "PENDIENTE":
            raise ValidationError(
                {"estado": "Solo una transacción PENDIENTE puede cancelarse."}
            )

        # Se conserva la operacion y se registran los datos de cancelacion.
        transaccion_obj.estado = "CANCELADA"
        transaccion_obj.cancelado_por_keycloak_id = usuario_id
        transaccion_obj.cancelado_por_username = usuario_username
        transaccion_obj.cancelado_en = timezone.now()
        transaccion_obj.motivo_cancelacion = (
            "Cancelación solicitada por el usuario."
        )

        transaccion_obj.full_clean()
        transaccion_obj.save()

    return transaccion_obj


def listar_metodos_pago_operacion(*, usuario_id, cliente_id, es_admin=False):
    """Devuelve los métodos activos disponibles para un cliente autorizado.

    El método preferido solamente se informa cuando continúa activo. La
    selección no procesa pagos: únicamente prepara el catálogo permitido para
    previsualizar y confirmar una operación.

    Args:
        usuario_id (str): Identidad Keycloak del usuario que consulta.
        cliente_id (int): Cliente seleccionado para la operación.
        es_admin (bool): Permite al administrador operar sobre cualquier
            cliente activo.

    Returns:
        tuple: Cliente validado, lista de métodos activos y método preferido
        activo (o ``None``).

    Requisitos relacionados: HU-23 y RF-13.
    """

    usuario_id = _validar_identidad(usuario_id)
    cliente = _obtener_cliente_activo(cliente_id)
    if not es_admin:
        _validar_acceso_usuario_cliente(cliente, usuario_id)

    metodos = list(MetodoPago.objects.activos())
    preferido = cliente.metodo_pago_preferido
    if preferido is None or not preferido.activo:
        preferido = None

    return cliente, metodos, preferido


def listar_transacciones(*, usuario_id, es_admin=False, cliente_id=None):
    """Consulta el historial autorizado de transacciones.

    Un usuario no administrador solo ve transacciones de los clientes
    asociados con una asociación activa. Es una consulta de solo lectura
    que utiliza los snapshots guardados sin recalcular valores.

    Args:
        usuario_id (str): Identidad Keycloak del usuario que consulta.
        es_admin (bool): Indica si el usuario posee el rol de administrador.
        cliente_id (int | None): Limita el historial al cliente seleccionado.

    Returns:
        list: Transacciones visibles para el usuario.
    """

    transacciones = (
        Transaccion.objects
        .select_related(
            "cliente",
            "moneda_origen",
            "moneda_destino",
            "tasa_comercial",
            "metodo_pago",
        )
        .distinct()
    )

    usuario_id = _validar_identidad(usuario_id)

    if cliente_id is not None:
        cliente = _obtener_cliente_activo(cliente_id)
        if not es_admin:
            _validar_acceso_usuario_cliente(cliente, usuario_id)
        transacciones = transacciones.filter(cliente=cliente)
    elif not es_admin:
        transacciones = transacciones.filter(
            cliente__usuarios_asignados__keycloak_user_id=usuario_id,
            cliente__usuarios_asignados__activo=True,
        )

    return list(transacciones)


def obtener_detalle_transaccion(
    *,
    transaccion_id,
    usuario_id,
    cliente_id,
    es_admin=False,
):
    """Obtiene una transacción del cliente seleccionado de forma segura.

    La consulta conserva los snapshots históricos y exige que la transacción
    pertenezca al cliente indicado. Para usuarios no administradores también
    revalida la asociación activa con ese cliente.

    Args:
        transaccion_id (int): Identificador de la transacción solicitada.
        usuario_id (str): Identidad Keycloak del usuario que consulta.
        cliente_id (int): Cliente seleccionado y esperado para la transacción.
        es_admin (bool): Permite consultar cualquier cliente activo.

    Returns:
        Transaccion: Registro histórico solicitado con sus relaciones.

    Raises:
        ValidationError: Si el cliente no está autorizado o la transacción no
        pertenece al contexto seleccionado.

    Requisitos relacionados: HU-24 y HU-32.
    """

    usuario_id = _validar_identidad(usuario_id)
    cliente = _obtener_cliente_activo(cliente_id)
    if not es_admin:
        _validar_acceso_usuario_cliente(cliente, usuario_id)

    try:
        return (
            Transaccion.objects
            .select_related(
                "cliente",
                "moneda_origen",
                "moneda_destino",
                "tasa_comercial",
                "metodo_pago",
            )
            .get(pk=transaccion_id, cliente=cliente)
        )
    except (Transaccion.DoesNotExist, TypeError, ValueError):
        raise ValidationError(
            {"transaccion": "La transacción no existe para el cliente seleccionado."}
        )
