# Endpoints API — Global Exchange

> Contrato verificado en código el 02/10/2026. Las escrituras usan JSON y conservan protección CSRF.

La autorización utiliza un único rol efectivo con prioridad
`ADMINISTRADOR > ANALISTA_CAMBIARIO > CAJERO > USUARIO`. Tener un rol inferior
adicional no amplía los permisos del rol efectivo.

## Acceso público

| Endpoint | Método | Función |
|---|---|---|
| `/api/tasas/` | GET | Devuelve `tasas_referencia` externas y `tasas_comerciales` vigentes |
| `/api/tasas/simular/` | POST | Simulación sin persistir operaciones; requiere token CSRF |
| `/api/monedas/activas/` | GET | Catálogo activo necesario para consulta y simulación |

Estos endpoints no exponen administración. En `GET /api/tasas/`, cada elemento de `tasas_referencia` tiene tipo `REFERENCIA` y representa una cotización externa, con fuente, fecha y estado de frescura. Cada elemento de `tasas_comerciales` tiene tipo `COMERCIAL` y representa una tasa interna de compra/venta; la consulta pública incluye únicamente registros vigentes.

Una indisponibilidad total del proveedor de tasas de referencia responde `503` con un estado JSON controlado; el servicio puede devolver respaldo persistido identificado como desactualizado. Esto no convierte las tasas comerciales en tasas de referencia ni cambia su origen.

El mismo simulador atiende a visitantes y usuarios autenticados. Aplica tasas de referencia persistidas, vigentes y directamente aplicables, inversas o cruzadas mediante la moneda base configurada. Informa monto, tasa, tipo `REFERENCIA`, fecha/hora de la fuente y resultado, sin consultar tasas comerciales ni crear operaciones.

## Usuarios — ADMINISTRADOR

| Endpoint | Método | Función |
|---|---|---|
| `/api/usuarios/crear/` | POST | Crear identidad en Keycloak |
| `/api/usuarios/<user_id>/detalle/` | GET | Consultar identidad y roles |
| `/api/usuarios/<user_id>/editar/` | POST | Editar identidad y roles |
| `/api/usuarios/<user_id>/baja/` | POST | Deshabilitar identidad |

No existe un `GET /api/usuarios/` de listado. La pantalla web `/usuarios/` obtiene el listado directamente mediante el servicio de administración de Keycloak.

## Clientes

| Endpoint | Método | Rol |
|---|---|---|
| `/api/clientes/crear/` | POST | ADMINISTRADOR |
| `/api/clientes/<id>/editar/` | POST | ADMINISTRADOR |
| `/api/clientes/<id>/baja/` | POST | ADMINISTRADOR |
| `/api/clientes/<id>/seleccionar/` | POST | ADMINISTRADOR, CAJERO o USUARIO; limitado a sus asociaciones salvo ADMINISTRADOR |
| `/api/clientes/categorias/comisiones/` | POST | ADMINISTRADOR |
| `/api/clientes/<id>/metodo-pago-preferido/` | POST | ADMINISTRADOR, CAJERO o USUARIO; limitado a sus asociaciones salvo ADMINISTRADOR |

La consulta web `/clientes/consultar/` muestra todos los clientes al administrador
y solo asociaciones activas a CAJERO o USUARIO. ANALISTA_CAMBIARIO no consulta ni
selecciona clientes.

La actualización de comisiones recibe
`{"comisiones": [{"id": <categoria_id>, "porcentaje_comision": <decimal>}]}`
y responde `200` con un mensaje de confirmación. Rechaza con `400` listas,
identificadores o porcentajes inválidos, y con `404` una categoría inexistente.

La preferencia de pago recibe `{"metodo_pago_id": <id>}` y responde `200` con
el método activo persistido. Devuelve `400` para un identificador inválido o un
método inactivo, `403` si un CAJERO o USUARIO no está asociado al cliente, y
`404` si el cliente o el método no existen. La misma URL admite `GET` para
consultar la preferencia y el catálogo global activo disponible.

## Monedas

| Endpoint | Método | Rol |
|---|---|---|
| `/api/monedas/` | GET | ADMINISTRADOR |
| `/api/monedas/activas/` | GET | Público |
| `/api/monedas/crear/` | POST | ADMINISTRADOR |
| `/api/monedas/<id>/editar/` | POST | ADMINISTRADOR |
| `/api/monedas/<id>/estado/` | POST | ADMINISTRADOR |

## Tasas comerciales

| Endpoint | Método | Rol |
|---|---|---|
| `/api/tasas/comerciales/` | POST | ANALISTA_CAMBIARIO |
| `/api/tasas/comerciales/historial/` | GET | ADMINISTRADOR o ANALISTA_CAMBIARIO |
| `/api/tasas/comerciales/<id>/desactivar/` | POST | ANALISTA_CAMBIARIO |

Cada escritura crea una nueva versión y conserva el histórico. La desactivación es lógica (`vigente=false`), no elimina el registro y permite crear después una nueva versión vigente del mismo par. El administrador consulta, pero no modifica ni desactiva.

## Operaciones de cambio

