"""RF-10/RN4: correo ante variaciones relevantes; política concreta acordada para HU-20."""

import logging
from decimal import Decimal, InvalidOperation, localcontext

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMessage, mailers
from django.core.validators import validate_email
from django.db import connection, transaction

from usuarios.keycloak import admin_request
from usuarios.services.keycloak import rol_efectivo

from .models import (BaseNotificacionTasa, ConfiguracionNotificacionTasa,
                     EventoNotificacionTasa, ResultadoNotificacionTasa)

logger = logging.getLogger(__name__)
TAMANO_PAGINA = 100


def configurar_umbral(*, valor, roles):
    """Solo ADMINISTRADOR efectivo configura un decimal finito y positivo."""
    if rol_efectivo(roles) != "ADMINISTRADOR":
        raise PermissionDenied("Solo ADMINISTRADOR puede configurar notificaciones.")
    if not isinstance(valor, (str, Decimal)):
        raise ValidationError("Ingresá un porcentaje decimal explícito.")
    try:
        umbral = Decimal(valor)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Ingresá un porcentaje numérico.")
    if not umbral.is_finite() or umbral <= 0:
        raise ValidationError("Ingresá un porcentaje finito y mayor que cero.")
    with transaction.atomic():
        configuracion = ConfiguracionNotificacionTasa.objects.select_for_update().get(pk=1)
        configuracion.umbral_porcentaje = umbral
        configuracion.full_clean()
        configuracion.save(update_fields=["umbral_porcentaje"])
    return configuracion


def obtener_destinatarios():
    """Recorre Admin REST paginada; admite solo cuentas activas con correo verificado válido."""
    encontrados = {}
    inicio = 0
    while True:
        pagina = admin_request(f"/users?first={inicio}&max={TAMANO_PAGINA}")
        if not isinstance(pagina, list):
            raise ValueError("Respuesta de usuarios inválida.")
        for usuario in pagina:
            if not isinstance(usuario, dict):
                raise ValueError("Respuesta de usuario inválida.")
            if usuario.get("enabled") is not True or usuario.get("emailVerified") is not True:
                continue
            identidad = usuario.get("id")
            correo = usuario.get("email")
            if not isinstance(identidad, str) or not identidad or len(identidad) > 255 or not isinstance(correo, str):
                continue
            correo = correo.strip()
            try:
                validate_email(correo)
            except ValidationError:
                continue
            encontrados[identidad] = correo
        if len(pagina) < TAMANO_PAGINA:
            return encontrados
        inicio += TAMANO_PAGINA


def registrar_evento(tasa, anterior):
    """Registra dentro de la transacción; un rollback descarta evento y callback."""
    evento = EventoNotificacionTasa.objects.create(
        tasa=tasa, compra_anterior=anterior.compra if anterior else None,
        venta_anterior=anterior.venta if anterior else None,
        umbral_porcentaje=ConfiguracionNotificacionTasa.objects.get(pk=1).umbral_porcentaje,
    )
    transaction.on_commit(lambda: procesar_evento(evento.pk), robust=True)


def _cambios_relevantes(evento, base):
    """Compara acumulación sin redondear; producto cruzado preserva el límite inclusivo exacto."""
    cambios = []
    # Los campos tienen 24 dígitos. Esta precisión cubre las operaciones exactas
    # de resta y producto; la división solo produce el porcentaje presentado.
    with localcontext() as contexto:
        contexto.prec = 80
        for lado in ("compra", "venta"):
            anterior = getattr(base, lado)
            nuevo = getattr(evento.tasa, lado)
            diferencia = abs(nuevo - anterior)
            if diferencia * 100 >= evento.umbral_porcentaje * anterior:
                cambios.append({"lado": lado, "anterior": str(anterior), "nueva": str(nuevo),
                                "porcentaje": str(diferencia / anterior * 100),
                                "direccion": "subida" if nuevo > anterior else "bajada"})
    return cambios


def enviar_correo(subject, message, from_email, recipient_list, *, envio):
    """Abre SMTP una sola vez por procesamiento; una apertura fallida no se reintenta.

    Se sigue registrando cada destinatario. Si SMTP aceptó la conexión pero
    rechazó un mensaje individual, los demás se envían por esa misma conexión.
    """
    if envio["fallo_conexion"]:
        raise ConnectionError("SMTP no disponible para este procesamiento.")
    if envio["conexion"] is None:
        try:
            conexion = mailers.create_connection("default")
            conexion.open()
            envio["conexion"] = conexion
        except Exception:
            envio["fallo_conexion"] = True
            raise
    return envio["conexion"].send_messages([EmailMessage(subject, message, from_email, recipient_list)])


