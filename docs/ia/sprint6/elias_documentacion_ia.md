# Documentación de uso de IA — Sprint 6

**Integrante:** Elías Hirano

**Historia de usuario:** HU-18 / IS2TQ2026-22 — Consultar el histórico de tasas de cambio.

Las consultas están resumidas y agrupadas por tema a partir de la asistencia utilizada durante el desarrollo.

## Consultas y decisiones

### 1. ¿Cómo podemos reutilizar el histórico existente para HU-18?

**Respuesta resumida de la IA:** Revisar cómo se guardan las modificaciones de tasas antes de agregar otro modelo. Si cada cambio conserva su versión y fecha, esos registros pueden utilizarse para construir la evolución histórica.

**Aplicación:** Se reutilizó `TasaComercial`, que conserva compra, venta y fecha de registro de cada versión. La consulta incluye versiones anteriores y permite consultar monedas que después fueron desactivadas. No fue necesario crear tablas ni migraciones nuevas.

### 2. ¿Por qué necesitamos seleccionar un par de monedas y no solamente una moneda?

**Respuesta resumida de la IA:** Una tasa expresa la relación entre dos monedas. Para comparar valores a lo largo del tiempo debe mantenerse el mismo origen y destino, sin mezclar pares ni asumir que una tasa inversa equivale al dato registrado.

**Aplicación:** Se incorporaron los selectores de moneda de origen y destino. El gráfico y la tabla muestran únicamente el par elegido, y se rechaza seleccionar la misma moneda en ambos campos. Esto contempla la selección de moneda de Jira y el par solicitado por el plan del Sprint 6.

### 3. ¿Cómo damos acceso a visitantes sin exponer la auditoría de las tasas?

**Respuesta resumida de la IA:** Separar los datos necesarios para la consulta pública de los utilizados para administrar y auditar las modificaciones. El acceso público no debe ampliar los permisos del historial administrativo.

**Aplicación:** La nueva consulta devuelve fechas y valores de compra y venta, sin nombres de usuario ni identificadores de auditoría. Visitantes y usuarios autenticados pueden consultar el gráfico. La API administrativa mantiene sus restricciones y las nuevas rutas solo admiten GET.

### 4. ¿Cómo incluimos todo el día seleccionado sin perder registros por la hora?

**Respuesta resumida de la IA:** Interpretar las fechas en la zona horaria del proyecto. Para la fecha final, consultar hasta el inicio del día siguiente de forma exclusiva, en lugar de comparar con la medianoche del mismo día.

**Aplicación:** Desde y Hasta incluyen los días completos en `America/Asuncion`. Se permiten límites independientes y, si ambos están vacíos, se consulta todo el histórico del par. La primera visita propone los últimos 30 días como filtro editable.

### 5. ¿Qué debe ocurrir si el usuario ingresa filtros inválidos?

**Respuesta resumida de la IA:** Validar también en backend para que la consulta no dependa de las restricciones del navegador. Diferenciar errores de entrada de una consulta válida que simplemente no tiene registros.

**Aplicación:** El formulario valida monedas existentes, pares distintos y fechas válidas. Si la fecha inicial es posterior a la final, se muestra el error correspondiente. La API responde 400 ante filtros inválidos y no se genera un gráfico con esa entrada.

### 6. ¿Cómo representamos correctamente registros tomados en momentos distintos?

**Respuesta resumida de la IA:** Ubicar cada punto según su fecha real y no según su posición en una lista. Distinguir las series de compra y venta y permitir visualizar también una sola observación.

**Aplicación:** Se utilizó un gráfico SVG con eje temporal proporcional, compra con línea continua y venta con línea discontinua. Los puntos permiten consultar fecha y valor. Las líneas conectan registros disponibles; no generan cotizaciones intermedias. Se conserva un orden por fecha y clave primaria para registros simultáneos.

### 7. ¿Cómo conservamos los valores exactos y evitamos que la paginación cambie el gráfico?

**Respuesta resumida de la IA:** Mantener la precisión decimal de las tasas y separar la paginación de la tabla del conjunto de datos representado. Los filtros deben conservarse al cambiar de página.

**Aplicación:** La API serializa los importes como cadenas decimales y la tabla permite consultar sus valores. La tabla muestra 25 registros por página, mientras el gráfico conserva toda la serie del período seleccionado. La paginación mantiene el par y las fechas elegidos.

### 8. ¿Qué mostramos cuando no hay registros para el período consultado?

**Respuesta resumida de la IA:** Informar que no hay información disponible y permitir cambiar los filtros. No completar fechas con valores ficticios ni presentar la ausencia de registros como un error de servidor.

**Aplicación:** Se muestra un mensaje para el par y período seleccionados y se omite el gráfico. Elías verificó este caso consultando del 01/10/2026 al 31/10/2026. También comparó el gráfico y la tabla con los tres registros disponibles del 14/09/2026.

### 9. ¿Qué pruebas permiten comprobar el histórico sin afectar los datos de trabajo?

**Respuesta resumida de la IA:** Utilizar una base de pruebas aislada y cubrir filtros, permisos, límites de fechas, precisión, orden temporal, ausencia de datos y paginación. Complementar las pruebas automáticas con la revisión de la pantalla.

**Aplicación:** Se agregaron 18 pruebas de la HU-18. La suite completa pasó con 705 pruebas en Docker, utilizando la imagen del proyecto y PostgreSQL 17. Se revisó la presentación en escritorio y móvil y se ajustaron contraste y espacio bajo la navegación. La aceptación del equipo y la validación productiva permanecen pendientes.
