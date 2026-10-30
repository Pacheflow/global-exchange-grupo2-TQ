"""Adaptador seguro y sin persistencia para la API ESI de Factura Segura.

La capa no decide reglas tributarias ni crea modelos de Factura. Recibe un DE
ya validado por el modulo de dominio, ejecuta el contrato HTTP del proveedor y
devuelve resultados tipados. En particular, ``generar_de`` nunca se reintenta
automaticamente: un timeout puede significar que el proveedor si proceso el
documento y el coordinador persistente debe conciliarlo antes de reemitir.
"""

from dataclasses import dataclass
import json
import math
import re
from typing import Any
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings


CDC_RE = re.compile(r"[A-Za-z0-9]{20,64}")
OPERACIONES_POST = frozenset({"calcular_de", "generar_de", "get_estado_sifen"})
OPERACIONES_DESCARGA = frozenset({"dwn_kude", "dwn_xml"})


class FacturaSeguraError(Exception):
    """Base de errores controlados; nunca contiene token ni payload completo."""


class FacturaSeguraConfiguracionError(FacturaSeguraError):
    """La integracion no posee una configuracion segura y utilizable."""


class FacturaSeguraValidacionError(FacturaSeguraError):
    """La solicitud local viola el contrato minimo del adaptador."""


class FacturaSeguraAutenticacionError(FacturaSeguraError):
    """El proveedor rechazo el token ESI."""


class FacturaSeguraNoDisponible(FacturaSeguraError):
    """Fallo transitorio de red o del proveedor en una operacion consultable."""


class FacturaSeguraResultadoIndeterminado(FacturaSeguraError):
    """No se sabe si generar_de fue procesado; no debe reemitirse a ciegas."""


class FacturaSeguraRespuestaInvalida(FacturaSeguraError):
    """El proveedor respondio, pero no con el contrato esperado."""


class FacturaSeguraProveedorError(FacturaSeguraError):
    """Factura Segura devolvio ``code`` negativo."""

    def __init__(self, *, codigo: int, descripcion: str, operacion_id: str | None):
        super().__init__("Factura Segura rechazo la operacion solicitada.")
        self.codigo = codigo
        self.descripcion = descripcion
        self.operacion_id = operacion_id


@dataclass(frozen=True)
class ResultadoOperacion:
    codigo: int
    descripcion: str
    operacion_id: str | None
    resultados: tuple[Any, ...]


@dataclass(frozen=True)
class ResultadoGeneracion(ResultadoOperacion):
    cdc: str


@dataclass(frozen=True)
class ArchivoFactura:
    contenido: bytes
    content_type: str
    nombre: str


def _texto_controlado(valor: Any, *, maximo: int) -> str:
    if not isinstance(valor, str):
        raise FacturaSeguraRespuestaInvalida("La respuesta contiene texto invalido.")
    texto = valor.strip()
    if len(texto) > maximo or any(ord(caracter) < 32 and caracter not in "\r\n\t" for caracter in texto):
        raise FacturaSeguraRespuestaInvalida("La respuesta contiene texto invalido.")
    return texto