def _procesar_destinatario(evento, identidad, correo, envio):
    """Reserva el resultado antes de SMTP y avanza solo las bases enviadas exitosamente."""
    tasa = evento.tasa
    with transaction.atomic():
        resultado, creado = ResultadoNotificacionTasa.objects.get_or_create(
            evento=evento, destinatario_id=identidad,
        )
        if not creado:
            return
        base, _ = BaseNotificacionTasa.objects.get_or_create(
            destinatario_id=identidad, moneda_origen=tasa.moneda_origen, moneda_destino=tasa.moneda_destino,
            defaults={"compra": evento.compra_anterior or tasa.compra,
                      "venta": evento.venta_anterior or tasa.venta},
        )
        cambios = _cambios_relevantes(evento, base) if evento.compra_anterior is not None else []
        resultado.cambios = cambios
        if not cambios:
            resultado.estado = "SIN_CAMBIOS"
        resultado.save(update_fields=["cambios", "estado"])
    if not cambios:
        return
    par = f"{tasa.moneda_origen.codigo}/{tasa.moneda_destino.codigo}"
    texto = [f"Variación de tasas comerciales: {par}"]
    for cambio in cambios:
        texto.append(f"{cambio['lado'].capitalize()} ({cambio['direccion']}): tasa anterior {cambio['anterior']}; "
                     f"tasa nueva {cambio['nueva']}; variación {cambio['porcentaje']} %.")
    try:
        aceptados = enviar_correo(f"Variación de tasas {par}", "\n".join(texto), None, [correo], envio=envio)
        if aceptados != 1:
            raise RuntimeError("El backend no aceptó el mensaje.")
    except Exception:
        resultado.estado = "FALLIDO"
        resultado.error = "envio_no_aceptado"
        resultado.save(update_fields=["estado", "error"])
        logger.error("Falló correo de tasas: evento=%s destinatario=%s error=envio_no_aceptado", evento.pk, identidad)
        return
    with transaction.atomic():
        for cambio in cambios:
            setattr(base, cambio["lado"], getattr(tasa, cambio["lado"]))
        base.save(update_fields=[cambio["lado"] for cambio in cambios])
        resultado.estado = "ENVIADO"
        resultado.save(update_fields=["estado"])


def procesar_evento(evento_id):
    """Procesa eventos confirmados en orden por par, sin bloquear filas de tasas.

    El bloqueo asesor pertenece solo a notificaciones; serializa callbacks de
    este par y no participa en actualizar_tasa_comercial. Keycloak/SMTP no
    mantienen transacciones de tasas abiertas. Resultados reservados evitan
    repetir un evento incluso después de un fallo. No hay reintentos ni worker.
    Una caída entre aceptación SMTP y persistencia deja resultado indeterminado;
    no se promete entrega exactamente una vez.
    """
    evento = EventoNotificacionTasa.objects.select_related("tasa").get(pk=evento_id)
    clave = f"notificaciones_tasas:{evento.tasa.moneda_origen_id}:{evento.tasa.moneda_destino_id}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", [clave])
    envio = {"conexion": None, "fallo_conexion": False}
    try:
        pendientes = EventoNotificacionTasa.objects.filter(
            tasa__moneda_origen_id=evento.tasa.moneda_origen_id,
            tasa__moneda_destino_id=evento.tasa.moneda_destino_id, procesado=False,
        ).select_related("tasa__moneda_origen", "tasa__moneda_destino").order_by("tasa__version", "pk")
        for pendiente in pendientes:
            try:
                destinatarios = obtener_destinatarios()
            except Exception:
                pendiente.error_destinatarios = "consulta_keycloak_fallida"
                logger.error("Falló consulta de destinatarios: evento=%s error=consulta_keycloak_fallida", pendiente.pk)
            else:
                for identidad, correo in destinatarios.items():
                    try:
                        _procesar_destinatario(pendiente, identidad, correo, envio)
                    except Exception:
                        logger.error("Falló procesamiento de tasas: evento=%s destinatario=%s error=persistencia_fallida",
                                     pendiente.pk, identidad)
                        ResultadoNotificacionTasa.objects.filter(evento=pendiente, destinatario_id=identidad).update(
                            error="persistencia_fallida",
                        )
            pendiente.procesado = True
            pendiente.save(update_fields=["procesado", "error_destinatarios"])
    finally:
        if envio["conexion"] is not None:
            try:
                envio["conexion"].close()
            except Exception:
                logger.error("Falló cierre SMTP: evento=%s error=cierre_smtp_fallido", evento.pk)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", [clave])
