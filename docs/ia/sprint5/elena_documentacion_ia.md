# Documentación de uso de IA — Sprint 5


**Integrante:** Elena Gisselle Ramirez Medina



## Consultas y decisiones

### 1. ¿Cómo podemos reutilizar la selección de métodos de pago existente para HU-27?

**Respuesta resumida de la IA:** Revisar el catálogo, el método preferido del cliente, la selección durante la creación y el método guardado en la transacción. Reutilizar estos componentes antes de agregar otro flujo.

**Aplicación:** Se mantuvo el catálogo global y la preferencia del cliente como selección inicial. La elección específica queda asociada a la operación mediante su referencia y una copia del nombre.

### 2. ¿Cómo diferenciamos efectivo de los métodos electrónicos sin depender de sus nombres?

**Respuesta resumida de la IA:** Incorporar una naturaleza explícita, independiente del nombre y de la habilitación administrativa. Los registros sin validar pueden permanecer como SIN_CLASIFICAR.

**Aplicación:** Se agregó ELECTRONICO, EFECTIVO y SIN_CLASIFICAR, junto con un comando de clasificación que permite revisar el plan antes de aplicarlo. Elena ejecutó la clasificación explícita. Permanecieron habilitados Efectivo, Tarjeta y Transferencia Bancaria. QR continuó deshabilitado y el registro erróneo Peso Chileno permaneció inactivo.

### 3. ¿Necesitamos implementar una integración distinta para tarjeta y transferencia?

**Respuesta resumida de la IA:** Para el alcance acordado puede conservarse una simulación común, identificándola claramente y diferenciándola del soporte real de cada modalidad.

**Decisión:** Tarjeta y Transferencia Bancaria utilizan la simulación existente de tarjeta Stripe TEST. No se implementó transferencia bancaria real ni captura de datos de tarjeta. El efectivo no debe invocar Stripe. La captura de tarjeta mediante una pantalla del proveedor se discutió como posible ampliación, pero no forma parte de esta entrega.

### 4. ¿Dónde debe poder cambiar el usuario su método para evitar pasos innecesarios?

**Respuesta resumida de la IA:** Mantener el método preferido en Nueva operación y permitir ajustar la elección en el resumen antes de confirmar, sincronizando ambos selectores.

**Decisión final de Elena:** El método se selecciona inicialmente y puede cambiarse en el resumen. Confirmar operación guarda la elección final. Después de crearla, el detalle muestra el método como información y conserva las acciones de pago correspondientes. Se retiró la edición posterior y sus botones adicionales.

**Diferencia de alcance:** Los criterios literales 1 y 6 de Jira contemplan una operación pendiente y cambio previo al pago. El recorrido aprobado permite cambiar antes de crear la operación, sin edición posterior. Esta diferencia fue identificada y aceptada por Elena; no se presenta como cumplimiento literal de ambos criterios.

### 5. ¿Cómo permitimos cambiar el método en el resumen sin aceptar condiciones económicas manipuladas?

**Respuesta resumida de la IA:** Separar la selección final de las condiciones económicas protegidas de la previsualización. Revalidar método habilitado, identidad, autorización y condiciones al confirmar.

**Aplicación:** Se adaptó el flujo de confirmación para conservar las validaciones de cotización, importes, comisión, disponibilidad e idempotencia. Cambiar el método no modifica la preferencia general del cliente.

### 6. ¿Qué debe ocurrir si deshabilitan el método o no hay opciones disponibles?

**Respuesta resumida de la IA:** La restricción debe existir en backend. Si el método ya no está disponible, rechazar con un aviso y exigir una nueva elección; si el catálogo está vacío, informar y bloquear la confirmación.

**Aplicación:** La interfaz muestra métodos activos y mensajes de ausencia de opciones. El servidor valida nuevamente la selección final, evitando confiar únicamente en el selector del navegador.

### 7. ¿Cómo simplificamos los mensajes de confirmación y los detalles?