class FacturaSeguraClient:
    """Cliente ESI configurable, estricto y sin reintentos implicitos."""

    def __init__(
        self,
        *,
        api_url: str,
        token: str,
        ruc_emisor: str,
        timeout: float = 30,
        max_download_bytes: int = 15 * 1024 * 1024,
        session=None,
    ):
        self.api_url = api_url.rstrip("/") if isinstance(api_url, str) else api_url
        self.token = token
        self.ruc_emisor = ruc_emisor
        self.timeout = timeout
        self.max_download_bytes = max_download_bytes
        self.session = session or requests.Session()
        self._validar_configuracion()

    def _validar_configuracion(self):
        try:
            url = urlsplit(self.api_url)
        except (TypeError, ValueError):
            url = None
        if (
            url is None or url.scheme != "https" or not url.netloc or url.username or url.password
            or url.query or url.fragment
        ):
            raise FacturaSeguraConfiguracionError("La URL HTTPS de Factura Segura no es valida.")
        if (
            not isinstance(self.token, str) or not self.token.strip() or len(self.token) > 4096
            or any(caracter.isspace() for caracter in self.token)
        ):
            raise FacturaSeguraConfiguracionError("El token ESI no esta configurado correctamente.")
        if not isinstance(self.ruc_emisor, str) or not re.fullmatch(r"[0-9]{5,20}", self.ruc_emisor):
            raise FacturaSeguraConfiguracionError("El RUC del emisor debe contener solo digitos, sin DV.")
        if (
            not isinstance(self.timeout, (int, float)) or isinstance(self.timeout, bool)
            or not math.isfinite(self.timeout) or not 0 < self.timeout <= 60
        ):
            raise FacturaSeguraConfiguracionError("El timeout debe ser un numero entre 0 y 60 segundos.")
        if type(self.max_download_bytes) is not int or not 1024 <= self.max_download_bytes <= 50 * 1024 * 1024:
            raise FacturaSeguraConfiguracionError("El limite de descarga no es valido.")

    @property
    def _headers(self):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authentication-Token": self.token,
        }

    @staticmethod
    def _validar_de(de):
        if not isinstance(de, dict) or not de or not all(isinstance(clave, str) for clave in de):
            raise FacturaSeguraValidacionError("El DE debe ser un objeto JSON no vacio.")
        try:
            json.dumps(de, ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise FacturaSeguraValidacionError("El DE debe contener datos JSON validos.") from error

    @staticmethod
    def _validar_cdc(cdc):
        if not isinstance(cdc, str) or not CDC_RE.fullmatch(cdc):
            raise FacturaSeguraValidacionError("El CDC no tiene un formato valido.")
        return cdc

    def _post(self, operacion: str, params: dict, *, emision=False) -> ResultadoOperacion:
        if operacion not in OPERACIONES_POST or not isinstance(params, dict):
            raise FacturaSeguraValidacionError("La operacion ESI no es valida.")
        try:
            respuesta = self.session.post(
                self.api_url,
                json={"operation": operacion, "params": params},
                headers=self._headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.Timeout as error:
            excepcion = FacturaSeguraResultadoIndeterminado if emision else FacturaSeguraNoDisponible
            raise excepcion("Factura Segura excedio el tiempo de espera.") from error
        except requests.RequestException as error:
            excepcion = FacturaSeguraResultadoIndeterminado if emision else FacturaSeguraNoDisponible
            raise excepcion("No fue posible confirmar el resultado con Factura Segura.") from error
        if respuesta.status_code in {301, 302, 303, 307, 308}:
            raise FacturaSeguraRespuestaInvalida("Factura Segura intento redirigir una solicitud autenticada.")
        if respuesta.status_code in {401, 403}:
            raise FacturaSeguraAutenticacionError("Factura Segura rechazo el token ESI.")
        if respuesta.status_code >= 500:
            excepcion = FacturaSeguraResultadoIndeterminado if emision else FacturaSeguraNoDisponible
            raise excepcion("Factura Segura no se encuentra disponible.")
        if respuesta.status_code < 200 or respuesta.status_code >= 300:
            raise FacturaSeguraRespuestaInvalida("Factura Segura rechazo la solicitud HTTP.")
        try:
            payload = respuesta.json()
        except (TypeError, ValueError) as error:
            raise FacturaSeguraRespuestaInvalida("Factura Segura devolvio JSON invalido.") from error
        return self._interpretar(payload)

    @staticmethod
    def _interpretar(payload) -> ResultadoOperacion:
        if not isinstance(payload, dict) or type(payload.get("code")) is not int:
            raise FacturaSeguraRespuestaInvalida("La respuesta ESI no contiene un codigo valido.")
        descripcion = _texto_controlado(payload.get("description", ""), maximo=4000)
        info = payload.get("operation_info")
        if info is not None and not isinstance(info, dict):
            raise FacturaSeguraRespuestaInvalida("operation_info tiene un formato invalido.")
        operacion_id = None
        if info and info.get("id") is not None:
            operacion_id = _texto_controlado(str(info["id"]), maximo=255)
        resultados = payload.get("results", [])
        if not isinstance(resultados, list):
            raise FacturaSeguraRespuestaInvalida("results debe ser una lista.")
        resultado = ResultadoOperacion(
            codigo=payload["code"], descripcion=descripcion,
            operacion_id=operacion_id, resultados=tuple(resultados),
        )
        if resultado.codigo < 0:
            raise FacturaSeguraProveedorError(
                codigo=resultado.codigo, descripcion=resultado.descripcion,
                operacion_id=resultado.operacion_id,
            )
        return resultado

    def calcular_de(self, de: dict) -> ResultadoOperacion:
        self._validar_de(de)
        return self._post("calcular_de", {"DE": de})

    def generar_de(self, de_calculado: dict) -> ResultadoGeneracion:
        """Genera una sola vez; timeout/conexion/5xx dejan resultado indeterminado."""
        self._validar_de(de_calculado)
        resultado = self._post("generar_de", {"DE": de_calculado}, emision=True)
        if not resultado.resultados or not isinstance(resultado.resultados[0], dict):
            raise FacturaSeguraRespuestaInvalida("generar_de no devolvio un resultado utilizable.")
        datos = resultado.resultados[0]
        cdc = datos.get("CDC", datos.get("cdc"))
        self._validar_cdc(cdc)
        return ResultadoGeneracion(
            codigo=resultado.codigo, descripcion=resultado.descripcion,
            operacion_id=resultado.operacion_id, resultados=resultado.resultados,
            cdc=cdc,
        )

    def consultar_estado(self, cdc: str) -> ResultadoOperacion:
        cdc = self._validar_cdc(cdc)
        return self._post("get_estado_sifen", {"CDC": cdc, "dRucEm": self.ruc_emisor})

    def descargar_kude(self, cdc: str) -> ArchivoFactura:
        return self._descargar("dwn_kude", cdc, "application/pdf", "pdf")

    def descargar_xml(self, cdc: str) -> ArchivoFactura:
        return self._descargar("dwn_xml", cdc, ("application/xml", "text/xml"), "xml")

    def _descargar(self, operacion, cdc, content_types, extension):
        if operacion not in OPERACIONES_DESCARGA:
            raise FacturaSeguraValidacionError("La descarga ESI no es valida.")
        cdc = self._validar_cdc(cdc)
        url = "/".join((self.api_url, operacion, quote(self.ruc_emisor, safe=""), quote(cdc, safe="")))
        headers = {"Accept": "*/*", "Authentication-Token": self.token}
        try:
            respuesta = self.session.get(
                url, headers=headers, timeout=self.timeout,
                allow_redirects=False, stream=True,
            )
        except requests.Timeout as error:
            raise FacturaSeguraNoDisponible("Factura Segura excedio el tiempo de espera.") from error
        except requests.RequestException as error:
            raise FacturaSeguraNoDisponible("No fue posible descargar el documento.") from error
        if respuesta.status_code in {401, 403}:
            raise FacturaSeguraAutenticacionError("Factura Segura rechazo el token ESI.")
        if respuesta.status_code >= 500:
            raise FacturaSeguraNoDisponible("Factura Segura no se encuentra disponible.")
        if respuesta.status_code != 200 or respuesta.status_code in {301, 302, 303, 307, 308}:
            raise FacturaSeguraRespuestaInvalida("Factura Segura no devolvio el archivo solicitado.")
        esperado = (content_types,) if isinstance(content_types, str) else content_types
        recibido = respuesta.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if recibido not in esperado:
            raise FacturaSeguraRespuestaInvalida("El tipo de archivo recibido no es valido.")
        partes = []
        total = 0
        for parte in respuesta.iter_content(chunk_size=64 * 1024):
            if not parte:
                continue
            total += len(parte)
            if total > self.max_download_bytes:
                raise FacturaSeguraRespuestaInvalida("El archivo excede el limite permitido.")
            partes.append(parte)
        if not partes:
            raise FacturaSeguraRespuestaInvalida("Factura Segura devolvio un archivo vacio.")
        return ArchivoFactura(
            contenido=b"".join(partes), content_type=recibido,
            nombre=f"{operacion.removeprefix('dwn_')}-{cdc}.{extension}",
        )


def obtener_factura_segura_client(*, session=None) -> FacturaSeguraClient:
    """Construye el unico cliente permitido usando secretos del servidor."""
    return FacturaSeguraClient(
        api_url=settings.FACTURA_SEGURA_API_URL,
        token=settings.FACTURA_SEGURA_TOKEN,
        ruc_emisor=settings.FACTURA_SEGURA_RUC,
        timeout=settings.FACTURA_SEGURA_TIMEOUT_SECONDS,
        max_download_bytes=settings.FACTURA_SEGURA_MAX_DOWNLOAD_BYTES,
        session=session,
    )
