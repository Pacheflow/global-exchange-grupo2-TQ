# Documentación técnica — HU-28 Realizar Pago

**Proyecto:** Global Exchange

**Integrante:** Axel Pacheco

**Sprint:** 4

**Rama:** `feature/hu28-pago-modelo`

**Proveedor:** Stripe, exclusivamente modo TEST

**Estado:** cierre técnico del alcance aprobado de HU-28: Pago, Stripe TEST, liquidación con Caja y UX de Cajero implementados. Regresión completa aprobada; QA visual manual aprobado por Axel Pacheco. No implica cierre de Jira ni integración a develop.

**Corte de validación:** 11/10/2026, commit funcional `07ef6fd`.

## 1. Objetivo

Registrar y procesar el pago de una operación COMPRA mediante Stripe TEST, evitando autorizaciones duplicadas y separando el resultado financiero del procesamiento operativo de la transacción.

La aprobación del pago no completa automáticamente la operación. La finalización se realiza explícitamente mediante `liquidar_transaccion(...)`, coordinado con Caja/HU-41.

## 2. Alcance implementado

- App `pagos`, modelo `Pago`, migración inicial y restricciones.
- Contrato neutral `PaymentProvider` y adaptador `StripePaymentProvider`.
- Servicios `iniciar_pago`, `reintentar_pago`, `recuperar_pago` y `consultar_estado_pago`.
- Endpoints HTTP autenticados con protección CSRF.
- UI de consulta y acciones dentro del detalle de operaciones.
- Protección de cancelación según el estado del pago.
- Pruebas de modelo, adaptador offline, servicios, API y concurrencia PostgreSQL.
- Validación E2E mediante HTTP real y Stripe TEST.
- Coordinador interno de liquidación COMPRA/VENTA, endpoint HTTP y catálogo de períodos.
- Bandeja pendiente e historial separados para Cajero, Saldos/Movimientos y contexto reutilizable de Caja/Período.

La integración no incluye Stripe.js, campos de tarjeta, suscripciones, Billing, Connect, refunds, clientes Stripe persistentes ni facturación Stripe.

## 3. Arquitectura

```text
UI Django template + JavaScript
  → endpoint HTTP
  → pagos/services.py
  → PaymentProvider
  → StripePaymentProvider
  → Stripe TEST
  → persistencia local de Pago
```

El dominio utiliza solicitudes y resultados neutrales. El adaptador concentra la dependencia del SDK y la interpretación de respuestas Stripe.

El servicio reserva el pago dentro de una transacción local, libera los locks antes de llamar al proveedor y posteriormente persiste el resultado.

## 4. Reglas de negocio

### COMPRA

- Se crea como `Transaccion.PENDIENTE`.
- Puede iniciar un pago Stripe TEST.
- `monto_pago = transaccion.monto_origen`.
- `moneda_pago = transaccion.moneda_origen`.
- `base_importe = ORIGEN`.
- `Pago.APROBADO` mantiene `Transaccion.PENDIENTE` hasta liquidación explícita. Stripe no representa ingreso de efectivo; COMPRA registra solo EGRESO de monto/moneda destino.

### VENTA

- Se crea como `Transaccion.PENDIENTE`.
- No utiliza Stripe ni crea `Pago`.
- Inicio y reintento de pago la rechazan antes de invocar al proveedor.
- Su liquidación registra INGRESO origen y EGRESO destino en Caja y completa la operación en el mismo commit.

Importe, moneda, proveedor, instrumento TEST e idempotencia se determinan en backend. El frontend no envía esos valores.

## 5. Modelo Pago

`Pago` representa la obligación de pago asociada a una transacción.

Incluye identificación UUID, relación única con `Transaccion`, método de pago, proveedor, importe y moneda persistidos, base del importe, huella de solicitud, estado, referencia externa, fechas y trazabilidad controlada.

Las restricciones protegen la unicidad del pago y la coherencia de una aprobación. Cancelar una transacción no modifica ni elimina su `Pago`.

## 6. Estados y tratamiento

| Estado local | Uso |
|---|---|
| `EN_PROCESO` | Reserva autorizada o resultado externo todavía en proceso. |
| `APROBADO` | Resultado Stripe `succeeded`, con identidad e importe validados. |
| `RECHAZADO` | Rechazo reconocido o cancelación externa definitiva validada. |
| `ERROR` | Fallo local o externo clasificado como ausencia de ejecución. Permite reintento controlado. |
| `INDETERMINADO` | Resultado incierto, respuesta inconsistente o situación que requiere verificación. |

