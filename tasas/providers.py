from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
import math

import requests
from django.conf import settings


class ProveedorTasasError(Exception):
    """Error controlado al consultar o interpretar el proveedor externo."""


@dataclass(frozen=True)
class RespuestaTasas:
    """Respuesta externa validada y normalizada, independiente del proveedor."""

    moneda_base: str
    tasas: dict[str, Decimal]
    fuente: str
    fecha_hora: datetime
    respuesta_original: dict


class ProveedorTasasHTTP:
    """Adaptador HTTP del proveedor configurado mediante variables de entorno."""

    def __init__(self, *, session=None):
        self.session = session or requests.Session()

    def obtener(self, moneda_base, monedas_cotizadas):
        """Obtiene tasas y rechaza respuestas parciales, no numéricas o no positivas."""

        base = moneda_base.strip().upper()
        codigos = {codigo.strip().upper() for codigo in monedas_cotizadas}
        url = settings.TASAS_PROVIDER_URL.replace("__BASE__", base)
        if "__BASE__" in url or not url.startswith(("http://", "https://")):
            raise ProveedorTasasError("La URL del proveedor está mal configurada.")

        headers = {"Accept": "application/json"}
        if settings.TASAS_PROVIDER_API_KEY:
            headers["Authorization"] = f"Bearer {settings.TASAS_PROVIDER_API_KEY}"

        try:
            response = self.session.get(
                url,
                headers=headers,
                timeout=settings.TASAS_PROVIDER_TIMEOUT,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise ProveedorTasasError("El proveedor excedió el tiempo de espera.") from exc
        except requests.RequestException as exc:
            raise ProveedorTasasError("No fue posible consultar el proveedor de tasas.") from exc

        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise ProveedorTasasError("El proveedor devolvió JSON inválido.") from exc

        if not isinstance(payload, dict):
            raise ProveedorTasasError("La respuesta del proveedor tiene un formato inválido.")
        if payload.get("result") not in (None, "success"):
            raise ProveedorTasasError("El proveedor informó que la consulta no fue exitosa.")

        base_respuesta = str(payload.get("base_code") or payload.get("base") or "").upper()
        rates = payload.get("rates") or payload.get("conversion_rates")
        if base_respuesta != base or not isinstance(rates, dict):
            raise ProveedorTasasError("La respuesta del proveedor está incompleta.")

        faltantes = codigos - set(rates)
        if faltantes:
            raise ProveedorTasasError(
                "La respuesta no contiene todas las monedas solicitadas: "
                + ", ".join(sorted(faltantes))
                + "."
            )

        normalizadas = {}
        for codigo in codigos:
            try:
                valor = Decimal(str(rates[codigo]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ProveedorTasasError(f"La tasa de {codigo} no es numérica.") from exc
            if not valor.is_finite() or valor <= 0 or not math.isfinite(float(valor)):
                raise ProveedorTasasError(f"La tasa de {codigo} debe ser positiva y finita.")
            normalizadas[codigo] = valor

        timestamp = payload.get("time_last_update_unix")
        try:
            fecha_hora = datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError) as exc:
            raise ProveedorTasasError("La fecha/hora del proveedor es inválida.") from exc

        return RespuestaTasas(
            moneda_base=base,
            tasas=normalizadas,
            fuente=settings.TASAS_PROVIDER_NAME,
            fecha_hora=fecha_hora,
            respuesta_original=payload,
        )
