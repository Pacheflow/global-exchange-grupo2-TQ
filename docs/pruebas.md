# Pruebas — Global Exchange

> Estado verificado el 02/10/2026.
> Suite ejecutada en Docker con `python manage.py test`.

## Resumen

| Métrica | Valor |
|---|---|
| Total de tests detectados | **203** |
| Tests pasando | **203** |
| Tests fallando | **0** |
| Errores | **0** |
| Duración última ejecución | 20.981 s |

La suite completa fue ejecutada después de incorporar los cambios de
operaciones correspondientes a HU-22, HU-23, HU-25 y HU-32/HU-24.

## Detalle por app

| App | Archivo | Métodos `test_*` | Funcionalidad cubierta |
|---|---|---:|---|
| `usuarios` | `usuarios/tests.py`, `usuarios/test_production_settings.py` | 54 | Autenticación, sesión, Keycloak, prioridad multirrol, permisos, administración de usuarios y configuración productiva |
| `clientes` | `clientes/tests.py` | 29 | Modelo, clientes, asociaciones Usuario–Cliente, selección, restricción del analista y validaciones |
| `tasas` | `tasas/tests.py`, `test_reference_rates.py`, `test_simulator.py` | 36 | Proveedor y fallback, simulación, permisos, validación, versionado, histórico y baja lógica |
| `monedas` | `monedas/tests.py` | 7 | Configuración de monedas, estados y validaciones |
| `metodos_pago` | `metodos_pago/tests.py` | 6 | Configuración y administración de métodos de pago |
| `operaciones` | `operaciones/tests.py`, `operaciones/test_guillermo.py` | 71 | Previsualización, compra, venta, huellas de comisión e idempotencia, confirmación, métodos, historial, detalle y cancelación |
| **Total** | | **203** | |

## HU-23 y HU-32/HU-24 — Venta, historial y detalle

Las ocho pruebas incorporadas para Guillermo verifican que Venta utilice la
tasa comercial de venta y cree una transacción completada, que solo se ofrezcan
métodos de pago activos, que el preferido inactivo no se preseleccione, que el
historial quede limitado al cliente seleccionado, que un detalle ajeno no sea
accesible, que los snapshots no se recalculen y que historial/detalle rechacen
escrituras.

```bash
python manage.py test operaciones.test_guillermo
```

Resultado verificado: 8 tests ejecutados correctamente.

## HU-22 — Compra de divisas

La funcionalidad de compra utiliza el núcleo común de operaciones para
evitar duplicar las reglas de cálculo.

Cuando el cliente vende una moneda a Global Exchange, la operación se
considera de tipo `COMPRA` desde el punto de vista de la empresa.

En este caso se utiliza la tasa comercial de `compra` correspondiente al
par de monedas seleccionado.

Las pruebas verifican principalmente que:

- una operación `COMPRA` utilice `TasaComercial.compra`;
- la operación sea validada antes de confirmarse;
- una compra válida pueda generar una transacción;
- la transacción confirmada quede en estado `COMPLETADA`;
- los cálculos monetarios se realicen en el Backend.

La lógica de tasa, comisión y resultado no se duplica en el Frontend.

## HU-25 — Cancelar transacción

Las pruebas de HU-25 verifican la cancelación definida en Jira:

- una transacción `PENDIENTE` puede pasar a `CANCELADA`;
- la cancelación registra usuario, fecha y motivo;
- los valores históricos de la operación no se recalculan;
- una transacción inexistente es rechazada;
- un usuario sin acceso al cliente no puede cancelar la operación;
- una transacción ya cancelada no puede cancelarse nuevamente;
- la transacción cancelada permanece en el historial.

La cancelación solicitada por el usuario no depende de que cambie la cotización.
Las pruebas de HU-25 preparan explícitamente una transacción `PENDIENTE`; el flujo
normal de confirmación actual crea transacciones `COMPLETADA`.

La confirmación visual previa a cancelar corresponde a la integración de frontend.

## Pruebas del simulador

El simulador continúa comprobando:

- monto numérico;
- monto mayor que cero;
- monedas existentes;
- monedas activas;
- moneda de origen diferente de la moneda de destino;
- tasa directa;
- tasa inversa;
- tasa cruzada;
- ausencia de una tasa disponible;
- tasas desactualizadas;
- ausencia de efectos secundarios durante una simulación.

También se realizó una corrección en el campo de monto de la interfaz para
evitar el ingreso de letras.

La suite específica del simulador fue ejecutada con:

```bash
python manage.py test tasas.test_simulator
```

Resultado:

```text
Found 14 test(s).
OK
```

La suite completa de la aplicación `tasas` también fue ejecutada:

```bash
python manage.py test tasas
```

