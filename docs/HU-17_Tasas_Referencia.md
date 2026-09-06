# Documentación técnica — HU-17 Consultar y visualizar tasas

**Proyecto:** Global Exchange

**Integrante:** Guillermo Benítez

**Responsabilidad:** Backend completo

**Historia de usuario:** HU-17 — Consultar y visualizar tasas

**Sprint:** 2 — Hito 4

**Rama:** `feature/hu-17-consultar-visualizar-tasas`

**Tecnologías:** Django 6.1, PostgreSQL 17, Requests, Docker y unittest/mock

---

## 1. Objetivo

Obtener tasas de referencia desde un proveedor externo, validarlas, persistir la última respuesta válida y ofrecer un contrato de consulta que distinga expresamente datos actualizados, datos de respaldo desactualizados e indisponibilidad.

## 2. Alcance implementado

- Consulta de tasas de referencia desde un proveedor externo real.
- Relación de cada tasa con una moneda base y una moneda cotizada de HU-36.
- Registro del tipo, fuente, fecha/hora y vigencia.
- Adaptador desacoplado de la lógica de negocio.
- Configuración externa de URL, credencial, timeout, fuente, base y vigencia.
- Validación y normalización estricta de la respuesta.
- Persistencia de la respuesta externa y del último valor por par.
- Fallback al último dato válido ante fallos posteriores.
- Indisponibilidad explícita cuando no existe información previa.
- Endpoint autenticado y contrato preparado para el frontend.
- Separación entre tasa de referencia y tasa comercial.
- Pruebas unitarias y de integración con mocks.

No forma parte de HU-17 la edición de tasas comerciales. Esa responsabilidad corresponde a HU-21.

## 3. Arquitectura y flujo técnico

```text
GET /tasas/
  -> autenticación OIDC
  -> servicio consultar_tasas_referencia
  -> catálogo de monedas activas (HU-36)
  -> adaptador ProveedorTasasHTTP
  -> validación y normalización
  -> transacción PostgreSQL
       -> ConsultaProveedorTasas (respuesta válida)
       -> TasaReferencia (último valor por par)
  -> respuesta JSON
```

Si el proveedor falla, el servicio no guarda la respuesta fallida:

```text
Fallo externo
  |-- existe TasaReferencia -> HTTP 200, estado desactualizado
  `-- no existe dato previo -> HTTP 503, estado indisponible
```

### 3.1 Organización del módulo

```text
tasas/
|-- models.py                    Persistencia y restricciones
|-- providers.py                 Adaptador del proveedor externo
|-- services.py                  Caso de uso, transacción y fallback
|-- views.py                     Contrato HTTP/JSON
|-- urls.py                      Ruta pública del módulo
|-- admin.py                     Inspección administrativa
|-- tests.py                     Pruebas con mocks e integración
`-- migrations/0001_initial.py   Esquema PostgreSQL
```

### 3.2 Responsabilidad de cada capa

| Capa | Responsabilidad |
|---|---|
| `ProveedorTasasHTTP` | Comunicación HTTP, timeout y transformación inicial. |
| `RespuestaTasas` | Estructura normalizada independiente del proveedor. |
| `consultar_tasas_referencia` | Orquestación, selección de monedas, persistencia y fallback. |
| Modelos | Integridad, trazabilidad y último dato válido. |
| Vista | Serialización y códigos HTTP. |

## 4. Modelos y persistencia

### 4.1 `ConsultaProveedorTasas`

Conserva cada respuesta externa válida para trazabilidad:

- Fuente.
- Moneda base.
- Fecha/hora informada por el proveedor.
- Fecha/hora de recepción.
- Respuesta JSON original.

### 4.2 `TasaReferencia`

Mantiene el último dato válido normalizado por par:

- Moneda base y moneda cotizada.
- Valor decimal positivo.
- Fuente.
- Fecha/hora del proveedor.
- Vigencia calculada.
- Consulta de origen.

La base de datos impide pares repetidos, monedas iguales en un par y valores menores o iguales a cero.

### 4.3 Estrategia de persistencia

Cada respuesta válida genera una `ConsultaProveedorTasas`. Los pares normalizados actualizan `TasaReferencia` mediante `update_or_create`. Así se conserva la trazabilidad de consultas válidas y, al mismo tiempo, se dispone de una lectura eficiente del último valor conocido.

Toda la escritura se realiza dentro de `transaction.atomic()`. Una respuesta parcial o un error de persistencia no deja tasas actualizadas a medias.

## 5. Proveedor externo

El proveedor predeterminado es **ExchangeRate-API**, usando su endpoint abierto:

```text
https://open.er-api.com/v6/latest/USD
```

El adaptador no incorpora esta dirección directamente en la lógica. La URL proviene de configuración y `__BASE__` se reemplaza por el código de moneda base.

## 6. Configuración

