# Pruebas — Global Exchange

> Estado verificado el 11/10/2026.
> Suite ejecutada en Docker con `python manage.py test`.

## Resumen

| Métrica | Valor |
|---|---|
| Total de tests detectados | **452** |
| Tests pasando | **452** |
| Tests fallando | **0** |
| Errores | **0** |
| Duración última ejecución | 72.980 s |

La suite completa fue ejecutada en Docker/PostgreSQL sobre el commit funcional `07ef6fd`, tras integrar HU-28, Caja/HU-40/HU-41 y navegación final de CAJERO. Se creó/eliminó la base temporal de tests; no se migró la base funcional.

## Tests coleccionados por app en el corte final

La distribución proviene de DiscoverRunner; la suite completa ejecutó los 452 casos sin fallos. No equivale a contar únicamente métodos de los archivos.

| App | Casos coleccionados |
|---|---:|
| cajas | 92 |
| clientes | 29 |
| metodos_pago | 6 |
| monedas | 7 |
| operaciones | 128 |
| pagos | 73 |
| tasas | 58 |
| usuarios | 59 |


## HU-40 y HU-41 — Saldos y movimientos de caja

Los diez escenarios nuevos de Guillermo comprueban saldo inicial, separación
por moneda, ingresos, egresos, fondos insuficientes, períodos cerrados,
permisos, trazabilidad inmutable, idempotencia automática y el flujo web.

```bash
python manage.py test cajas.test_saldos_movimientos
```

En el corte histórico de HU-40/HU-41, la validación conjunta ejecutó 82 tests correctamente; el corte final incluye 92 casos de Caja:

```bash
python manage.py test cajas.test_saldos_movimientos cajas.test_apertura cajas.tests
```

## HU-23 y HU-32/HU-24 — Venta, historial y detalle

Las pruebas incorporadas para Guillermo verifican que Venta utilice la
tasa comercial de venta y cree una transacción PENDIENTE, que solo se ofrezcan
métodos de pago activos, que el preferido inactivo no se preseleccione, que el
historial quede limitado al cliente seleccionado, que un detalle ajeno no sea
accesible, que los snapshots no se recalculen y que historial/detalle rechacen
escrituras.

```bash
python manage.py test operaciones.test_guillermo
```

El primer corte histórico ejecutó 8 tests; el archivo se amplió posteriormente para bandeja, historial y autorización de CAJERO. La regresión final está detallada al final de este documento.

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
- la transacción comercial creada quede en estado `PENDIENTE`; COMPLETADA requiere liquidación posterior;
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
normal de creación comercial deja transacciones `PENDIENTE`, y la cancelación comprueba además el estado de Pago.

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


## Evidencia final HU-28 — 11/10/2026

| Verificación | Resultado |
|---|---|
| `docker exec global-exchange-web python manage.py test --noinput` | 452 ejecutados, 452 aprobados, 0 fallos/errores; 72.980 s |
| `node --test static/js/tests/operaciones.test.cjs` (todos los Node/DOM encontrados) | 3 ejecutados, 3 aprobados, 0 fallidos |
| `node --check static/js/operaciones.js` | Correcto |
| Django check | Sin issues |
| makemigrations --check --dry-run | Sin cambios |
| git diff --check | Correcto |

Cobertura relevante: Pago/modelo/adapter offline, autorización, recuperación, reserva concurrente, cancelación vs pago, liquidación COMPRA/VENTA, rollback, movimiento concurrente/idempotente y Caja antes de Período; contrato HTTP, bandeja/historial y selector explícito. DOM verifica saldo insuficiente persistente, elegibilidad y capacidades por rol.

QA Stripe real corresponde a evidencia previa, sin nuevas llamadas externas durante esta regresión. QA visual manual final aprobado por Axel Pacheco; no es una suite automatizada de navegador. Evidencias y DoD: [HU-28](HU-28_Realizar_Pago.md).

Los resultados PUD de 02/10/2026 y los cortes focalizados anteriores se conservan como históricos; no se suman con esta ejecución final.
