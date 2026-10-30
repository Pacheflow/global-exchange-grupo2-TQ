# HU-28 — Integración técnica con Factura Segura

## Alcance de Guillermo Benítez

Esta entrega implementa la frontera técnica entre Global Exchange y la API ESI
de Factura Segura. No implementa la lógica tributaria ni las HU-29/HU-30: el
modelo de Factura, su asociación funcional, pantallas, correo y reglas fiscales
corresponden al módulo que consumirá este contrato.

La fuente funcional entregada define el flujo
`calcular_de → generar_de → get_estado_sifen` y las descargas `dwn_kude` y
`dwn_xml`. El tratamiento fiscal de operaciones cambiarias, IVA y conversión de
EUR/BRL no está definido; el adaptador no inventa esos datos.

## Componentes implementados

| Componente | Responsabilidad |
|---|---|
| `facturacion/services/factura_segura.py` | Cliente HTTPS, token ESI, validación de contrato, errores, timeout y descargas limitadas. |
| `facturacion/services/emision.py` | Reserva persistente e idempotente antes de `generar_de`; nunca reemite una clave existente. |
| `facturacion/models.py` | Ledger técnico del intento, huella, estado, CDC, ID ESI y error del proveedor. No es el modelo Factura. |
| `facturacion/admin.py` | Consulta de solo lectura para auditoría técnica. |
| `facturacion/test_factura_segura.py` | Pruebas aisladas, sin red ni credenciales reales. |

## Configuración

```env
FACTURA_SEGURA_API_URL=https://apitest.facturasegura.com.py/misife00/v1/esi
FACTURA_SEGURA_TOKEN=
FACTURA_SEGURA_RUC=
FACTURA_SEGURA_TIMEOUT_SECONDS=30
FACTURA_SEGURA_MAX_DOWNLOAD_BYTES=15728640
```

El token es el token técnico ESI de Factura Segura, no un token de Keycloak.
Solo vive en `.env` o en el gestor de secretos del servidor. El cliente exige
HTTPS, impide credenciales embebidas en URL, no sigue redirecciones autenticadas
y nunca incluye el token dentro del JSON.

## Contrato para HU-29

### Calcular sin emitir

```python
from facturacion.services import obtener_factura_segura_client

client = obtener_factura_segura_client()
resultado = client.calcular_de(de_resumido)
```

`resultado.resultados` conserva la lista validada devuelta por el proveedor. La
capa HU-29 debe extraer y validar el DE calculado de acuerdo con el contrato
real habilitado para el emisor de TEST.

### Generar de forma idempotente

```python
from facturacion.services import generar_documento_una_vez

resultado = generar_documento_una_vez(
    clave_idempotencia=f"factura:transaccion:{transaccion.id}:v1",
    de_calculado=de_calculado,
)
intento = resultado.intento
```

| Estado | Significado | Acción permitida |
|---|---|---|
| `EN_PROCESO` | Se reservó la emisión; el proceso aún no cerró. | No emitir otra vez. |
| `GENERADA` | Factura Segura respondió con CDC válido. | Enlazar CDC y consultar SIFEN. |
| `INDETERMINADA` | Timeout, conexión, 5xx o respuesta inutilizable tras emitir. | Conciliar o contactar soporte; no reemitir. |
| `ERROR` | Error confirmado del proveedor o de autenticación/configuración. | Corregir y definir un reintento explícito; no usar otra clave a ciegas. |

Una misma clave con el mismo documento reutiliza el intento. La misma clave con
otro JSON se rechaza. La huella SHA-256 se calcula sobre JSON canónico; el DE
completo no se guarda en el ledger técnico.

### Consultar estado y descargar

```python
estado = client.consultar_estado(intento.cdc)
kude = client.descargar_kude(intento.cdc)
xml = client.descargar_xml(intento.cdc)
```

`code >= 0` significa que la operación de la API fue atendida; no equivale a
aprobación fiscal. HU-29 debe interpretar y persistir por separado
`estado_inu`, después `estado_can` y finalmente `estado_sifen`.

Las descargas validan estado HTTP, MIME, tamaño máximo y contenido no vacío. Una
vista HU-30 debe volver a validar permisos antes de devolver bytes al navegador.

## Taxonomía de errores

| Excepción | Interpretación |
|---|---|
| `FacturaSeguraConfiguracionError` | URL, token, RUC o límites inválidos. |
| `FacturaSeguraValidacionError` | DE, CDC o clave local inválidos; no se hace IO. |
| `FacturaSeguraAutenticacionError` | Token rechazado con 401/403. |
| `FacturaSeguraNoDisponible` | Timeout/red/5xx durante cálculo, consulta o descarga. |
| `FacturaSeguraResultadoIndeterminado` | Timeout/red/5xx durante `generar_de`; puede haberse emitido. |
| `FacturaSeguraRespuestaInvalida` | JSON, estructura, redirección, CDC o archivo inesperados. |
| `FacturaSeguraProveedorError` | `code` negativo; conserva código, descripción e ID ESI internamente. |

Las excepciones públicas no incluyen token, cuerpo completo ni detalles de
`requests`. Las descripciones se guardan para auditoría, pero no deben mostrarse
directamente al usuario.

## Pruebas

```bash
python manage.py test facturacion --noinput
```

La suite cubre configuración, petición exacta, cabecera ESI, generación/CDC,
códigos negativos, autenticación, JSON inválido, redirecciones, timeouts,
MIME/tamaño de descargas e idempotencia persistente. Toda llamada externa está
simulada.

## Pendientes externos, no defectos del adaptador

- Credenciales y emisor ESI autorizados en TEST.
- Confirmación del esquema tributario para compra/venta de divisas.
- JSON fiscal real, timbrado, establecimiento y punto de expedición.
- Confirmación contractual de rutas de descarga para la versión habilitada.
- Modelo Factura/DetalleFactura, estados funcionales, permisos, vistas y correo
  de HU-29/HU-30.
- Tarea programada para consultar SIFEN después de la emisión.

No debe probarse `generar_de` contra el proveedor hasta contar con esos datos:
un timeout no autoriza a repetir una emisión.