El adaptador conserva tratamiento conservador:

- `processing` y `requires_confirmation` → `EN_PROCESO`, bajo las validaciones del resultado.
- `requires_payment_method` sin error → `EN_PROCESO`.
- Rechazo reconocido → `RECHAZADO`.
- `requires_action` y otros resultados no resolubles → `INDETERMINADO`.
- Ningún estado no terminal se interpreta como aprobado.

Una búsqueda vacía, timeout o error de consulta no certifica ausencia de ejecución. La recuperación no convierte esa incertidumbre en `ERROR`.

## 7. Idempotencia y concurrencia

Existe un solo `Pago` por `Transaccion`.

La clave de creación Stripe permanece estable:

```text
ge:hu28:pago:<pago_id>:create:v1
```

Un inicio repetido reutiliza el pago existente. El reintento permitido conserva el mismo pago y la misma obligación económica.

La exclusión local mantiene este orden:

```text
Transaccion → Pago
```

Se utiliza `select_for_update(of=("self",))`. Las llamadas externas ocurren fuera de los locks.

Las pruebas PostgreSQL cubren reserva única y ambos órdenes entre pago y cancelación:

- Si cancelación confirma primero, el pago posterior falla porque la transacción ya no está pendiente.
- Si pago reserva primero `EN_PROCESO`, cancelación se rechaza.

La protección no depende únicamente de la retención temporal de claves Stripe. Un pago indeterminado se recupera mediante consultas, sin volver a crear el cobro.

## 8. Cancelación

| Estado Pago | Cancelación |
|---|---|
| Sin Pago | Permitida |
| `ERROR` | Permitida |
| `RECHAZADO` | Permitida |
| `EN_PROCESO` | Rechazada |
| `INDETERMINADO` | Rechazada |
| `APROBADO` | Rechazada |
| Desconocido | Rechazada conservadoramente |

La comprobación ocurre dentro del mismo bloque atómico y antes de cambiar la transacción a `CANCELADA`.

## 9. Contrato HTTP

```text
POST /api/operaciones/<id>/pago/iniciar/
GET  /api/operaciones/<id>/pago/
POST /api/operaciones/<id>/pago/reintentar/
POST /api/operaciones/<id>/pago/recuperar/
```

Los POST reciben:

```json
{}
```

La respuesta expone el resultado local mediante identificadores internos, `estado`, `codigo` y, en POST, `reutilizado`.

- GET consulta exclusivamente persistencia local.
- Reintento se permite desde `ERROR`.
- Recuperación consulta o concilia; no crea ni confirma otro cobro.
- La autorización valida sesión, rol efectivo y asociación activa. USUARIO requiere cliente seleccionado; CAJERO puede consultar Pago y liquidar sin selección de cliente. Recuperación conserva su contexto previo (ver roles finales).
- No se exponen claves ni payloads externos sensibles.

## 10. Stripe TEST: payload final

```text
amount = importe convertido a minor units
currency = moneda en minúsculas
payment_method = pm_card_visa
confirm = true
capture_method = automatic

automatic_payment_methods = {
  enabled: true,
  allow_redirects: never
}

metadata:
  pago_id
  transaccion_id
  huella_solicitud

idempotency_key = ge:hu28:pago:<pago_id>:create:v1
```

Parámetros ausentes:

```text
payment_method_types
error_on_requires_action
confirmation_method
return_url
```

El flujo excluye redirects. Utiliza Stripe SDK Python `16.0.0` y credencial TEST validada sin exponer su valor.

## 11. UI

Implementación en:

```text
templates/frontend/operaciones.html
static/js/operaciones.js
```

El bloque Pago aparece en el detalle de una COMPRA elegible. Consulta GET al abrir el detalle desde historial y después de crear la operación.

| Estado | Mensaje y acción |
|---|---|
| Sin Pago | “Pago no iniciado” / **Iniciar pago** |
| `EN_PROCESO` | “Pago en proceso” / **Recuperar estado** |
| `APROBADO` | “Pago aprobado. La operación está pendiente de liquidación.” cuando la Transacción sigue pendiente / sin acción |
| `RECHAZADO` | “Pago rechazado” / sin acción |
| `ERROR` | “No se pudo completar el pago.” / **Reintentar pago** |
| `INDETERMINADO` | “Pago pendiente de verificación.” / **Recuperar estado** |
| Desconocido | “Estado de pago no disponible.” / sin acción |