| Variable | Valor predeterminado | Descripción |
|---|---|---|
| `TASAS_PROVIDER_URL` | `https://open.er-api.com/v6/latest/__BASE__` | URL; debe admitir el marcador `__BASE__`. |
| `TASAS_PROVIDER_API_KEY` | vacío | Credencial opcional enviada como Bearer token. |
| `TASAS_PROVIDER_TIMEOUT` | `5` | Timeout HTTP en segundos. |
| `TASAS_PROVIDER_NAME` | `ExchangeRate-API` | Fuente visible y persistida. |
| `TASAS_BASE_CURRENCY` | `USD` | Código de moneda base activa. |
| `TASAS_VALIDITY_SECONDS` | `86400` | Duración de la vigencia desde la fecha externa. |

No se deben versionar credenciales reales. Deben declararse en `.env`.

## 7. Contrato de consulta

### 7.1 Solicitud

```http
GET /tasas/
Cookie: sessionid=...
```

La ruta requiere una sesión OIDC válida.

### 7.2 Respuesta actualizada — HTTP 200

```json
{
  "estado": "actualizado",
  "mensaje": null,
  "tasas_referencia": [
    {
      "id": 1,
      "tipo": "REFERENCIA",
      "par": "USD/EUR",
      "moneda_base": "USD",
      "moneda_cotizada": "EUR",
      "valor": "0.8600000000",
      "fuente": "ExchangeRate-API",
      "fecha_hora": "2026-09-04T12:00:00+00:00",
      "vigente_hasta": "2026-09-05T12:00:00+00:00",
      "desactualizada": false
    }
  ],
  "tasas_comerciales": []
}
```

### 7.3 Fallback — HTTP 200

Devuelve el mismo formato con:

```json
{
  "estado": "desactualizado",
  "mensaje": "El proveedor excedió el tiempo de espera.",
  "tasas_referencia": [{"desactualizada": true}],
  "tasas_comerciales": []
}
```

### 7.4 Sin datos previos — HTTP 503

```json
{
  "estado": "indisponible",
  "mensaje": "No fue posible consultar el proveedor de tasas.",
  "tasas_referencia": [],
  "tasas_comerciales": []
}
```

### 7.5 Otros estados

- `401`: no existe una sesión válida.
- `vacio`: la moneda base existe, pero no hay monedas cotizadas activas.
- `indisponible`: la moneda base configurada no existe o está inactiva.

## 8. Separación respecto de HU-21

HU-17 administra exclusivamente referencias externas. El contrato reserva `tasas_comerciales` como colección independiente, inicialmente vacía. HU-21 deberá poblarla desde su propio modelo/servicio sin modificar ni permitir edición manual de `TasaReferencia`.

## 9. Validaciones y errores controlados

El adaptador rechaza:

- Timeout.
- Error de red.
- Estado HTTP inválido.
- JSON inválido.
- Estructura incompleta.
- Moneda base diferente.
- Monedas solicitadas ausentes.
- Valores no numéricos, infinitos, cero o negativos.
- Fecha/hora inválida.

Solo una respuesta completamente válida entra en la transacción de persistencia.

## 10. Pruebas y evidencia técnica

```powershell
docker compose exec web python manage.py test tasas
```

Las pruebas usan mocks y no dependen de Internet. Cubren normalización, éxito, timeout, HTTP inválido, JSON inválido/incompleto, valores inválidos, persistencia, actualización, fallback, ausencia de datos, moneda base inactiva, catálogo vacío, autenticación y respuesta del endpoint.

Resultados obtenidos durante la implementación:

| Verificación | Resultado |
|---|---|
| Pruebas específicas de HU-17 | 16 aprobadas |
| Regresión completa del proyecto | 127 aprobadas |
| `manage.py check` | Sin observaciones |
| `makemigrations --check --dry-run` | Sin cambios pendientes |
| Consulta real ExchangeRate-API | Exitosa para EUR, PYG y BRL con base USD |

## 11. Migración y ejecución

```powershell
docker compose exec web python manage.py migrate
```

La migración incorporada es `tasas/migrations/0001_initial.py`.

## 12. Dependencias y condiciones operativas

- HU-36 debe tener registrada y activa la moneda definida en `TASAS_BASE_CURRENCY`.
- Debe existir al menos otra moneda activa para formar un par.
- El contenedor `web` necesita salida HTTPS para consultar al proveedor.
- PostgreSQL debe estar disponible para guardar la respuesta válida.
- El endpoint requiere una sesión OIDC vigente.

Si estas condiciones no se cumplen, el servicio informa el estado correspondiente y no genera valores sustitutos.

## 13. Decisiones técnicas relevantes

1. Se eligió `Decimal` para evitar errores de precisión de punto flotante.
2. La integración externa se aisló en un adaptador reemplazable.
3. Los tests no dependen de Internet; la red se sustituye mediante mocks.
4. La última tasa por par se separó del histórico de respuestas válidas.
5. Los errores del proveedor se transforman en mensajes controlados.
6. El endpoint devuelve valores decimales como texto para preservar precisión.
7. Las tasas comerciales se mantienen separadas y no se simulan antes de HU-21.

## 14. Estado final

El backend correspondiente a Guillermo para HU-17 se encuentra implementado, migrado, documentado y cubierto por pruebas. El contrato está disponible para que el frontend asignado a Axel reemplace las tasas constantes por información real del endpoint.
