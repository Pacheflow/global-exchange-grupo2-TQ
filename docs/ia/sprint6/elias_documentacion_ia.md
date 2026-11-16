# Uso de IA — Sprint 6 — Elías Hirano

**Historia:** HU-18 / IS2TQ2026-22, gráfico histórico de tasas.

Se utilizó asistencia de IA para interpretar los requisitos, revisar la estructura existente y preparar cambios de código, documentación y pruebas. El integrante aportó la historia de Jira y el plan del sprint, pidió incorporar el trabajo disponible del equipo y autorizó la implementación. También verificó la vista previa con datos y sin datos; queda pendiente la aceptación del equipo.

Las siguientes consultas son síntesis de lo conversado, no transcripciones literales.

## Alcance y dependencias

**Consulta:** ¿Qué HU corresponde a mi parte y necesito esperar a otro integrante?

**Apoyo recibido:** Identificar HU-18 como la consulta de histórico gráfico. El histórico existente conserva versiones de compra y venta; permite avanzar independientemente del backend de ganancias. El plan agrega selección de par y período a los criterios de Jira.

**Aplicación:** Se reutilizó `TasaComercial` y se preparó la funcionalidad sobre la rama `develop` actualizada, que ya incluía el reporte administrativo del equipo.

## Implementación y permisos

**Consulta:** Preparar la funcionalidad cumpliendo los criterios y considerando los cambios de los demás.

**Apoyo recibido:** Separar la consulta pública de los datos administrativos, validar los filtros en backend, conservar las fechas y valores reales y distinguir ausencia de información de errores de entrada.

**Aplicación:** Se prepararon los filtros por par y fechas, una consulta pública sin auditoría interna, el gráfico de compra y venta, la tabla y su paginación. La consulta administrativa conserva sus permisos.

## Verificación

**Apoyo recibido:** Preparar y ejecutar pruebas de permisos, fechas inclusivas, precisión decimal, monedas inactivas, ausencia de datos y representación temporal; revisar la presentación en escritorio y móvil.

**Resultado observado:** 18 pruebas nuevas y 705 en la suite completa correctas sobre PostgreSQL aislado. Se revisaron las pantallas con datos de prueba y se ajustaron contraste y espacio bajo la navegación móvil. El 16/11/2026, después de que el integrante abriera Docker, se repitió la suite con la imagen del proyecto y PostgreSQL 17: 705 pruebas correctas. El integrante compartió capturas de la consulta con los tres registros de septiembre y del período de octubre sin información. Quedan pendientes la aceptación del equipo y la validación productiva.
