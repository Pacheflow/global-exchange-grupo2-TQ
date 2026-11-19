# Documentación de uso de IA — Sprint 5

**Integrante:** Elías Hirano

**Historias de usuario:** HU-29 — Generar factura electrónica y alcance ajustado de HU-30 — Consultar, visualizar y descargar facturas desde la web.

Las consultas están resumidas y agrupadas por tema a partir de la asistencia utilizada durante el desarrollo, la documentación y las pruebas. Este registro recoge la implementación inicial del 29/10/2026 y el ajuste de alcance del 30/10/2026.

## Consultas y decisiones

### 1. ¿Cómo se relaciona la factura con una operación de cambio completada?

**Respuesta resumida de la IA:** Separar la operación comercial de la emisión del comprobante. La factura debe vincularse con una transacción completada y reutilizar el adaptador del proveedor, evitando duplicar la integración externa.

**Aplicación:** Se incorporó el modelo `Factura` con una asociación única a la transacción y estados de emisión. Se reutilizó la integración técnica de Guillermo con Factura Segura. La anulación del comprobante se mantuvo fuera del alcance de esta entrega.

### 2. ¿En qué momento conviene preparar la factura para evitar inconsistencias?

**Respuesta resumida de la IA:** Preparar la facturación después de confirmar la transacción en la base de datos. Si la operación se revierte, no debe quedar una factura correspondiente a una operación que no se completó.

**Aplicación:** Se utilizó la preparación posterior al commit de la operación y se agregaron verificaciones de confirmación y rollback. Se contempló la recuperación de eventos pendientes para que el procesamiento no dependa únicamente de una solicitud web.

### 3. ¿Cómo evitamos generar dos facturas para la misma transacción?

**Respuesta resumida de la IA:** Combinar una relación única con controles de estado y concurrencia. Un reintento no debe generar otro comprobante cuando la factura ya fue procesada.

**Aplicación:** Se protegió la asociación entre factura y transacción y se incorporaron pruebas de unicidad y concurrencia. El procesamiento revisa el estado existente antes de continuar y conserva el vínculo con la operación original.

### 4. ¿Qué datos necesita el proveedor y por qué no alcanza con enviar cualquier JSON?

**Respuesta resumida de la IA:** JSON es el formato del intercambio, pero el proveedor exige un contrato fiscal concreto: datos del emisor y receptor, concepto, importes, timbrado, establecimiento y punto de expedición. Esos campos deben validarse con el contrato habilitado, sin inventar valores fiscales.

**Aplicación:** Se revisó `docs/HU-28_Integracion_Factura_Segura.md` y se identificó la dependencia del documento fiscal real y de la respuesta de `calcular_de`. En la revisión inicial, la falta del contrato configurado mantenía la factura pendiente e impedía contactar al proveedor para emitir.

### 5. ¿Una respuesta de generación significa que SIFEN aprobó la factura?

**Respuesta resumida de la IA:** La generación del documento y su aprobación fiscal son estados distintos. La interfaz debe reflejar el estado comprobado, sin interpretar una respuesta técnica como aprobación definitiva.

**Aplicación:** Se distinguieron los estados de emisión y los errores del proveedor. La consulta e interpretación completa de estados SIFEN quedó identificada como dependencia de cierre en esta revisión; las respuestas simuladas no se presentaron como emisión ni aprobación fiscal real.

### 6. ¿Qué ocurre si el proveedor devuelve un error o tarda demasiado?

**Respuesta resumida de la IA:** Un fallo de facturación debe conservar la operación comercial ya completada. Registrar el estado y permitir recuperar el procesamiento sin duplicar comprobantes ni revertir el cambio de divisas.

**Aplicación:** Se agregaron pruebas de timeout, errores y generación simulada mediante el adaptador existente. Los fallos del comprobante mantienen la transacción realizada y permiten distinguir una emisión pendiente de una solicitud resuelta correctamente.

### 7. ¿Cómo impedimos que una persona consulte o descargue una factura ajena?

**Respuesta resumida de la IA:** Verificar la autorización en cada consulta y descarga, utilizando la asociación activa del usuario con el cliente de la operación. Conocer un identificador no debe ser suficiente para acceder al comprobante.

**Aplicación:** Se protegieron el listado, la consulta y las descargas PDF/XML mediante los controles de asociación activa. Se incorporaron pruebas de permisos y descargas privadas; el acceso a los documentos utiliza el adaptador del proveedor.

### 8. ¿Cómo queda HU-30 con el ajuste a facturas disponibles desde la web?

**Respuesta resumida de la IA:** Si el alcance acordado es consultar, visualizar y descargar comprobantes en Mis facturas, retirar los servicios, rutas y pantallas del envío por correo y mantener las garantías de permisos y generación única.

**Aplicación:** El 30/10/2026 se aplicó la indicación de Axel, confirmada por Elías: las facturas quedan disponibles en la web, sin envío automático ni manual de correo. Se retiró la configuración de correo del flujo operativo y se conservaron las migraciones publicadas y los registros históricos para evitar eliminar datos.

**Alcance acordado:** El correo figuraba en los criterios originales de HU-30. La consulta y descarga web responden al ajuste comunicado por el equipo; el cambio debe reflejarse en Jira y no equivale a cumplir el criterio original de envío por correo.

### 9. ¿Qué verifican las pruebas de facturación?

**Respuesta resumida de la IA:** Cubrir estados, permisos, generación única, concurrencia y errores con respuestas simuladas. Comprobar también que una operación revertida no genere factura y que el alcance web funcione sin acciones de correo.

**Aplicación:** Las pruebas cubren asociación, unicidad, transacción pendiente, generación simulada, timeout, preparación posterior al commit, rollback y descargas privadas. Para el alcance ajustado se verificaron la ausencia de acciones de correo, el rechazo de sus URLs y el procesamiento sin SMTP.

**Verificación registrada:** La versión inicial pasó 43 pruebas de facturación y 566 de la suite completa. Después de retirar el flujo de correo, la revisión del 30/10/2026 pasó 38 pruebas de facturación y 561 de la suite completa. También pasaron `manage.py check`, la comprobación de migraciones pendientes y `git diff --check`. Las cantidades corresponden a esas versiones históricas del proyecto.

### 10. ¿Qué conviene explicar con comentarios y documentación dentro del código?

**Respuesta resumida de la IA:** Documentar las decisiones que no son evidentes: cuándo se prepara la factura, cómo se evitan duplicados, qué autorización exige una descarga y cómo se separan los fallos del comprobante de la operación comercial.

**Aplicación:** Se agregaron docstrings y comentarios en los componentes principales y se documentó el flujo en `docs/HU-29_HU-30_Facturacion.md`. Las pruebas permiten revisar por separado los escenarios normales, errores, permisos y concurrencia.

### 11. ¿Hasta dónde alcanza la evidencia de las pruebas simuladas?

**Respuesta resumida de la IA:** Las pruebas automáticas verifican la lógica interna, pero no sustituyen una emisión real con el contrato fiscal y las credenciales TEST habilitadas, ni la revisión de los documentos generados.

**Aplicación:** Se registraron como pendientes de aquella revisión la confirmación del contrato fiscal, la consulta de estados SIFEN, la configuración segura de credenciales TEST, la ejecución programada del procesador y la validación visual y fiscal del circuito completo. No se emitieron documentos fiscales reales en las pruebas aquí registradas; los avances posteriores deben evaluarse con su propia evidencia.
