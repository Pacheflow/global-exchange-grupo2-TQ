# Sprint 2 — Estado verificado

> Alcance confirmado: HU-17, HU-19, HU-21, HU-36 y HU-37. Revisión del 11/09/2026.

| HU | Resultado actual |
|---|---|
| HU-17 | Consulta conjunta de tasas de referencia reales y tasas comerciales vigentes, diferenciadas en el contrato y en la pantalla; el histórico comercial permanece separado |
| HU-19 | Visitante y usuario autenticado comparten el simulador basado en tasas de referencia persistidas; no requiere cliente ni persiste operaciones y conserva CSRF |
| HU-21 | Versionado, histórico y baja lógica comercial; ANALISTA crea, modifica y desactiva, mientras ADMIN sólo consulta. La baja independiente aún no registra actor y fecha propios |
| HU-36 | CRUD administrativo de monedas y catálogo activo de consulta |
| HU-37 | CRUD administrativo de métodos de pago, con navegación exclusiva para ADMINISTRADOR |

## Integración real

- `static/js/landing.js` consume `/api/tasas/`, `/api/monedas/activas/` y `/api/tasas/simular/`.
- `static/js/frontend-api.js` integra las pantallas autenticadas y consume el mismo `/api/tasas/simular/` que la landing para HU-19.
- El Conversor no integra cliente ni Compra/Venta: HU-19 termina en el resultado estimado previo a una operación.
- `static/js/ge-data.js` y `static/js/frontend.js` se conservan como prototipos futuros, pero ninguna template activa los carga.
- La landing no presenta variaciones, históricos, compra/venta ni horas inventadas cuando esos datos no forman parte de la respuesta real.

## Funciones futuras preservadas

Operaciones, transacciones, pagos reales, cajas, arqueos, transferencias, ganancias, reportes, facturación y notificaciones no se implementaron. Sus accesos están deshabilitados con estado `Pendiente`, y sus prototipos no alimentan el runtime activo.

La simulación no crea operaciones, transacciones, pagos, facturas, reservas de tasa ni modifica saldos.

Este documento registra el estado técnico del worktree; no declara cerrado el
Sprint, actualizado Jira ni creado el tag de entrega.

## Diferencia entre vacío y pendiente

Los módulos implementados informan que no existen registros cuando sus tablas están vacías. Los módulos fuera de alcance se identifican como funcionalidad pendiente y no inventan datos.
