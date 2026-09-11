# Endpoints API — Global Exchange

> Contrato verificado en código el 11/09/2026. Las escrituras usan JSON y conservan protección CSRF.

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
| `/api/clientes/<id>/seleccionar/` | POST | Cualquier rol de negocio autenticado, limitado a sus asociaciones salvo ADMINISTRADOR |

La consulta web `/clientes/consultar/` muestra todos los clientes al administrador y sólo asociaciones activas a los demás roles.

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
