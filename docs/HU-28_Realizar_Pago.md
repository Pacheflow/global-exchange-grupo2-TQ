# Documentación técnica — HU-28 Realizar Pago

**Proyecto:** Global Exchange

**Integrante:** Axel Pacheco

**Sprint:** 4

**Rama:** `feature/hu28-pago-modelo`

**Proveedor:** Stripe, exclusivamente modo TEST

**Estado:** pagos implementados y QA técnico real aprobado; integración con Caja y QA visual autenticado pendientes.

## 1. Objetivo

Registrar y procesar el pago de una operación COMPRA mediante Stripe TEST, evitando autorizaciones duplicadas y separando el resultado financiero del procesamiento operativo de la transacción.

La aprobación del pago no completa automáticamente la operación. La finalización posterior debe coordinarse con Caja/HU-41.

## 2. Alcance implementado

- App `pagos`, modelo `Pago`, migración inicial y restricciones.
- Contrato neutral `PaymentProvider` y adaptador `StripePaymentProvider`.
- Servicios `iniciar_pago`, `reintentar_pago`, `recuperar_pago` y `consultar_estado_pago`.
- Endpoints HTTP autenticados con protección CSRF.
- UI de consulta y acciones dentro del detalle de operaciones.
- Protección de cancelación según el estado del pago.
- Pruebas de modelo, adaptador offline, servicios, API y concurrencia PostgreSQL.
- Validación E2E mediante HTTP real y Stripe TEST.

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
- `Pago.APROBADO` mantiene `Transaccion.PENDIENTE`.

### VENTA

- Se crea como `Transaccion.PENDIENTE`.
- No utiliza Stripe ni crea `Pago`.
- Inicio y reintento de pago la rechazan antes de invocar al proveedor.
- Su liquidación futura depende del flujo operativo de Caja/HU-41.

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
- La autorización valida sesión, rol, cliente seleccionado y asociación activa.
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
| `APROBADO` | “Pago aprobado. La operación continúa pendiente de procesamiento.” / sin acción |
| `RECHAZADO` | “Pago rechazado” / sin acción |
| `ERROR` | “No se pudo completar el pago.” / **Reintentar pago** |
| `INDETERMINADO` | “Pago pendiente de verificación.” / **Recuperar estado** |
| Desconocido | “Estado de pago no disponible.” / sin acción |

Los botones se bloquean durante la solicitud. No existen reintentos POST automáticos.

Las respuestas se vinculan al identificador y versión del detalle visible. Una respuesta tardía no actualiza otra operación. Los errores quedan confinados al bloque Pago y conservan el detalle económico.

VENTA y el contexto supervisor quedan fuera de este flujo.

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

La evidencia valida el recorrido HTTP, servicio, adaptador, Stripe TEST y persistencia. No acredita todavía el recorrido visual autenticado completo.

## 13. Dependencias, riesgos y deuda

- Integración pendiente con Caja/HU-41.
- Finalización operativa de COMPRA pendiente.
- Liquidación de VENTA mediante movimientos de Caja pendiente.
- `SaldoInicialCaja` representa el importe de apertura; no representa saldo actual.
- Debe mantenerse la separación entre Pago y efecto operativo de Caja.
- La limitación previa de `rol_en_cliente` en cancelación permanece como deuda fuera del alcance realizado.
- QA visual autenticado completo pendiente: el cliente QA no dispone de una identidad Keycloak válida asociada para recorrer la UI.
- Las pruebas offline no sustituyen la compatibilidad real con Stripe.
- Después de modificar el adaptador, debe reiniciarse el proceso Python para evitar ejecutar código anterior.

Los datos QA históricos se conservan como evidencia. No debe reintentarse un pago indeterminado para comprobar un cambio de payload.

## 14. Commits relevantes

| Commit | Contenido |
|---|---|
| `4f897cb` | Base del modelo Pago y adaptador Stripe TEST. |
| `21653b4` | Integración de `origin/develop`. |
| `09b890f` | Orquestación y protección de cancelaciones. |
| `47cc18e` | API de pagos y validación Stripe TEST. |
| `31f89c0` | Estado y acciones de pago en operaciones. |

El alcance implementado no representa todavía el cierre integral de HU-28 con Caja.
