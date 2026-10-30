"""Contratos de proveedores externos usados por el modulo de facturacion."""

from .factura_segura import (
    ArchivoFactura,
    FacturaSeguraAutenticacionError,
    FacturaSeguraConfiguracionError,
    FacturaSeguraNoDisponible,
    FacturaSeguraProveedorError,
    FacturaSeguraRespuestaInvalida,
    FacturaSeguraResultadoIndeterminado,
    FacturaSeguraValidacionError,
    FacturaSeguraClient,
    ResultadoGeneracion,
    ResultadoOperacion,
    obtener_factura_segura_client,
)
from .emision import ResultadoEmision, generar_documento_una_vez

__all__ = [
    "ArchivoFactura",
    "FacturaSeguraAutenticacionError",
    "FacturaSeguraConfiguracionError",
    "FacturaSeguraNoDisponible",
    "FacturaSeguraProveedorError",
    "FacturaSeguraRespuestaInvalida",
    "FacturaSeguraResultadoIndeterminado",
    "FacturaSeguraValidacionError",
    "FacturaSeguraClient",
    "ResultadoGeneracion",
    "ResultadoOperacion",
    "obtener_factura_segura_client",
    "ResultadoEmision",
    "generar_documento_una_vez",
]
