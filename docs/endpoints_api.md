# Endpoints API — Global Exchange

> Estado real verificado del código, rama `frontend-integration`, HEAD `590f131`.
> Prefijo base: `/api/`.

## Convenciones

- Todos los endpoints requieren sesión autenticada salvo indicación.
- Lectura JSON: `Accept: application/json` o cualquier request que no pida HTML explícitamente.
- Escritura: `Content-Type: application/json` con `X-CSRFToken` desde cookie.
- `metodos_pago` es **dual**: responde JSON si `Accept: application/json` o `Content-Type: application/json`, o HTML renderizando la template.

## `/api/usuarios/` → `usuarios.api_urls`

| Endpoint | Método | Función | Rol requerido |
|---|---|---|---|
| `api/usuarios/` | GET | Listar usuarios (Keycloak) | ADMINISTRADOR |
| `api/usuarios/crear/` | POST | Crear usuario en Keycloak | ADMINISTRADOR |
| `api/usuarios/<user_id>/detalle/` | GET | Detalle de usuario | ADMINISTRADOR |
| `api/usuarios/<user_id>/editar/` | POST | Editar usuario en Keycloak | ADMINISTRADOR |
| `api/usuarios/<user_id>/baja/` | POST | Deshabilitar usuario | ADMINISTRADOR |

**Crear usuario (POST):**
```json
{
  "username": "string",
  "email": "string",
  "password": "string"
}
```
Respuesta 201: `{ "message": "...", "usuario": { "id": "..." } }`
Error 400: `{ "error": "..." }`

## `/api/clientes/` → `clientes.api_urls`

| Endpoint | Método | Función | Rol requerido |
|---|---|---|---|
| `api/clientes/crear/` | POST | Registrar cliente nuevo | ADMINISTRADOR |
| `api/clientes/<id>/editar/` | POST | Editar cliente | ADMINISTRADOR |
| `api/clientes/<id>/baja/` | POST | Baja lógica (estado → INACTIVO) | ADMINISTRADOR |
| `api/clientes/<id>/seleccionar/` | POST | Seleccionar cliente activo | CUALQUIER_ROL |

**Crear cliente (POST):**
```json
{
  "nombre_razon_social": "string",
  "tipo_persona": "FISICA | JURIDICA",
  "documento": "string"
}
```
Respuesta 201: `{ "message": "...", "cliente": { "id": 1, "estado": "ACTIVO", ... } }`
Error 400: `{ "error": "Los datos del cliente no son válidos.", "detalles": {...} }`
Error 409: `{ "error": "Ya existe un cliente con ese documento." }` (documento duplicado)

## `/api/monedas/` → `monedas.urls`

| Endpoint | Método | Función | Rol requerido |
|---|---|---|---|
| `api/monedas/` | GET | Listar todas las monedas | CUALQUIER_ROL |
| `api/monedas/activas/` | GET | Listar monedas con estado ACTIVA | CUALQUIER_ROL |
| `api/monedas/crear/` | POST | Crear moneda nueva | ADMINISTRADOR |
| `api/monedas/<id>/editar/` | POST | Editar moneda | ADMINISTRADOR |
| `api/monedas/<id>/estado/` | POST | Alternar estado ACTIVA ↔ INACTIVA | ADMINISTRADOR |

**Crear moneda (POST):**
```json
{
  "codigo": "PYG",
  "nombre": "Guaraní",
  "simbolo": "₲"
}
```
Respuesta 201: `{ "message": "...", "moneda": { "id": 1, "codigo": "PYG", ... } }`
Error 400: `{ "error": "..." }`
Error 409: `{ "error": "Ya existe una moneda con ese código." }`

## `/api/metodos-pago/` → `metodos_pago.urls`

| Endpoint | Método | Función | Rol requerido |
|---|---|---|---|
| `api/metodos-pago/` | GET | Listar métodos de pago del cliente activo | CUALQUIER_ROL (filtrado por cliente en sesión) |
| `api/metodos-pago/registrar/` | POST | Registrar método nuevo | ADMINISTRADOR |
| `api/metodos-pago/consultar/` | GET | Listar métodos de pago | CUALQUIER_ROL |
| `api/metodos-pago/editar/<id>/` | POST | Editar método de pago | ADMINISTRADOR |
| `api/metodos-pago/estado/<id>/` | POST | Alternar estado ACTIVO ↔ INACTIVO | ADMINISTRADOR |

**Respuesta dual:** si `Accept: application/json` → JSON; si no → HTML (`templates/frontend/pagos.html`).

**Registrar método (POST):**
```json
{
  "cliente": 1,
  "nombre": "Efectivo",
  "tipo": "EFECTIVO"
}
```
Respuesta 201: `{ "message": "...", "metodo_pago": { ... } }`
Error 400: `{ "error": "..." }`
Error 409: `{ "error": "Ya existe un método de pago con ese nombre para este cliente." }`

## `/api/tasas/` → `tasas.urls`

| Endpoint | Método | Función | Rol requerido |
|---|---|---|---|
| `api/tasas/` | GET | Consultar tasas de referencia (proveedor externo) | CUALQUIER_ROL |
| `api/tasas/comerciales/` | POST | Crear/modificar tasa comercial (versionado) | ANALISTA_CAMBIARIO |
| `api/tasas/comerciales/historial/` | GET | Histórico de tasas comerciales | ADMINISTRADOR, ANALISTA_CAMBIARIO |
| `api/tasas/simular/` | POST | Simular conversión entre monedas | CUALQUIER_ROL |

**Consultar tasas (GET):**
Respuesta: `{ "actualizado": true|false, "fuente": "...", "moneda_base": "USD", "tasas": { ... } }`

**Simular conversión (POST):**
```json
{
  "moneda_origen": "USD",
  "moneda_destino": "PYG",
  "monto": 100
}
```
Respuesta: `{ "resultado": { "moneda_origen": "USD", "moneda_destino": "PYG", "monto": 100, "conversion": 785000, "tasa": 7850, "fuente": "..." } }`

**Tasas comerciales (POST — crear o modificar):**
```json
{
  "moneda_origen": 1,
  "moneda_destino": 2,
  "compra": 7800.00,
  "venta": 7900.00
}
```
Respuesta: `{ "message": "...", "tasa_comercial": { ... } }`

**Histórico tasas (GET):** lista todas las versiones de la tasa comercial entre las dos monedas, ordenadas por versión descendente.

## Respuestas comunes

| Código | Significado |
|---|---|
| 200 | OK (lectura) |
| 201 | Created (escritura exitosa) |
| 400 | Datos inválidos / error de validación |
| 401 | No autenticado |
| 403 | Sin permisos / rol requerido no presente |
| 409 | Conflicto (recurso duplicado) |
| 500 | Error inesperado (controlado: `{"error": "..."}`) |
