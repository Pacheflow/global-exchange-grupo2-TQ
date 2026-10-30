# Documentación de uso de IA — Sprint 5

**Proyecto:** Global Exchange  
**Sprint:** Sprint 5  
**Integrante:** Axel  
**Fecha:** Octubre de 2026  

## 1. Objetivo

Durante el Sprint 5 se utilizó asistencia de inteligencia artificial principalmente como apoyo para análisis técnico, revisión de flujos, detección de errores, propuestas de implementación, generación de casos de prueba y validación de cambios realizados en el proyecto.

El trabajo se centró principalmente en operaciones, pagos electrónicos, experiencia de usuario, métodos de pago, operaciones de caja, clientes y compatibilidad con el módulo de facturación.

---

## 2. Actividades realizadas

### 2.1. Revisión del flujo de pagos electrónicos

Se analizó el funcionamiento de los pagos electrónicos y su integración con Stripe en modo TEST.

Se revisaron los siguientes casos:

- pago aprobado;
- pago rechazado;
- pago en proceso;
- pago indeterminado;
- error sin ejecución;
- recuperación de un pago previamente aprobado;
- prevención de cobros duplicados;
- finalización automática de operaciones online.

Se verificó que una operación electrónica aprobada pueda finalizar automáticamente sin intervención manual del cajero.

También se revisó la idempotencia del flujo para evitar:

- doble cobro;
- doble finalización;
- movimientos financieros duplicados;
- reintentos incorrectos después de una aprobación.

---

## 2.2. Separación entre operaciones online y Caja física

Se trabajó sobre la separación funcional entre:

- operaciones online/electrónicas;
- operaciones presenciales en efectivo.

El flujo online utiliza los fondos internos del sistema y no debe depender de Caja física.

El flujo presencial en efectivo queda asociado al cajero y a la Caja física.

Se realizaron verificaciones para evitar que una operación electrónica aparezca como pendiente de liquidación manual por parte del cajero.

---

## 2.3. Recuperación de operaciones electrónicas

Se revisó el caso en que Stripe aprueba un pago pero la operación no puede finalizar localmente.

Para este escenario se mantuvo la evidencia del pago aprobado y se permitió recuperar la misma operación posteriormente sin realizar un nuevo cobro.

Se agregaron validaciones para garantizar que un pago aprobado no vuelva a enviarse al proveedor de pagos durante la recuperación.

---

## 2.4. Cambio de método después de un pago fallido

Se detectó que, después de ciertos fallos de pago, el usuario podía quedar sin posibilidad de seleccionar otro método.

Se trabajó sobre las reglas para permitir el cambio únicamente en estados seguros.

Se definió el siguiente comportamiento:

- `PAGO_NO_INICIADO`: puede cambiar método.
- `RECHAZADO`: puede cambiar método.
- `ERROR` sin ejecución confirmada: puede cambiar método.
- `EN_PROCESO`: no puede cambiar método.
- `INDETERMINADO`: no puede cambiar método hasta recuperar el estado.
- `APROBADO`: no puede cambiar método ni iniciar un nuevo cobro.

El objetivo principal fue evitar cobros duplicados y mantener la trazabilidad de intentos anteriores.

---

## 2.5. Clasificación de métodos de pago

Se detectó que algunos métodos quedaban registrados con:

`SIN_CLASIFICAR`

Esto impedía determinar correctamente si correspondían al flujo electrónico o al flujo en efectivo.

Se trabajó para incorporar la selección del tipo directamente desde la interfaz de administración de métodos de pago.

Tipos disponibles:

- Electrónico
- Efectivo

Internamente se mantienen los valores:

- `ELECTRONICO`
- `EFECTIVO`

`SIN_CLASIFICAR` se conserva únicamente por compatibilidad con registros anteriores.

También se agregaron validaciones del lado del servidor para evitar nuevos métodos activos sin clasificación.

---

## 2.6. Mejoras en la interfaz de Operaciones