Resultado:

```text
Found 36 test(s).
OK
```

## Pruebas de operaciones

La suite de operaciones fue ejecutada de forma independiente:

```bash
python manage.py test operaciones
```

Resultado:

```text
Found 71 test(s).
OK
```

Las pruebas de operaciones cubren:

- previsualización de operaciones;
- compra;
- venta;
- selección de tasas comerciales;
- cálculo de comisión;
- confirmación;
- creación de transacciones;
- estado final `COMPLETADA` en la confirmación normal;
- rechazo cuando cambian categoría o comisión desde el preview;
- rechazo de claves idempotentes reutilizadas por otro usuario, cliente o payload;
- rechazo de categorías distintas con el mismo porcentaje y de filas históricas sin huella;
- validación de la misma huella tras una carrera de unicidad;
- idempotencia;
- historial;
- detección de cambios de cotización;
- cancelación;
- auditoría de cancelación.

## Correcciones realizadas (2026-09-06)

### Corrección 1: HTTP 409 para documento duplicado

- **Test:** `clientes.tests.ClientesFrontendApiTest.test_crear_cliente_con_documento_duplicado`
- **Problema:** devolvía 400 en vez de 409 porque Django usa `code="unique"` y la vista buscaba `code="duplicate"`.
- **Corrección:** `clientes/views.py:310` → cambiar `error.code == "duplicate"` por `error.code in ("unique", "duplicate")`.
- **Renombre:** `ClientesFiguApiTest` → `ClientesFrontendApiTest` por consistencia post-refactor figma→frontend.

### Corrección 2: Encoding Unicode en mensaje de error Keycloak

- **Test:** `usuarios.tests.UsuariosFrontendApiTest.test_crear_usuario_api_error_keycloak`
- **Problema:** `assertContains` buscaba `"Keycloak rechazó la creación."` en el body, pero `JsonResponse` serializa con `ensure_ascii=True` por defecto.
- **Corrección:** reemplazar `assertContains(response, "...")` por `self.assertEqual(response.json()["error"], "...")`.
- **Nota:** la respuesta JSON es válida; el problema estaba en la forma de comparar el texto serializado.

## Ejecución de pruebas

La suite completa puede ejecutarse desde el entorno virtual del proyecto:

```bash
python manage.py test
```

Cuando el proyecto se ejecuta completamente dentro de Docker también puede
utilizarse:

```bash
docker compose exec -T web python manage.py test
```

Para ejecutar solamente operaciones:

```bash
python manage.py test operaciones
```

Para ejecutar solamente tasas:

```bash
python manage.py test tasas
```

Para ejecutar solamente el simulador:

```bash
python manage.py test tasas.test_simulator
```

## Configuración

- `pytest.ini`: utiliza `DJANGO_SETTINGS_MODULE=config.settings`.
- El runner utilizado en la verificación actual es Django mediante `manage.py test`.
- La base de datos de pruebas se crea y destruye automáticamente durante la ejecución.
- Las pruebas que dependen de servicios externos utilizan mocks o datos controlados cuando corresponde.

## Lo que NO está cubierto completamente

- Consulta real al proveedor externo durante las pruebas automáticas.
- Pagos reales mediante plataformas externas.
- Facturación electrónica real.
- Envío real de comprobantes para todos los flujos.
- Reportes financieros avanzados.
- Control completo de cajas.
- Pruebas de rendimiento y carga.
- Backups.
- Flujos end-to-end reales de navegador para todos los roles.
- Compatibilidad completa entre navegadores.

Las operaciones de compra, venta y cancelación sí cuentan actualmente con
cobertura automatizada en `operaciones/tests.py`.

## Evidencia PUD actual

La suite y los checks fueron ejecutados el 02/10/2026.

| Verificación | Resultado |
|---|---|
| `python manage.py check` | Sin issues |
| `python manage.py makemigrations --check --dry-run` | Sin cambios pendientes |
| `python manage.py test` | 203 tests, 0 fallos, 0 errores |
| `git diff --check` | Sin errores |

La ejecución completa mostró:

```text
System check identified no issues (0 silenced).
No changes detected
Found 203 test(s).
Ran 203 tests in 20.981s
OK
```

## Documentación automática

La documentación automática del código se genera en:

```text
docs/generated/
```

Esta carpeta no se modifica manualmente. Después de actualizar los
docstrings del código se vuelve a ejecutar el generador configurado por el
proyecto para reflejar los cambios.

La generación utiliza `pdoc` según la configuración existente en el
proyecto.

## CI/CD

No hay integración continua configurada actualmente para estas
verificaciones.

Las pruebas y checks se ejecutan manualmente antes de integrar los cambios.
