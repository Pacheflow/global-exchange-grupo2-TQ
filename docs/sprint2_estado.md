# Sprint 2 — Estado Final

> Rama `frontend-integration`, HEAD `590f131`. Estado real verificado por código y pruebas.

## Resumen

El Sprint 2 está **funcionalmente completo**. Implementa tasas de referencia, tasas comerciales, simulador, monedas y métodos de pago, integrados con datos reales persistidos en backend.

## HU implementadas

| HU | Funcionalidad | Estado real |
|---|---|---|
| HU-17 | Tasas de referencia | Implementado: `ProveedorTasasHTTP` (configurable por entorno), `consultar_tasas_referencia()`, API `GET /api/tasas/`, template `frontend/tasas.html` |
| HU-19 | Simulador | Implementado: `simular_conversion()` con conversiones directas, inversas y vía moneda base; API `POST /api/tasas/simular/`, template `frontend/simulador.html` |
| HU-21 | Tasas comerciales | Implementado: versionado (`TasaComercial` con `transaction.atomic` + `select_for_update`), histórico, API `POST /api/tasas/comerciales/` + `GET .../historial/`, template `frontend/tasas_comerciales.html` |
| HU-36 | Monedas | Implementado: CRUD completo, normalización de código, estados ACTIVA/INACTIVA, API `GET/POST /api/monedas/...`, template `frontend/monedas.html` |
| HU-37 | Métodos de pago | Implementado: CRUD, unicidad por cliente, patrón dual HTML/JSON, API `GET/POST /api/metodos-pago/...`, template `frontend/pagos.html` |

## Integración backend → frontend

Las pantallas del panel (`templates/frontend/`) consultan y modifican datos reales vía `static/js/frontend-api.js`:

| Pantalla | Namespace `data-ge-api` | Endpoints consumidos |
|---|---|---|
| Monedas | `currencies` | `monedas:*` |
| Tasas comerciales | `rates` | `tasas:*` |
| Métodos de pago | `payments` | `metodos_pago:*` |
| Tasas de referencia | `reference-rates` | `tasas:consultar` |
| Simulador | `simulator` | `monedas:listar_monedas_activas`, `tasas:simular_conversion` |
| Usuarios | `usuarios-page` | `usuarios_api:*` |
| Clientes | `clientes-page` | `clientes_api:*` |

Las URLs de API se inyectan desde templates Django (`{% url '...' %}`); no están hardcodeadas en JavaScript.

## Servicio de tasas (proveedor externo)

- **Proveedor:** ExchangeRate-API (open.er-api.com), configurable vía `TASAS_PROVIDER_URL`.
- **Validación:** respuesta JSON, `result` success, presencia de todas las monedas, tasas numéricas positivas finitas, timestamp.
- **Estados de respuesta:** `actualizado` (último < `TASAS_VALIDITY_SECONDS`, default 86400 s = 24 h), `desactualizado`, `indisponible`, `vacio`.
- **Persistencia:** `TasaReferencia` se guarda en DB; `TasaComercial` usa versionado.

## Arquitectura de presentación del panel

- **Shell:** `templates/frontend/base.html` → CSS (Material + `frontend.css`), JS (`frontend.js`, `app.js`, etc.), blocks `sidebar`, `content`, `extra_js`.
- **Sidebar:** partials con 14 iconos SVG lineales compartidos con Navbar; se ocultan opciones según el rol del usuario.
- **JavaScript:** `frontend.js` (tabs, sparklines, charts SVG, búsqueda en tablas, CRUD demo visual no persistente), `frontend-api.js` (consumo de APIs), `clientes.js`, `usuarios.js`.
- **React:** `static/react/global-exchange-react.js` compilado pero **no montado** en ninguna template Django; la Landing usa server-side.

## Pruebas

- 201 tests ejecutados, 0 fallos (post-corrección 2026-09-06).
- Tests de monedas, métodos de pago, tasas y usuarios/clientes pasan.
- `manage.py check`, `makemigrations --check --dry-run`, render de 14 templates: OK.

## Archivos clave del Sprint 2

| Archivo | Función |
|---|---|
| `tasas/providers.py` | Adaptador HTTP del proveedor externo |
| `tasas/services.py` | `consultar_tasas_referencia()`, `actualizar_tasa_comercial()` |
| `tasas/simulador.py` | `simular_conversion()` |
| `metodos_pago/views.py` | Patrón dual HTML/JSON |
| `static/js/frontend-api.js` | Consumo de APIs del panel |
| `static/js/frontend.js` | Lógica de presentación del panel |
| `templates/frontend/*.html` | 14 templates del panel + partials |

## Pendientes conocidos

- La Landing pública usa datos demo hardcodeados (no backend).
- El backend `pytz` se importa en `metodos_pago/views.py` pero no está en `requirements.txt` (dependencia transitiva de Django).
- Pruebas de integración end-to-end con Keycloak/PostgreSQL reales no ejecutadas en la última sesión.
