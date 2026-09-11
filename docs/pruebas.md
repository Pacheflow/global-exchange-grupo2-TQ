# Pruebas — Global Exchange

> Estado verificado el 11/09/2026, rama
> `fix/keycloak-session-and-default-role`, HEAD `9085a47`.
> Suite ejecutada: `docker compose exec -T web python manage.py test`.

## Resumen

| Métrica | Valor |
|---|---|
| Total de tests detectados | **262** |
| Tests pasando | **262** |
| Tests fallando | **0** |
| Errores | **0** |
| Tests omitidos | **0** |
| Duración última ejecución | 14.950 s |

## Detalle por app

| App | Archivo | Métodos `test_*` | Funcionalidad cubierta |
|---|---|---|---|
| `usuarios` | `usuarios/tests.py` | 111 | OIDC/PKCE, JWT/JWKS, refresh de sesión, roles heredados, logout, Admin API Keycloak (mock), realm, navegación y API REST |
| `clientes` | `clientes/tests.py` | 60 | Modelo, CRUD con baja lógica, segmentación, asignación Usuario–Cliente, API JSON (crear, editar, baja, selección), validación de documento duplicado |
| `tasas` | `tasas/tests.py`, `test_reference_rates.py`, `test_simulator.py` | 54 | Proveedor y fallback, simulación, permisos, validación, versionado, histórico y baja lógica |
| `monedas` | `monedas/tests.py` | 17 | CRUD, normalización de código, estados ACTIVA/INACTIVA, catálogo público y migración inicial |
| `metodos_pago` | `metodos_pago/tests.py` | 20 | CRUD, unicidad por cliente, seguridad HTML/JSON y estados |
| **Total** | | **262** | |

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
- Flujos end-to-end reales de navegador para todos los roles
- Compatibilidad entre navegadores

## Evidencia PUD actual

La suite, los checks y la documentación automática se ejecutaron el 11/09/2026
en el entorno Docker oficial:

| Verificación | Resultado |
|---|---|
| `python manage.py check` | Sin issues |
| `python manage.py makemigrations --check --dry-run` | Sin cambios pendientes |
| `python manage.py test` | 262 tests, 0 fallos, 0 errores, 0 omitidos |
| `python scripts/generate_docs.py` | Documentación pdoc generada en `docs/generated/` |

La generación automática utiliza `pdoc==16.0.0`, documenta los módulos
configurados en `scripts/generate_docs.py` y redacta los valores sensibles del
entorno. No se debe activar `PDOC_DISPLAY_ENV_VARS`.

## CI/CD

No hay integración continua configurada. Las pruebas se ejecutan manualmente en el contenedor Docker.
