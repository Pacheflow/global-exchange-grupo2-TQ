# Modelo de Datos — Global Exchange

> Estado real verificado del código el 11/09/2026, rama
> `fix/keycloak-session-and-default-role`, HEAD `9085a47`.

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
| `rol_en_cliente` | `CharField(max_length=20)` | choices: `RESPONSABLE`/`OPERADOR` (default)/`CONSULTA` |
| `activo` | `BooleanField` | default `True` |
| `fecha_asignacion` | `DateTimeField` | `auto_now_add=True` |
| | | `UniqueConstraint(cliente, keycloak_user_id)`, nombre `cliente_usuario_keycloak_unico`; ordering por `username` |

### `monedas`

#### `Moneda`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `codigo` | `CharField(max_length=10)` | `unique=True`, se guarda en mayúsculas |
| `nombre` | `CharField(max_length=100)` | se guarda sin espacios exteriores |
| `simbolo` | `CharField(max_length=10)` | se guarda sin espacios exteriores |
| `estado` | `CharField(max_length=10)` | choices: `ACTIVA` (default)/`INACTIVA` |
| `fecha_registro` | `DateTimeField` | `auto_now_add=True` |
| `fecha_actualizacion` | `DateTimeField` | `auto_now=True` |
| | | ordering por `codigo` |

### `metodos_pago`

#### `MetodoPago`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `cliente` | `ForeignKey(Cliente)` | `on_delete=PROTECT`, related_name `metodos_pago` |
| `nombre` | `CharField(max_length=100)` | se guarda sin espacios exteriores |
| `tipo` | `CharField(max_length=20)` | choices: `EFECTIVO`/`TARJETA`/`TRANSFERENCIA`/`OTRO` |
| `estado` | `CharField(max_length=10)` | choices: `ACTIVO` (default)/`INACTIVO` |
| `fecha_registro` | `DateTimeField` | `auto_now_add=True` |
| `fecha_actualizacion` | `DateTimeField` | `auto_now=True` |
| | | `UniqueConstraint(cliente, nombre)`, nombre `cliente_metodo_pago_nombre_unico`; ordering por `nombre` |

### `tasas`

#### `ConsultaProveedorTasas`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `fuente` | `CharField(max_length=100)` | — |
| `moneda_base` | `ForeignKey(Moneda)` | `on_delete=PROTECT`, related_name `consultas_tasas` |
| `fecha_hora_fuente` | `DateTimeField` | — |
| `recibida_en` | `DateTimeField` | `auto_now_add=True` |
| `respuesta` | `JSONField` | respuesta original del proveedor |
| | | ordering descendente por `recibida_en` |

#### `TasaReferencia`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `moneda_base` | `ForeignKey(Moneda)` | `on_delete=PROTECT`, related_name `tasas_referencia_base` |
| `moneda_cotizada` | `ForeignKey(Moneda)` | `on_delete=PROTECT`, related_name `tasas_referencia_cotizada` |
| `valor` | `DecimalField(max_digits=24, decimal_places=10)` | mínimo `0.0000000001` |
| `fuente` | `CharField(max_length=100)` | — |
| `fecha_hora_fuente` | `DateTimeField` | — |
| `vigente_hasta` | `DateTimeField` | — |
| `actualizada_en` | `DateTimeField` | `auto_now=True` |
| `consulta` | `ForeignKey(ConsultaProveedorTasas)` | `on_delete=PROTECT`, related_name `tasas` |
| | | `UniqueConstraint(moneda_base, moneda_cotizada)`, nombre `tasa_referencia_par_unico` |
| | | `CheckConstraint` de monedas distintas y `valor > 0`; ordering por códigos del par |

#### `TasaComercial`

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `moneda_origen` | `ForeignKey(Moneda)` | `on_delete=PROTECT`, related_name `tasas_origen` |
| `moneda_destino` | `ForeignKey(Moneda)` | `on_delete=PROTECT`, related_name `tasas_destino` |
| `compra` | `DecimalField(max_digits=18, decimal_places=6)` | validado como mayor que cero en `clean()` |
| `venta` | `DecimalField(max_digits=18, decimal_places=6)` | validado como mayor que cero en `clean()` |
| `vigente` | `BooleanField` | default `True` |
| `version` | `PositiveIntegerField` | default `1` |
| `usuario_id` | `CharField(max_length=255)` | — |
| `usuario_username` | `CharField(max_length=150)` | `blank=True` |
| `fecha_registro` | `DateTimeField` | `auto_now_add=True` |
| | | `CheckConstraint` de monedas distintas, nombre `tasa_monedas_distintas` |
| | | `UniqueConstraint(moneda_origen, moneda_destino)` condicionado a `vigente=True`, nombre `una_tasa_vigente_por_par`; ordering descendente por `fecha_registro` |

**Patrón de versionado del servicio:** al modificar un registro vigente se desactiva el anterior (`vigente=False`) y se crea uno nuevo con `version=ultima_version + 1` dentro de `transaction.atomic` + `select_for_update`. Si el par no tiene tasa vigente, también se crea la siguiente versión a partir del histórico. Las monedas deben estar activas y ser distintas; compra y venta se validan como valores positivos.

## Relaciones entre apps

- `Cliente` → `CategoriaCliente` (FK, PROTECT) — no se puede borrar una categoría con clientes asignados.
- `UsuarioCliente` → `Cliente` (FK, CASCADE) — borrar un cliente elimina sus asociaciones.
- `MetodoPago` → `Cliente` (FK, PROTECT) — un método de pago impide borrar físicamente su cliente.
- `TasaReferencia` y `TasaComercial` → `Moneda` (FK, PROTECT) — una tasa impide borrar físicamente sus monedas.
- `ConsultaProveedorTasas` → `Moneda` (FK, PROTECT).
- `TasaReferencia` → `ConsultaProveedorTasas` (FK, PROTECT).

## Reglas de validación en `clean()`

- `MetodoPago` normaliza `nombre` en `save()`; la unicidad por `(cliente, nombre)` se aplica con `UniqueConstraint`.
- `TasaReferencia` aplica con constraints de base de datos la unicidad del par, las monedas distintas y `valor > 0`; además usa `MinValueValidator` para el valor.
- `TasaComercial.clean()` exige monedas activas y valores de compra/venta positivos. La base de datos exige monedas distintas y una sola tasa `vigente=True` por par.