| Endpoint | Método | Rol efectivo |
|---|---|---|
| `/api/operaciones/previsualizar/` | POST | CAJERO o USUARIO |
| `/api/operaciones/crear/` | POST | CAJERO o USUARIO |
| `/api/operaciones/cancelar/` | POST | CAJERO o USUARIO |
| `/api/operaciones/metodos-pago/` | GET | CAJERO o USUARIO |
| `/api/operaciones/historial/` | GET | ADMINISTRADOR, CAJERO o USUARIO |
| `/api/operaciones/<id>/detalle/` | GET | ADMINISTRADOR, CAJERO o USUARIO |

ANALISTA_CAMBIARIO no accede al módulo operativo. ADMINISTRADOR supervisa el
historial y detalle globales, pero no previsualiza, crea ni cancela operaciones.

La previsualización valida identidad, cliente asociado, monedas, monto, tasa
comercial vigente y método de pago. Calcula en backend y devuelve la versión de
tasa junto con la huella de categoría y porcentaje de comisión, sin persistir.

En `COMPRA` se usa `TasaComercial.compra`; en `VENTA`, `TasaComercial.venta`.
La confirmación vuelve a leer y bloquear la configuración vigente, compara la
huella del preview, recalcula siempre en backend y crea una transacción
`COMPLETADA`. Si cambió la versión, categoría o comisión, responde con error y no
crea registros. No existe snapshot histórico de categoría.

Cada transacción nueva conserva además una huella SHA-256 nullable destinada
exclusivamente a idempotencia; no es un snapshot de categoría ni interviene en
los cálculos.

La clave de idempotencia solo admite un reintento del mismo usuario autorizado,
cliente y payload lógico. Otro usuario, cliente, monto, tipo, par, método,
versión, categoría o comisión recibe un error genérico sin revelar la operación
original. La huella se construye desde una serialización canónica de esos datos
y se compara tanto en el reintento normal como después de una carrera de
unicidad. Una transacción histórica con huella nula nunca se presume equivalente.

El catálogo operativo devuelve únicamente métodos activos y marca el preferido
solo si continúa activo. La interfaz lo refresca mediante el endpoint dedicado;
el render server-side se conserva como fallback progresivo. El método y su
nombre quedan persistidos como referencia y snapshot, sin procesar un pago real.

Para CAJERO y USUARIO, historial y detalle exigen cliente seleccionado, validan
estado y asociación, y aíslan las transacciones por cliente. ADMINISTRADOR puede
consultarlos globalmente. El modal obtiene el detalle mediante el endpoint
dedicado; no depende del payload resumido del historial. Ambos contratos son de
solo lectura y no exponen PUT, PATCH ni DELETE.

### Cancelación HU-25

La cancelación recibe el identificador de una transacción existente. El Backend verifica que el usuario tenga acceso al cliente asociado y que la transacción continúe en estado `PENDIENTE`.

Una transacción `PENDIENTE` puede pasar a `CANCELADA` por solicitud del usuario. Al cancelar se registran el usuario, la fecha y el motivo de cancelación. La transacción no se elimina y sus montos, tasa aplicada y comisión permanecen sin modificaciones.

Si la transacción no existe, pertenece a un cliente no autorizado o ya no se encuentra `PENDIENTE`, la cancelación es rechazada y se informa el motivo.

La confirmación visual previa a la cancelación corresponde a la integración de la interfaz. El núcleo Backend expone la operación necesaria para realizarla.

> Nota de alcance: Jira HU-25 permite cancelar una transacción pendiente por solicitud del usuario. La guía de trabajo del Sprint también describe el caso `CAMBIO_COTIZACION`; para esta implementación se siguieron los criterios de aceptación vigentes de Jira proporcionados para HU-25.

El servicio registra el método de pago seleccionado como parte de la operación. El procesamiento real del pago no se implementa en este módulo.

## Métodos de pago — ADMINISTRADOR

| Endpoint | Método | Función |
|---|---|---|
| `/api/metodos-pago/` | GET | Listado y clientes disponibles |
| `/api/metodos-pago/registrar/` | GET/POST | Formulario o alta |
| `/api/metodos-pago/consultar/` | GET | Listado |
| `/api/metodos-pago/editar/<id>/` | GET/POST | Edición |
| `/api/metodos-pago/estado/<id>/` | POST | Activación/desactivación lógica |

Las vistas son duales HTML/JSON según `Accept` o `Content-Type`. “Métodos de pago” es configuración HU-37; no representa pagos ni transacciones reales.

## Respuestas de autorización

- API sin sesión cuando corresponde autenticación: `401` JSON.
- Rol no permitido: `403` JSON.
- Vista web sin sesión: redirección a login.
- Vista web con rol no permitido: `403`.

## Rutas web relacionadas

- `/clientes/`: activa como entrada histórica del módulo.
- `/clientes/seleccionar/`: alias de compatibilidad que redirige a consulta.
- `/acceso-administrador/`: diagnóstico protegido; no es navegación de negocio.
- `/metodos-pago/`: entrada web canónica del módulo de configuración.
- `/pagos/`: alias técnico conservado por compatibilidad con la pantalla integrada; la UI lo denomina “Métodos de pago”.
