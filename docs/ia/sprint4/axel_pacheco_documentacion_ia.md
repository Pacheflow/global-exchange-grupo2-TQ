# Documentación de conversaciones con IA — Axel Pacheco — Sprint 4

**Integrante:** Axel Pacheco

Este registro corresponde a HU-28 Realizar Pago. Las preguntas y respuestas son síntesis de las conversaciones y decisiones del trabajo, no transcripciones literales. La asistencia se realizó mediante Codex; Axel Pacheco definió y autorizó los alcances de implementación.

### Pregunta 1

**Usuario:**
> ¿Cómo incorporar pagos para COMPRA sin mezclar el cobro con la finalización de la operación?

**IA:**
Se propuso separar `Pago` de `Transaccion` y utilizar un proveedor neutral. Axel Pacheco confirmó que `Pago.APROBADO` debe conservar `Transaccion.PENDIENTE`. La finalización queda pendiente de una función posterior coordinada con Caja/HU-41.

### Pregunta 2

**Usuario:**
> ¿Qué debe implementarse como base de HU-28?

**IA:**
Se incorporaron la app `pagos`, el modelo `Pago`, migración inicial, restricciones y pruebas. Las nuevas COMPRA y VENTA pasan a crearse pendientes, conservando cálculos, snapshots e idempotencia comercial. Solo COMPRA utiliza Stripe; VENTA no crea Pago.

### Pregunta 3

**Usuario:**
> ¿Cómo evitar que la lógica de dominio dependa directamente de Stripe?

**IA:**
Se utilizó el contrato `PaymentProvider`, con solicitudes y resultados neutrales, y un adaptador `StripePaymentProvider`. Stripe se limita al modo TEST. El alcance excluye Billing, Connect, suscripciones, refunds, clientes persistentes y facturación Stripe.

### Pregunta 4

**Usuario:**
> ¿Cómo garantizar que dos solicitudes no autoricen dos cobros?

**IA:**
El servicio reserva un único Pago por Transacción. Se mantiene la clave `ge:hu28:pago:<pago_id>:create:v1` y el orden de locks `Transaccion → Pago`. La llamada externa ocurre fuera de los locks. Se implementaron pruebas reales PostgreSQL con conexiones independientes para verificar exclusión y autorización única.

### Pregunta 5

**Usuario:**
> ¿Cómo tratar un resultado incierto y un fallo local después de aprobarse externamente?

**IA:**
Se implementaron inicio, reintento y recuperación. El reintento se limita a `ERROR`; la recuperación consulta por referencia o concilia mediante metadata. Una búsqueda vacía, timeout o error de consulta no demuestra ausencia de ejecución. `INDETERMINADO` se conserva hasta contar con evidencia concluyente, evitando un nuevo cobro.

### Pregunta 6

**Usuario:**
> ¿Cómo coordinar cancelación y pago sin que ambos puedan ganar simultáneamente?

**IA:**
La cancelación bloquea primero Transacción y luego Pago dentro del mismo bloque atómico. Sin Pago, `ERROR` y `RECHAZADO` permiten cancelar; `EN_PROCESO`, `INDETERMINADO`, `APROBADO` y estados desconocidos lo impiden. Se probaron ambos órdenes de la carrera. Cancelar no modifica ni elimina el Pago.

### Pregunta 7

**Usuario:**
> ¿Qué debe aceptar la API y qué información debe obtener del backend?

**IA:**
Los POST reciben `{}`. Importe, moneda, proveedor, instrumento TEST e idempotencia se determinan en servidor. Se agregaron endpoints de inicio, consulta local, reintento y recuperación, con sesión, permisos y CSRF. GET no invoca Stripe.

### Pregunta 8

**Usuario:**
> ¿Por qué las pruebas offline pasaban mientras Stripe TEST rechazaba el flujo real?

**IA:**
El QA real expuso parámetros incompatibles en la solicitud. También se detectó un proceso `web` que ejecutaba código anterior. Los logs Stripe aportados durante el diagnóstico permitieron aplicar correcciones mínimas: retirar `payment_method_types`, `error_on_requires_action` y `confirmation_method`, y configurar métodos automáticos con redirects deshabilitados. No se agregaron `return_url` ni cambios económicos o de idempotencia.

Las pruebas offline verificaban el contrato construido, pero no garantizaban aceptación por la API real. La evidencia externa corrigió las suposiciones previas.

### Pregunta 9

**Usuario:**
> ¿Cuál es el payload final y qué resultado tuvo el QA real?

**IA:**
El payload conserva importe, moneda, `pm_card_visa`, confirmación y captura automática, metadata e idempotencia. Utiliza `automatic_payment_methods={"enabled": True, "allow_redirects": "never"}`.

La Transacción 7 y el Pago `6efc584f-3441-4916-b263-f07b76e1d3c2` produjeron el PaymentIntent `pi_3UPObFBQZWvj5xJC0q264mFW`: `succeeded`, `livemode=false`, USD 12.34. Pago quedó aprobado y Transacción pendiente. GET respondió 200 y el inicio repetido reutilizó el mismo pago. Se verificó un PaymentIntent y ningún cobro TEST adicional.

### Pregunta 10

**Usuario:**
> ¿Cómo integrar la UI sin modificar el backend ya validado?

**IA:**
Se modificaron únicamente el template de operaciones y su JavaScript. Primero se incorporó consulta local; después, acciones explícitas según estado. Se protegieron doble clic y respuestas tardías, se mantuvieron errores dentro del bloque Pago y no se agregaron Stripe.js ni datos financieros al POST.

## Pruebas, Git y cierre

### Pregunta 11

**Usuario:**
> ¿Qué verificaciones respaldan la implementación?

**IA:**
Las validaciones anteriores reportaron 147/147 pruebas backend distintas aprobadas, con 16/16 Stripe offline dentro de ese conjunto. La integración UI ejecutó 90/90 pruebas relevantes, además de sintaxis JavaScript, Django check y revisión de diff. No quedaron migraciones pendientes.

Estas cifras corresponden a ejecuciones de diferente alcance y no se suman. El QA visual autenticado completo permanece pendiente.

### Pregunta 12

**Usuario:**
> ¿Qué commits permiten seguir el trabajo?

**IA:**
Los commits verificados son `4f897cb`, base de pagos; `21653b4`, integración de develop; `09b890f`, orquestación y cancelaciones; `47cc18e`, API y Stripe TEST; y `31f89c0`, UI de estado y acciones.

### Pregunta 13

**Usuario:**
> ¿Qué riesgos y dependencias siguen abiertos?

**IA:**
Quedan Caja/HU-41, finalización de COMPRA, liquidación de VENTA y QA visual autenticado. `SaldoInicialCaja` no representa saldo actual. La limitación previa de permisos en cancelación no se corrigió fuera del alcance autorizado.

Debe preservarse la separación Pago/Caja y evitar completar Transacción antes del efecto operativo. Los resultados inciertos requieren recuperación, no un nuevo intento de cobro.

### Pregunta 14

**Usuario:**
> ¿Puede considerarse cerrada completamente HU-28?

**IA:**
La evidencia respalda la implementación del pago, API, protección de cancelación, UI y QA técnico Stripe TEST. No acredita integración con Caja ni QA visual autenticado completo. La asistencia de IA y las pruebas no sustituyen la revisión humana ni permiten declarar pendientes como terminados.
