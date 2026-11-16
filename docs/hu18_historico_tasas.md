# HU-18 / IS2TQ2026-22 — Histórico de tasas

La consulta está disponible en `/tasas/historico/`, desde Histórico en la navegación pública, el menú lateral y Ver histórico en Tasas. No requiere iniciar sesión. El panel del analista también enlaza a la consulta.

## Alcance y datos

- Selección explícita de moneda de origen y destino: satisface la selección de moneda de la HU y el par solicitado en el plan del Sprint 6.
- Desde y Hasta opcionales e inclusivos en `America/Asuncion`. Sin fechas se consulta todo el histórico del par. La primera visita propone un par existente y los últimos 30 días; los filtros quedan visibles y editables.
- Reutiliza las versiones persistidas de `TasaComercial`, tanto vigentes como anteriores, con orden por fecha y clave primaria para desempatar.
- Conserva la consulta de monedas que luego fueron desactivadas. No calcula tasas inversas ni obtiene datos históricos de un proveedor externo.
- Gráfico SVG con series de compra y venta, eje horizontal proporcional al tiempo, puntos de registros reales y detalles al pasar el puntero. Las líneas solo conectan observaciones; no crean registros entre ellas. Una única observación también es visible.
- Tabla de fechas y valores exactos, 25 registros por página. La paginación conserva los filtros y no reduce la serie del gráfico. En pantallas pequeñas, gráfico y tabla admiten desplazamiento horizontal dentro de sus tarjetas.
- Si no existen registros, se informa que no hay información disponible. No se muestra una curva vacía ni datos de ejemplo.

## API y permisos

`GET /api/tasas/historico/?moneda_origen_id=<id>&moneda_destino_id=<id>&desde=2026-11-01&hasta=2026-11-15`

La API devuelve el par, la zona horaria y registros con `fecha`, `compra` y `venta`. Los importes se serializan como cadenas decimales para conservar precisión. Los filtros inválidos devuelven 400 y errores por campo; una consulta válida sin registros devuelve 200 y una lista vacía. POST devuelve 405.

Es una consulta pública de solo lectura, para visitante y usuario autenticado. No expone `usuario_id`, nombres de usuario ni auditoría. La API administrativa `/api/tasas/comerciales/historial/` conserva sus permisos anteriores. La consulta pública no invoca al proveedor ni modifica tasas.

## Dependencias e integración

No depende del cálculo de ganancias, del dashboard financiero ni del reporte administrativo. Requiere que existan monedas y versiones históricas de tasas. No necesita migraciones ni dependencias adicionales de Python o JavaScript. La base de trabajo incluye `origin/develop` en `0f7b8f6`, con el reporte administrativo de transacciones y las correcciones de despliegue ya integrados.

## Validación

- 18 pruebas nuevas en `tasas.test_historico`: acceso público y autenticado, permisos administrativos conservados, filtros, límites de días, precisión, monedas inactivas, ausencia de datos, orden, paginación y coordenadas temporales.
- Suite completa: 705 pruebas correctas primero sobre PostgreSQL 18 aislado y, el 16/11/2026, otras 705 correctas en Docker con la imagen del proyecto y PostgreSQL 17 (76,226 segundos). Django creó y retiró su base de pruebas, sin modificar datos de trabajo ni producción.
- `makemigrations --check --dry-run`: sin cambios.
- Revisión con Chromium en 1440 px y 390 px: consulta, gráfico, estado vacío, sin errores JavaScript ni desbordamiento del ancho de página. Datos de prueba locales, no datos productivos.

La ejecución Docker utilizó un contenedor temporal con la imagen `global-exchange-web:latest`, el código de esta rama montado en solo lectura y PostgreSQL 17 de Compose. Se ejecutó `python manage.py test --noinput`; se conservó la aplicación activa. El integrante verificó en la vista previa los tres registros reales de septiembre y el mensaje sin información para octubre. Quedan pendientes la aceptación del equipo y la validación en producción. Publicar la rama o abrir un Pull Request no implica aceptación, despliegue productivo ni cierre en Jira.