La pantalla de operaciones fue simplificada para concentrarse principalmente en la creación de nuevas operaciones.

Se separó el historial completo en una vista independiente.

La vista principal mantiene únicamente una lista reducida de operaciones recientes y un acceso al historial completo.

También se eliminó una notificación innecesaria que aparecía al ingresar a Operaciones sin tener un cliente seleccionado.

En ese caso se utiliza un estado visual informativo, mientras que la validación de cliente continúa siendo necesaria en la sección Historial.

---

## 2.7. Historial de operaciones

Se incorporó una sección específica de Historial para consultar las operaciones realizadas.

El historial permite visualizar información como:

- identificador;
- fecha;
- tipo de operación;
- monedas;
- importes;
- estado;
- método de pago;
- detalle de la operación.

Se mantuvieron los controles de permisos y asociación de clientes existentes.

---

## 2.8. Mejoras para el rol Cajero

Se revisó el flujo presencial del cajero.

Se corrigieron casos en los que un método correctamente clasificado como `EFECTIVO` no podía utilizarse correctamente durante la previsualización.

Se definió que:

- el cajero solo utilice métodos efectivos activos;
- si existe un único método efectivo, quede seleccionado automáticamente;
- si existen varios, puedan seleccionarse normalmente;
- un error de previsualización no bloquee permanentemente el formulario;
- el usuario pueda corregir los datos y volver a intentar.

También se reemplazó la sección de operaciones pendientes por una sección informativa de:

`Últimas operaciones de caja`

Esta sección muestra únicamente movimientos recientes correspondientes a Caja física.

---

## 2.9. Unificación de notificaciones

Se revisaron mensajes duplicados que aparecían simultáneamente dentro de las vistas y como notificaciones flotantes.

Se unificó el comportamiento utilizando un único sistema de notificaciones flotantes para mensajes generales.

Se contemplaron los siguientes tipos:

- éxito;
- error;
- advertencia;
- información.

Las validaciones específicas de campos permanecen asociadas directamente a cada input.

También se agregó deduplicación para evitar mostrar varias veces la misma notificación.

---

## 2.10. Manejo de fondos insuficientes

Se mejoró el mensaje presentado cuando una operación no puede realizarse por falta de fondos en la moneda destino.

El sistema muestra un mensaje comprensible para el usuario, indicando la moneda correspondiente.

Ejemplo:

`No hay fondos suficientes en PYG para completar esta operación. Probá con otro monto o intentá nuevamente más tarde.`

La validación del backend se mantiene como fuente de verdad.

---

## 2.11. Validación de montos excesivos

Durante las pruebas manuales se detectó que un monto extremadamente grande podía producir un error interno del servidor.

Se incorporaron validaciones para evitar que datos inválidos o fuera del rango permitido lleguen a operaciones financieras posteriores.

Se contemplaron:

- monto cero;
- monto negativo;
- valor no numérico;
- precisión inválida;
- monto superior al máximo permitido;
- valores extremadamente grandes.

Los errores de entrada ahora se manejan como respuestas controladas y no como errores internos del servidor.

---

## 2.12. Compatibilidad con Stripe

Se detectó una referencia a una API interna de la biblioteca Stripe relacionada con la configuración de logging.

Se revisó la compatibilidad con la versión utilizada por el proyecto sin modificar el comportamiento de:

- PaymentIntent;
- idempotencia;
- montos;
- monedas;
- recuperación;
- estados de pago.

Los tests específicos del proveedor Stripe continuaron funcionando correctamente.

---

## 2.13. Datos fiscales del cliente

Se incorporaron mejoras para preparar los datos necesarios para facturación.

Se reutilizó el campo existente:

`correo_facturacion`

y se incorporó un campo separado para:

`DV`

El campo `documento` continúa utilizándose como documento personal o RUC según el tipo de cliente.

Para personas jurídicas se manejan de forma separada:

- RUC;
- DV.

Los nuevos datos fiscales se incorporan al snapshot de la factura para evitar que modificaciones posteriores del cliente cambien los datos históricos de un comprobante ya preparado.

