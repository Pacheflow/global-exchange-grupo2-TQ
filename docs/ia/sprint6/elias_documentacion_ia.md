# Documentación de uso de IA — Sprint 6

**Integrante:** Elías Hirano

**Historia de usuario:** HU-18 / IS2TQ2026-22 — Consultar el histórico de tasas de cambio.

Las consultas siguientes son síntesis de lo conversado y de la asistencia utilizada durante el desarrollo, no transcripciones literales.

## Consultas y decisiones

### 1. ¿Qué historia me corresponde y necesito esperar a otro integrante?

**Respuesta resumida de la IA:** La responsabilidad asignada es el gráfico histórico de tasas. Puede avanzar de forma independiente del cálculo de ganancias y del dashboard financiero, siempre que el histórico existente permita consultar las tasas con sus fechas.

**Aplicación:** Se relacionó HU-18 / IS2TQ2026-22 con el alcance de Elías en el plan del Sprint 6. Se comprobó que `TasaComercial` conserva versiones anteriores de compra y venta y se reutilizó esa información.

### 2. ¿Cómo incorporamos lo que ya hicieron los demás antes de trabajar en mi parte?

**Respuesta resumida de la IA:** Revisar el estado local y la rama compartida, traer las actualizaciones disponibles y trabajar en una rama propia para no modificar directamente el trabajo integrado del equipo.

**Aplicación:** La implementación se preparó sobre `develop` actualizado, que ya incluía el reporte administrativo de transacciones y las correcciones de despliegue. Se utilizó la rama `feature/hu-18-historico-tasas-elias`.

### 3. ¿Cómo cumplimos los criterios de Jira y lo que agrega el plan del sprint?

**Respuesta resumida de la IA:** Permitir seleccionar el par de monedas y el período, mostrar las tasas reales de compra y venta con sus fechas y representar su evolución. Si no hay registros, informar la ausencia de información sin completar datos inexistentes.

**Aplicación:** Se prepararon los filtros de origen, destino, Desde y Hasta, el gráfico temporal y la tabla paginada. Las fechas incluyen el día completo en la zona horaria del proyecto. Se conservaron las versiones anteriores y la consulta de monedas desactivadas. Con las fechas vacías se puede consultar todo el histórico del par.

### 4. ¿Cómo permitimos la consulta de visitantes y usuarios sin exponer información interna?

**Respuesta resumida de la IA:** Separar la consulta pública de la consulta administrativa. El histórico público debe mostrar fechas y valores de tasas, mientras la auditoría interna conserva sus permisos.

**Aplicación:** Se agregó una API pública de solo lectura y la pantalla de histórico, sin nombres de usuario ni identificadores de auditoría. El historial administrativo mantuvo sus restricciones. La consulta no modifica tasas ni solicita información histórica al proveedor externo.

### 5. ¿Qué pruebas necesitamos para comprobar la funcionalidad?

**Respuesta resumida de la IA:** Verificar permisos, filtros, límites de fechas, precisión decimal, orden temporal, versiones anteriores y ausencia de datos. También comprobar que la paginación mantenga los filtros y que un único registro pueda visualizarse.

**Aplicación:** Se prepararon y ejecutaron 18 pruebas nuevas. La suite completa pasó con 705 pruebas sobre PostgreSQL aislado. Después de que Elías abriera Docker, se repitió la suite con la imagen del proyecto y PostgreSQL 17: 705 pruebas correctas. La comprobación de migraciones no detectó cambios pendientes.

### 6. ¿Qué tengo que revisar en la pantalla del histórico?

**Respuesta resumida de la IA:** Comparar los puntos del gráfico con los valores de la tabla, consultar un período con registros y otro sin información, y comprobar que los filtros se mantengan al realizar la consulta.

**Aplicación:** Elías compartió capturas de la consulta USD/PYG con los tres registros del 14/09/2026 y del período 01/10/2026–31/10/2026 sin registros. Se comprobó el mensaje de ausencia de información. También se revisó la presentación en escritorio y móvil y se ajustaron el contraste y el espacio bajo la navegación.

### 7. ¿Cómo queda el trabajo para revisarlo con el equipo y verlo en mi carpeta habitual?

**Respuesta resumida de la IA:** Mantener los cambios en la rama de la historia, abrir un Pull Request hacia `develop` para revisión y traer esa misma rama a la copia local que se utiliza en VS Code.

**Aplicación:** Se publicó la rama y se abrió el PR #59 hacia `develop`. Después se actualizó la carpeta habitual mediante avance directo y se dejó seleccionada la rama de HU-18, sin cambios locales pendientes. La publicación no implica aceptación del equipo, despliegue productivo ni cierre de Jira.
