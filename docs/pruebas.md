# Pruebas — Global Exchange

> Estado verificado, rama `frontend-integration`, HEAD `590f131`.
> Suite ejecutada: `docker compose exec -T web python manage.py test`.

## Resumen

| Métrica | Valor |
|---|---|
| Total de tests detectados | **201** |
| Tests pasando | **201** |
| Tests fallando | **0** (post-corrección) |
| Métodos `test_*` encontrados (grep) | ~174 |
| Duración última ejecución | 7.66 s |

**Nota:** el número de tests detectados (201) es mayor que el de métodos `test_*` (~174) porque algunos tests son subcasos ejecutados por unittest/parameterized.

## Detalle por app

| App | Archivo | Métodos `test_*` | Funcionalidad cubierta |
|---|---|---|---|
| `usuarios` | `usuarios/tests.py` | 69 | OIDC/PKCE, JWT/JWKS, roles, sesión, logout, Admin API Keycloak (mock), realm, screens frontend, API REST crear/editar/detalle/baja |
| `clientes` | `clientes/tests.py` | 60 | Modelo, CRUD con baja lógica, segmentación, asignación Usuario–Cliente, API JSON (crear, editar, baja, selección), validación de documento duplicado |
| `tasas` | `tasas/tests.py` | 12 | Permisos por rol, validación de datos, versionado/histórico de tasas comerciales |
| `monedas` | `monedas/tests.py` | 16 | CRUD, normalización de código, estados ACTIVA/INACTIVA, migración inicial |
| `metodos_pago` | `metodos_pago/tests.py` | 17 | CRUD, unicidad por cliente, patrón dual HTML/JSON, estados |
| **Total** | | **~174** | |

## Correcciones realizadas (2026-09-06)

### Corrección 1: HTTP 409 para documento duplicado

- **Test:** `clientes.tests.ClientesFrontendApiTest.test_crear_cliente_con_documento_duplicado`
- **Problema:** devolvía 400 en vez de 409 porque Django usa `code="unique"` y la vista buscaba `code="duplicate"`.
- **Corrección:** `clientes/views.py:310` → cambiar `error.code == "duplicate"` por `error.code in ("unique", "duplicate")`.
- **Renombre:** `ClientesFiguApiTest` → `ClientesFrontendApiTest` (consistencia post-refactor figma→frontend).

### Corrección 2: Encoding Unicode en mensaje de error Keycloak

- **Test:** `usuarios.tests.UsuariosFrontendApiTest.test_crear_usuario_api_error_keycloak`
- **Problema:** `assertContains` buscaba `"Keycloak rechazó la creación."` en el body, pero `JsonResponse` serializa con `ensure_ascii=True` por defecto, lo que convierte `ó` y `ó` en `\u00f3`.
- **Corrección:** reemplazar `assertContains(response, "...")` por `self.assertEqual(response.json()["error"], "...")`.
- **Nota:** la respuesta JSON es válida; solo la serialización ASCII-lizada causaba el fallo de coincidencia de cadena.

## Ejecución de pruebas

```bash
# Comando oficial (DENTRO del contenedor web):
docker compose exec -T web python manage.py test

# NO ejecutar desde Windows directamente:
# python manage.py test  ← puede apuntar a PostgreSQL local equivocado
```

## Configuración

- `pytest.ini`: `DJANGO_SETTINGS_MODULE=config.settings`, `python_files = tests.py test_*.py *_tests.py`.
- Runner: Django (`manage.py test`), no pytest por defecto.
- Base de datos de pruebas: crea/destruye temporal `test_global_exchange` automáticamente.
- Mock de Keycloak: las pruebas de usuarios mockean `admin_request` y `roles_usuario` para aislar del servicio externo.

## Lo que NO está cubierto

- Tasas de referencia en vivo (dependencia de proveedor externo)
- Operaciones de compra/venta (no implementadas)
- Pagos, facturación, comprobantes
- Historial, ganancias, reportes
- Control de cajas
- Auditoría, rendimiento, concurrencia, backups
- Pruebas de integración entre apps (end-to-end real)
- Frontend React (sin tests de frontend)
- Compatibilidad entre navegadores

## CI/CD

No hay integración continua configurada. Las pruebas se ejecutan manualmente en el contenedor Docker.