**Respuesta resumida de la IA:** Usar mensajes breves para el usuario y traducir los códigos internos a etiquetas legibles sin modificar los estados persistidos.

**Aplicación:** El diálogo final muestra “¿Desea confirmar la operación?” con Volver y Confirmar operación. El estado electrónico sin intento se presenta como “Pago no iniciado”, sin guiones bajos ni duplicación. Se conserva el aviso de simulación en el flujo previo. Tras confirmar COMPRA o VENTA se abre su detalle.


### 8. ¿Cómo debe funcionar el efectivo en una casa de cambios presencial?

**Respuesta resumida de la IA:** El cajero registra la operación para el cliente que llega al local, revisa sus condiciones y confirma el intercambio físico simulado usando una caja abierta.

**Aplicación:** El CAJERO accede a Nueva operación en efectivo, busca un cliente activo y registra COMPRA o VENTA con un método activo de naturaleza EFECTIVO. La creación queda PENDIENTE y abre el detalle, sin generar Pago Stripe ni movimientos todavía.

### 9. ¿El cajero debe estar asociado personalmente al cliente para atenderlo?

**Respuesta resumida de la IA:** La atención presencial requiere una autorización específica del personal. Deben distinguirse el cliente titular y el actor autenticado que ejecuta la acción.

**Decisión:** El CAJERO efectivo puede crear la operación presencial sin UsuarioCliente. Se conservaron las restricciones de asociación del usuario común y la prioridad multirrol existente. La búsqueda de clientes no debe conceder permisos generales de administración.

### 10. ¿Cómo registramos el intercambio sin dejar ingresos o egresos parciales?

**Respuesta resumida de la IA:** Revalidar bajo bloqueo y guardar todos los efectos dentro de una transacción. Si falla una escritura, revertir el conjunto.

**Aplicación:** El cajero selecciona Caja/período y confirma el intercambio. Se valida habilitación, período abierto, monedas y fondos suficientes. Se guardan juntos el ingreso de moneda origen, el egreso neto de moneda destino, la evidencia y el estado COMPLETADA. Se reutilizan los cálculos y servicios de Caja existentes. COMPRA electrónica mantiene su requisito de Pago aprobado.

### 11. ¿Cómo evitamos duplicados si el cajero confirma dos veces?

**Respuesta resumida de la IA:** Reutilizar claves idempotentes, bloqueos y evidencia de liquidación. Deshabilitar botones mientras se procesa ayuda a la experiencia, pero no sustituye la protección backend.

**Aplicación:** Repetir una liquidación devuelve el resultado existente sin duplicar movimientos. Una repetición que pretende usar otro período se rechaza. LiquidacionEfectivo relaciona operación, período, cajero, fecha y ambos movimientos.

### 12. ¿Por qué una COMPRA en efectivo completada mostraba Pago no iniciado?

**Respuesta resumida de la IA:** La interfaz interpretaba la ausencia de Pago electrónico como falta de pago. El efectivo necesita una presentación basada en su propia evidencia, sin crear un Pago Stripe ficticio.

**Aplicación:** Con LiquidacionEfectivo confirmada se muestra “Aprobado”; sin liquidación se muestra “Pendiente”, tanto para COMPRA como VENTA. Se trata de etiquetas visuales: no alteran los estados financieros ni fabrican un Pago aprobado.

### 13. ¿Cuántas pruebas debemos agregar y cómo documentarlas?

**Respuesta resumida de la IA:** Revisar primero la cobertura existente, ampliar casos reutilizables y añadir únicamente pruebas que cubran comportamientos o riesgos diferentes. Agrupar variantes equivalentes cuando mejore la claridad.

**Aplicación:** Se solicitaron pruebas necesarias de permisos, métodos, confirmación, protección económica, idempotencia, concurrencia, saldo insuficiente y rollback. Se exigieron docstrings en español para cada test nuevo o modificado. No se buscó aumentar el número de pruebas como objetivo.
