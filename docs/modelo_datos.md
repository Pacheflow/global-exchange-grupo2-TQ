# Modelo de Datos — Global Exchange

> Estado real verificado del código, rama `frontend-integration`, HEAD `590f131`.

## Modelos por app

### `usuarios`

**No tiene modelos.** La identidad vive íntegramente en Keycloak. Los usuarios se referencian por `keycloak_user_id` (texto) en otras apps. No existe `AUTH_USER_MODEL` personalizado.

### `clientes`

#### `CategoriaCliente`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `nombre` | `CharField(max_length=50)` | `unique=True` |
| `descripcion` | `TextField` | `blank=True` |

#### `Cliente`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `nombre_razon_social` | `CharField(max_length=150)` | — |
| `tipo_persona` | `CharField(max_length=10)` | choices: `FISICA`, `JURIDICA` |
| `documento` | `CharField(max_length=30)` | `unique=True` |
| `estado` | `CharField(max_length=10)` | choices: `ACTIVO` (default), `INACTIVO` |
| `categoria` | `ForeignKey(CategoriaCliente)` | `on_delete=PROTECT`, `null=True`, `blank=True` |
| `fecha_registro` | `DateTimeField` | `auto_now_add=True` |

Métodos de negocio: `activar()` → estado ACTIVO; `dar_de_baja()` → estado INACTIVO (baja lógica, sin eliminación física).

#### `UsuarioCliente`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `cliente` | `ForeignKey(Cliente)` | `on_delete=CASCADE` |
| `keycloak_user_id` | `CharField(max_length=64)` | — |
| `username` | `CharField(max_length=150)` | — |
| `rol_en_cliente` | `CharField(max_length=30)` | choices: `LECTOR`/`OPERADOR`/`ADMINISTRADOR_CLIENTE` |
| `activo` | `BooleanField` | default `True` |
| | | `unique_together=(cliente, keycloak_user_id)` |

### `monedas`

#### `Moneda`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `codigo` | `CharField(max_length=10)` | `unique=True`, se guarda en mayúsculas |
| `nombre` | `CharField(max_length=50)` | — |
| `simbolo` | `CharField(max_length=5, blank=True)` | — |
| `estado` | `CharField(max_length=10)` | choices: `ACTIVA`/`INACTIVA` |

### `metodos_pago`

#### `MetodoPago`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `cliente` | `ForeignKey(Cliente)` | `on_delete=CASCADE` |
| `nombre` | `CharField(max_length=50)` | `unique_together=(cliente, nombre)` (validado en clean) |
| `tipo` | `CharField(max_length=20)` | choices: `EFECTIVO`/`TARJETA`/`TRANSFERENCIA`/`OTRO` |
| `estado` | `CharField(max_length=10)` | choices: `ACTIVO`/`INACTIVO` |

### `tasas`

#### `ConsultaProveedorTasas`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `fuente` | `CharField(max_length=100)` | — |
| `moneda_base` | `ForeignKey(Moneda)` | `on_delete=CASCADE` |
| `fecha_hora_fuente` | `DateTimeField` | — |
| `respuesta` | `JSONField` | respuesta original del proveedor |

#### `TasaReferencia`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `moneda_base` | `ForeignKey(Moneda)` | `on_delete=CASCADE`, related_name `tasas_referencia_base` |
| `moneda_cotizada` | `ForeignKey(Moneda)` | `on_delete=CASCADE`, related_name `tasas_referencia_cotizada` |
| `valor` | `DecimalField(max_digits=24, decimal_places=10)` | `positive=True` |
| `fuente` | `CharField(max_length=100)` | — |
| `fecha_hora` | `DateTimeField` | — |
| `fecha_consulta` | `DateTimeField` | `auto_now_add=True` |
| | | `unique_together=(moneda_base, moneda_cotizada)` (validado en clean) |

#### `TasaComercial`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `moneda_origen` | `ForeignKey(Moneda)` | `on_delete=CASCADE`, related_name `tasas_comerciales_origen` |
| `moneda_destino` | `ForeignKey(Moneda)` | `on_delete=CASCADE`, related_name `tasas_comerciales_destino` |
| `compra` | `DecimalField(max_digits=18, decimal_places=6)` | `positive=True` |
| `venta` | `DecimalField(max_digits=18, decimal_places=6)` | `positive=True` |
| `vigente` | `BooleanField` | default `True` |
| `fecha_creacion` | `DateTimeField` | `auto_now_add=True` |
| `version` | `IntegerField` | default `1`, `positive=True` |
| `usuario_id` | `CharField(max_length=64)` | — |
| `usuario_username` | `CharField(max_length=150)` | — |
| | | `unique_together=(moneda_origen, moneda_destino, version)` (validado en clean) |

**Patrón de versionado:** al modificar un registro vigente se desactiva el anterior (`vigente=False`) y se crea uno nuevo con `version=version_actual + 1` dentro de `transaction.atomic` + `select_for_update`. Las monedas de origen/destino deben ser distintas; compra y venta deben ser positivos; `version >= 1`.

## Relaciones entre apps

- `Cliente` → `CategoriaCliente` (FK, PROTECT) — no se puede borrar una categoría con clientes asignados.
- `UsuarioCliente` → `Cliente` (FK, CASCADE) — borrar un cliente elimina sus asociaciones.
- `MetodoPago` → `Cliente` (FK, CASCADE) — borrar un cliente elimina sus métodos de pago.
- `TasaReferencia` y `TasaComercial` → `Moneda` (FK, CASCADE) — borrar una moneda elimina sus tasas.
- `ConsultaProveedorTasas` → `Moneda` (FK, CASCADE).

## Reglas de validación en `clean()`

- `MetodoPago.clean()`: `unique_together` por `(cliente, nombre)`.
- `TasaReferencia.clean()`: `unique_together` por `(moneda_base, moneda_cotizada)` y monedas distintas.
- `TasaComercial.clean()`: `unique_together` por `(moneda_origen, moneda_destino, version)`, monedas distintas y valores positivos.