---

## 2.14. Integración con facturación

Se revisó la integración con el módulo de facturación incorporado durante el sprint.

Las operaciones completadas generan registros de factura pendientes de emisión.

Se verificó la existencia de:

- listado de facturas;
- detalle de factura;
- permisos por cliente asociado;
- endpoint protegido para descarga PDF;
- preparación de datos comerciales y fiscales.

La descarga de PDF se muestra únicamente cuando la factura se encuentra generada y dispone del identificador correspondiente.

La descarga pasa por el backend de Global Exchange para mantener autenticación y permisos.

---

## 3. Pruebas realizadas

Durante el desarrollo se ejecutaron pruebas automáticas y manuales.

Entre las validaciones realizadas se incluyeron:

```bash
docker compose exec web python manage.py check
```

Pruebas específicas de módulos:

```bash
docker compose exec web python manage.py test fondos operaciones pagos
```

```bash
docker compose exec web python manage.py test facturacion
```

```bash
docker compose exec web python manage.py test clientes facturacion
```

También se ejecutó la suite completa del proyecto.

En una de las validaciones integradas finales se obtuvieron:

- 626 pruebas Django aprobadas.
- 57 pruebas frontend aprobadas.

Posteriormente, para los cambios fiscales se validaron:

- 101 pruebas de `clientes` y `facturacion` aprobadas.
- 11 pruebas frontend relacionadas con clientes aprobadas.
- `manage.py check` sin errores.
- `git diff --check` sin errores.

---

## 4. Pruebas manuales

Además de las pruebas automáticas, se realizaron pruebas manuales sobre los principales flujos.

Se verificaron casos como:

- creación de COMPRA online;
- procesamiento de pago mediante Stripe TEST;
- aprobación automática;
- movimientos en fondos online;
- finalización de la operación;
- historial de operaciones;
- fondos insuficientes;
- montos excesivos;
- operaciones presenciales en efectivo;
- comportamiento del rol cajero;
- cambio de método después de rechazo;
- navegación del usuario;
- listado de facturas;
- detalle de factura;
- clientes con información fiscal.

---

## 5. Decisiones principales

Las principales decisiones tomadas durante este trabajo fueron:

1. Separar completamente Caja física de los fondos utilizados para operaciones online.
2. Evitar intervención manual del cajero en operaciones electrónicas normales.
3. Mantener recuperación de pagos aprobados sin volver a cobrar.
4. Permitir cambio de método únicamente cuando el estado del pago sea seguro.
5. Clasificar los métodos de pago desde la interfaz.
6. Mantener `SIN_CLASIFICAR` únicamente por compatibilidad histórica.
7. Separar Operaciones e Historial.
8. Unificar las notificaciones generales mediante toast.
9. Validar montos antes de ejecutar lógica financiera.
10. Mantener la descarga de facturas detrás del backend y de los controles de permisos.
11. Mantener los datos fiscales de cada factura mediante snapshots históricos.

---

## 6. Limitaciones y pendientes

La emisión fiscal real todavía depende de configuración externa.

Actualmente quedan pendientes:

- configuración de `FACTURACION_CONTRATO`;
- credenciales TEST de Factura Segura;
- validación real con el proveedor fiscal;
- obtención de CDC real;
- validación de estados fiscales de SIFEN;
- validación de PDF/XML real generado por el proveedor.

Sin esta configuración, las facturas permanecen en estado pendiente con:

`CONTRATO_FISCAL_PENDIENTE`

El sistema conserva correctamente las operaciones y las facturas pendientes sin afectar pagos, fondos ni movimientos existentes.

---

## 7. Resultado

El uso de inteligencia artificial durante el Sprint 5 permitió apoyar el análisis y validación de los flujos implementados, detectar casos límite, organizar pruebas y revisar la integración de los diferentes módulos.

Los cambios realizados se validaron mediante pruebas automáticas y pruebas manuales antes de su integración al repositorio.