Los botones se bloquean durante la solicitud. No existen reintentos POST automáticos.

Las respuestas se vinculan al identificador y versión del detalle visible. Una respuesta tardía no actualiza otra operación. Los errores quedan confinados al bloque Pago y conservan el detalle económico.

VENTA y el contexto supervisor quedan fuera del flujo de Pago. Una Transacción completada no muestra acciones de Pago/Liquidación ni mensajes que la describan como pendiente.

## 12. Pruebas y evidencia

### Validaciones automatizadas anteriores

Los resultados aprobados durante la implementación fueron:

- **147/147 tests distintos aprobados** en la validación backend focalizada.
- **16/16 tests Stripe offline**, incluidos en esa cobertura.
- **90/90 tests relevantes aprobados** durante la integración UI.
- `node --check` correcto.
- `manage.py check` limpio.
- `makemigrations --check --dry-run` sin cambios.
- `git diff --check` correcto.

Estas cifras corresponden a validaciones anteriores; no son una nueva ejecución realizada durante la preparación documental. Las ejecuciones de distinto alcance no deben sumarse entre sí.

No se aplicaron migraciones sobre la base funcional durante el QA.

### QA E2E Stripe TEST

| Evidencia | Resultado |
|---|---|
| Transacción QA | `7` |
| Pago | `6efc584f-3441-4916-b263-f07b76e1d3c2` |
| PaymentIntent | `pi_3UPObFBQZWvj5xJC0q264mFW` |
| Stripe status | `succeeded` |
| `livemode` | `false` |
| Importe | USD 12.34 |
| Pago local | `APROBADO` |
| Transacción local | `PENDIENTE` |
| GET local | HTTP 200 |
| POST repetido | `reutilizado=true` |
| PaymentIntents asociados | 1 |
| Cobros TEST adicionales | 0 |

Esta es evidencia histórica del E2E de Pago, previa a liquidación. En lectura QA del 11/10/2026, Transacción 7 ya figura COMPLETADA, con Pago APROBADO y un movimiento de egreso. El QA visual manual final fue aprobado por Axel Pacheco; no se presenta como una automatización de navegador.

## 13. Dependencias, riesgos y deuda

Caja/HU-41 fue integrada desde `e0944c8` mediante merge `a6989e8`. La liquidación y finalización COMPRA/VENTA están implementadas.

Fuera del alcance aprobado de HU-28: arqueo, cierre de Caja, transferencias entre cajas, asignación persistente Cajero–Caja, facturación HU-29/30/31 e historial integral de Caja. No se afirma que estas funciones existan.

Deudas y límites:

- `MovimientoCaja` no tiene FK directa a Transaccion: trazabilidad por clave estable, motivo y referencia externa.
- `SaldoInicialCaja` representa apertura; saldo actual se calcula en el servicio desde apertura y movimientos.
- Traducción de algunos errores de Caja mediante mensajes exactos en `_error_liquidacion`; desconocidos → 500 genérico.
- La limitación previa de `rol_en_cliente` en cancelación permanece fuera de este cierre.
- Recuperación de Pago conserva cliente seleccionado y asociación RESPONSABLE/OPERADOR; la consulta local de CAJERO admite todos sus clientes asociados activamente. No se amplió recuperación en el cambio de bandeja.
- Exclusivamente Stripe TEST; no aprobación de uso con dinero real, carga o compatibilidad completa entre navegadores.
- Runtime QA con bind mount y `--noreload`: reiniciar `web` tras cambios Python/templates. Mantener la DB QA al reiniciar; no recrear a ciegas con configuración funcional.
- Conservar pagos inciertos históricos; recuperar evidencia antes de considerar otro cobro.

## 14. Commits relevantes

| Commit | Contenido |
|---|---|
| `4f897cb` | Base del modelo Pago y adaptador Stripe TEST. |
| `21653b4` | Integración de `origin/develop`. |
| `09b890f` | Orquestación y protección de cancelaciones. |
| `47cc18e` | API de pagos y validación Stripe TEST. |
| `31f89c0` | Estado y acciones de pago en operaciones. |

El cierre técnico cubre Pago y liquidación con Caja según las decisiones aprobadas. No se modificó Jira ni se mergeó a develop.


## 15. Liquidación con Caja: contrato final

`liquidar_transaccion(*, transaccion_id, periodo_id, usuario_id, username="", roles, cliente_seleccionado_id)` controla toda la unidad atómica. La view no añade un atomic exterior ni invoca Stripe.

| Operación | Precondición | Movimientos | Finalización |
|---|---|---|---|
| COMPRA | PENDIENTE y Pago APROBADO coherente con la obligación | EGRESO `monto_destino / moneda_destino` | COMPLETADA después del movimiento |
| VENTA | PENDIENTE; no requiere ni crea Pago | INGRESO `monto_origen / moneda_origen`, EGRESO `monto_destino / moneda_destino` | COMPLETADA junto con ambos movimientos |

Sin período abierto, moneda configurada o fondos suficientes, no hay efectos parciales. COMPRA conserva Pago APROBADO y Transaccion PENDIENTE; no se repite Stripe. En VENTA el egreso fallido revierte también el ingreso.

Orden de locks: `Transaccion → Pago (COMPRA) → Caja → PeriodoCaja`, con `select_for_update(of=("self",))`. El período identifica la Caja; Caja se bloquea antes de revalidar/bloquear período. No hay IO externo durante liquidación.

Claves independientes de clic, intento y período:

```text
ge:hu28:transaccion:<id>:caja:ingreso-origen:v1
ge:hu28:transaccion:<id>:caja:egreso-destino:v1
```

COMPRA usa solo egreso. Movimiento automático idéntico se reutiliza; payload conflictivo se rechaza. Transacción ya COMPLETADA retorna `repetida=true` sin aplicar otro movimiento.

### API operativa

- `GET /api/operaciones/<id>/periodos-liquidacion/`: solo CAJERO efectivo asociado; COMPRA pendiente con Pago aprobado o VENTA pendiente. Lista períodos ABIERTO de Caja HABILITADA; sin locks, saldos ni reserva de fondos.
- `POST /api/operaciones/<id>/liquidar/`: solo CAJERO; JSON exacto `{"periodo_id": 123}`. Rechaza campos extra, valores booleanos, no enteros o no positivos.
- Éxito: `{"transaccion_id": 7, "estado": "COMPLETADA", "repetida": false}`.
- Entrada/contexto/negocio conocido → 400; inexistente/no autorizado indistinguibles → 404; conflicto de idempotencia → 409; error inesperado o ValidationError desconocido → 500 genérico.
- CSRF normal y sesión OIDC. No se aceptan importes, monedas, Pago, Caja ni información Stripe desde UI.

## 16. Roles y UX final

| Capacidad | USUARIO | CAJERO | ADMINISTRADOR |
|---|---|---|---|
| Crear/previsualizar COMPRA/VENTA | Sí | No | No |
| Iniciar/reintentar Pago | Sí | No | No |
| Consultar Pago | Sí, cliente seleccionado | Sí, asociación activa sin selected_client | No endpoint operativo; supervisión de operaciones |
| Recuperar Pago | Sí, contexto previo | Sí, contexto previo | No |
| Liquidar | No | Sí, asociación activa sin selected_client | No |
| Abrir Caja/movimiento manual | No | Sí | No |
| Consultar saldos/movimientos | No | Sí | Sí, supervisión |

Rol efectivo: ADMINISTRADOR > ANALISTA_CAMBIARIO > CAJERO > USUARIO. Un rol inferior adicional no concede capacidad comercial/operativa.

- `/operaciones/`: CAJERO ve solo PENDIENTE de todos sus clientes asociados activamente; COMPRA liquidable solo con Pago APROBADO, VENTA pendiente liquidable. Sin Nueva operación.
- `/operaciones/historial/`: CAJERO ve COMPLETADA/CANCELADA, sin acciones; usa API de historial con `?vista=historial`. USUARIO/ADMIN mantienen su historial anterior.
- `/panel/`: selección explícita por `periodo_id` de URL actual; sin parámetro, selector vacío y sin saldos anteriores. No selección activa en sesión.
- `/cajas/saldos/` y `/cajas/movimientos/`: selector explícito; navegación cruzada conserva `periodo_id`. Ruta `/cajas/periodos/<id>/saldo/` sigue disponible.
- Sidebar: una sección activa, sin Transferencias/Arqueo; `up-nav="false"` limita el marcado automático conflictivo de Unpoly al sidebar.
- `caja_contexto.html` concentra título, descripción, badges y responsable/apertura; CSS mínimo responsive. Nuevo movimiento conserva acción primaria localizada y Consultar saldo secundaria.
- Liquidación bloquea envíos por transaccion_id y protege respuestas tardías. Solo interpreta éxito con ID correcto, COMPLETADA y repetida booleano.
- Error SALDO_INSUFICIENTE visible en contenedor independiente `role="alert"`; persiste durante refresh. Ante red incierta se consulta detalle antes de considerar otro envío; no POST automático.

## 17. Evidencia final y DoD técnico

11/10/2026, commit funcional `07ef6fd`:

- Suite completa Docker/PostgreSQL: 452 encontrados y ejecutados; 452 aprobados; 0 fallos/errores (72.980 s).
- Todos los Node/DOM encontrados: 3 ejecutados y aprobados; 0 fallidos.
- `node --check static/js/operaciones.js`, Django check y diff check limpios; sin migraciones pendientes.
- Django creó/eliminó su base de tests; no migraciones en base funcional. QA existente separada.
- QA visual manual aprobado por Axel Pacheco (evidencia de revisión humana, no captura/automatización nueva).
- Lectura QA: Transacciones 7/8 COMPRA COMPLETADA con Pago APROBADO y un egreso cada una; 9 VENTA COMPLETADA con dos movimientos; 10 VENTA PENDIENTE con cero movimientos.

| Requisito | Estado | Evidencia | Observación |
|---|---|---|---|
| Pago único y cinco estados | VALIDADO | pagos/models.py, pagos/tests.py | OneToOne y constraints |
| Economía derivada del backend | VALIDADO | pagos/services.py | Snapshots origen |
| Proveedor neutral y Stripe TEST | VALIDADO | pagos/providers.py, stripe_provider.py | SDK 16.0.0; secretos por entorno |
| Idempotencia, reintento y recuperación | VALIDADO | pagos/test_services.py, test_stripe_provider.py | Incertidumbre no habilita nuevo cobro |
| Cancelación protegida | VALIDADO | operaciones/services.py y tests | Transaccion antes de Pago |
| E2E Stripe TEST e idempotencia real | APROBADO | Evidencia histórica sección 12 | Un PaymentIntent; livemode=false |
| Sin llamada externa bajo locks | VALIDADO | pagos/services.py | Reserva durable antes de proveedor |
| COMPRA: egreso destino y finalización | VALIDADO | operaciones/tests.py: test_compra_aprobada_registra_solo_egreso_destino | Cobro digital no es ingreso de Caja |
| VENTA: dos movimientos atómicos | VALIDADO | operaciones/tests.py | Rollback ante egreso insuficiente |
| Locks y concurrencia de Caja | VALIDADO | cajas/test_saldos_movimientos.py | Dos egresos, misma clave y orden real |
| Liquidación concurrente/idempotente | VALIDADO | operaciones/tests.py | COMPRA/VENTA sin duplicación |
| API Pago, catálogo y liquidación | VALIDADO | pagos/test_views.py, operaciones/tests.py | Permisos, CSRF y respuestas controladas |
| Separación de roles | VALIDADO | Tests servicios, HTTP y templates | Recuperación conserva alcance anterior |
| Bandeja/historial y Caja explícita | VALIDADO | test_guillermo.py, usuarios/tests.py, cajas/tests.py | Sin selected_client para CAJERO |
| Error visible y exclusión UI | VALIDADO | static/js/tests/operaciones.test.cjs | 3 DOM reproducibles |
| UX y contexto Caja/Período | APROBADO MANUAL | Revisión de Axel Pacheco | Sin asignación permanente |
| Arqueo/cierre/transferencias/facturación | FUERA DE HU-28 | Alcance aprobado | No se documentan como implementados |
| FK movimiento y historial integral Caja | DEUDA/FUERA DE HU-28 | cajas/models.py y rutas | Trazabilidad textual existente |

### Commits posteriores al primer corte

| Commit | Contenido |
|---|---|
| a6989e8 | Merge Caja HU-40/HU-41 desde e0944c8 |
| 1b8a4d3 | Coordinador y normalización/concurrencia Caja |
| 0c6ca42 | Endpoint de liquidación |
| 9d43048 | Catálogo de períodos |
| 14b8907 | Separación comercial/liquidación por rol |
| d4626e4 | Bandeja multi-cliente y resumen Caja |
| 07ef6fd | Navegación, Saldos/Movimientos, historial y ajustes visuales finales |
