# Documentación de uso de IA – Sprint 6

**Proyecto:** Global Exchange  
**Materia:** Ingeniería de Software II  
**Sprint:** Sprint 6  
**Integrante:** Axel  
**Fecha:** Noviembre de 2026  

## 1. Objetivo del uso de IA

Durante el Sprint 6 se utilizó inteligencia artificial como apoyo para el análisis, diseño, validación y mejora de distintas funcionalidades del sistema Global Exchange.

El uso de IA estuvo enfocado principalmente en:
- analizar los requerimientos del Sprint 6;
- proponer una distribución adecuada de información en los dashboards;
- revisar criterios de métricas financieras;
- diseñar filtros y visualizaciones;
- mejorar la experiencia de usuario;
- detectar inconsistencias visuales y funcionales;
- apoyar la validación de cambios antes de integrarlos al proyecto;
- documentar decisiones tomadas durante el desarrollo.

La IA fue utilizada como herramienta de apoyo y consulta. Las decisiones finales de implementación fueron revisadas y adaptadas al funcionamiento real del sistema.

## 2. Funcionalidades trabajadas durante el Sprint 6

### Dashboard administrativo

Se desarrolló y mejoró el panel del administrador con información como:
- ganancia del período;
- volumen operado;
- cantidad de operaciones;
- cantidad de compras;
- cantidad de ventas;
- actividad reciente;
- gráficos de evolución;
- distribución por divisa;
- filtros por período;
- filtros por divisa.

También se definió que las ganancias debían mostrarse siempre en **guaraníes (PYG)**, independientemente de la divisa seleccionada para realizar el análisis.

### Reporte administrativo de transacciones

Se integró el acceso al reporte completo de transacciones desde el dashboard.

Durante las pruebas se detectó que al ingresar al reporte se marcaban simultáneamente las opciones **Operaciones** y **Transacciones** en el menú lateral.

Se analizó el problema y se corrigió el criterio utilizado para identificar la opción activa del sidebar, de modo que:
- en Operaciones se marque solamente **Operaciones**;
- en Reportes se marque solamente **Transacciones**.

### Formato de importes

Se revisó la presentación de importes porque inicialmente algunos valores aparecían con seis decimales, por ejemplo:

`51660.000000 PYG`

Se decidió utilizar un formato más adecuado para Paraguay:

`51.660 PYG`

También se mejoró la presentación de otras monedas, conservando únicamente los decimales necesarios.

Para evitar duplicación de lógica se creó un filtro reutilizable para la presentación de importes.

## 3. Análisis de métricas financieras

### Ganancia

La ganancia representa las **comisiones cobradas por operaciones completadas**.

Ejemplo:
- volumen operado: `738.000 PYG`
- comisión obtenida: `51.660 PYG`

En este caso:

`Ganancia = 51.660 PYG`

### Volumen

El volumen representa el monto total movilizado por las operaciones dentro del período seleccionado.

No debe confundirse con la ganancia.

Ejemplo:

`Volumen = 738.000 PYG`

`Ganancia = 51.660 PYG`

### Moneda de presentación

Se decidió que las métricas financieras principales del dashboard administrativo se expresen siempre en:

`PYG`

Esto permite mantener una única moneda base para el análisis del negocio.

## 4. Criterio temporal de las métricas

Durante la revisión se detectó que el módulo financiero actual utiliza la **fecha de creación de la operación** como criterio temporal.

Se analizó la posibilidad de utilizar en el futuro la fecha de finalización de la operación, debido a que una operación puede:
- crearse en un día;
- quedar pendiente;
- completarse posteriormente;
- cancelarse;
- fallar.

Sin embargo, para evitar introducir cambios adicionales al cierre del Sprint 6, se mantuvo el comportamiento actual y se dejó documentada esta diferencia para una revisión posterior.

## 5. Dashboard dinámico

Se trabajó en convertir el dashboard administrativo en un tablero más dinámico y útil para análisis.

Se definieron filtros globales por período y divisa.

### Período
- Hoy
- Esta semana
- Este mes
- Últimos 3 meses
- Últimos 6 meses
- Últimos 12 meses
- Personalizado

### Divisa
- Todas
- USD
- EUR
- BRL
- ARS
- otras monedas activas del sistema

Las monedas disponibles deben obtenerse de los datos reales del sistema y no estar escritas manualmente en el código.

## 6. Comportamiento de los filtros

Los filtros deben afectar de forma coordinada:
- ganancia;
- volumen;
- operaciones;
- compras;
- ventas;
- gráficos;
- actividad reciente.

Por ejemplo, al seleccionar:

`Período: Este mes`

`Divisa: USD`

el dashboard debe permitir conocer:
- cuánto se ganó con operaciones relacionadas con USD;
- cuánto volumen se movilizó;
- cuántas operaciones se completaron;
- cuántas fueron compras;
- cuántas fueron ventas;
- cómo evolucionaron los valores durante el período.

Aunque se filtre por USD, la ganancia continúa expresándose en PYG.

## 7. Visualización de datos

Se analizó la necesidad de evitar un dashboard demasiado estático.

Por este motivo se incorporaron o propusieron:
- gráficos de barras o líneas;
- gráficos de dona;
- tooltips;
- animaciones de entrada;
- transiciones al cambiar filtros;
- actualización dinámica de datos;
- estados vacíos cuando no existen operaciones;
- comportamiento responsive.

También se consideró que las animaciones debían ser discretas y profesionales, sin afectar la lectura de la información.

## 8. Gráficos del dashboard administrativo

### Evolución de ganancias

Permite observar el comportamiento de la ganancia a lo largo del tiempo.

Las ganancias se expresan siempre en PYG.

La granularidad puede variar de acuerdo con el período:
- días;
- semanas;
- meses.

### Distribución por divisa

Cuando se muestran todas las divisas, el gráfico puede representar la distribución de operaciones o ganancias por moneda.

Cuando se selecciona una única divisa, se consideró más útil mostrar la distribución entre:
- compras;
- ventas.

## 9. Dashboard del Analista Cambiario

También se analizó el panel correspondiente al rol **Analista Cambiario**.

Se determinó que este dashboard no debía ser una copia del dashboard administrativo.

El Analista Cambiario necesita información relacionada principalmente con:
- tasas;
- divisas;
- evolución histórica;
- variaciones;
- spread;
- comportamiento del mercado;
- operaciones por moneda.

Por esta razón se propuso reemplazar indicadores relacionados con ganancias globales por métricas más útiles para este rol.

## 10. Indicadores definidos para el Analista Cambiario

Entre los indicadores considerados se encuentran:
- USD/PYG de referencia;
- EUR/PYG de referencia;
- mayor variación del período;
- divisa más operada;
- cantidad de tasas vigentes;
- última actualización de tasas.

También se planteó una tabla de mercado con:
- divisa;
- compra;
- venta;
- spread;
- variación;
- última actualización.

## 11. Histórico de tasas

Se aprovechó la funcionalidad existente de histórico de tasas para utilizar datos reales dentro del dashboard.

Se propuso mostrar:
- evolución de compra;
- evolución de venta;
- filtros por período;
- filtros por divisa;
- tooltips;
- variaciones porcentuales;
- gráficos dinámicos.

También se decidió reemplazar textos como:

`Histórico · Próximamente`

por información real proveniente del histórico existente.

## 12. Spread

Para el dashboard del Analista Cambiario se consideró útil mostrar el spread existente entre compra y venta.

Conceptualmente:

`Spread = Venta - Compra`

Este indicador permite visualizar rápidamente la diferencia entre ambas cotizaciones.

## 13. Dashboard por roles

Durante el Sprint 6 también se analizó la conveniencia de que cada rol tenga un dashboard adaptado a sus necesidades.

### Administrador
Orientado a:
- ganancias;
- volumen;
- operaciones;
- compras;
- ventas;
- reportes;
- análisis general del negocio.

### Analista Cambiario
Orientado a:
- tasas;
- variaciones;
- monedas;
- histórico;
- spread;
- comportamiento del mercado.

### Cajero
Orientado principalmente a:
- operaciones del día;
- movimientos de caja;
- compras y ventas;
- estado de caja;
- últimas operaciones.

### Usuario
Orientado únicamente a su propia información:
- operaciones personales;
- estados;
- histórico;
- cotizaciones relevantes.

Esto permite que cada perfil visualice únicamente información relacionada con sus responsabilidades.

## 14. Problemas detectados durante las pruebas

### Librería de template no reconocida

Después de incorporar un nuevo filtro de formato, Django mostró:

`TemplateSyntaxError: 'importes' is not a registered tag library`

Se comprobó que la librería estaba correctamente implementada.

El problema se debía a que el proceso activo todavía no había descubierto el nuevo módulo.

Se solucionó reiniciando únicamente el servicio web.

Posteriormente se verificó correctamente:
- dashboard;
- reporte de transacciones;
- detalle del reporte.

### Sidebar con dos opciones activas

Al ingresar al reporte se marcaban:
- Operaciones;
- Transacciones.

Se revisó la lógica de navegación y se ajustó para que únicamente aparezca activa la opción correspondiente a la pantalla actual.

### Importes con demasiados decimales

Se detectaron valores como:

`738000.000000 PYG`

Esto se corrigió visualmente para mostrar:

`738.000 PYG`

sin modificar los valores financieros almacenados.

## 15. Validaciones realizadas

Durante el trabajo se realizaron distintas validaciones del proyecto.

Entre ellas:
- pruebas específicas del dashboard;
- pruebas financieras;
- pruebas del reporte administrativo;
- pruebas de navegación;
- pruebas de formato;
- validación de permisos;
- validación de endpoints;
- `manage.py check`;
- `git diff --check`;
- inspección manual en navegador.

También se verificó que las nuevas funcionalidades no alteraran módulos que ya se encontraban funcionando correctamente.

## 16. Integración del trabajo

Los cambios del dashboard administrativo fueron integrados con las métricas financieras y posteriormente incorporados a la rama `develop`.

También se incorporaron otros cambios del Sprint 6, como:
- histórico de tasas;
- exportación de transacciones a PDF;
- mejoras de navegación;
- documentación del sprint.

## 17. Decisiones importantes

Durante el Sprint 6 se tomaron las siguientes decisiones:

1. Mostrar las ganancias siempre en PYG.
2. Diferenciar claramente ganancia y volumen.
3. Incorporar filtros por período y divisa.
4. Evitar gráficos con datos ficticios.
5. Utilizar únicamente información persistida en el sistema.
6. Mantener dashboards diferentes según el rol.
7. Reutilizar servicios existentes antes de duplicar lógica.
8. Mantener el criterio temporal actual por fecha de creación durante este sprint.
9. Dejar el posible cambio a fecha de finalización para una revisión posterior.
10. Mantener las visualizaciones dinámicas pero sin animaciones excesivas.

## 18. Resultado del uso de IA

El uso de inteligencia artificial permitió:
- organizar mejor los requerimientos;
- analizar alternativas de diseño;
- detectar inconsistencias antes de cerrar el sprint;
- definir métricas de manera más clara;
- mejorar la experiencia visual;
- revisar permisos y comportamiento por rol;
- preparar criterios de pruebas;
- documentar decisiones técnicas.

La IA fue utilizada principalmente como herramienta de apoyo para análisis y revisión, mientras que las decisiones finales se tomaron considerando los requerimientos de la materia y el comportamiento real del proyecto.

## 19. Conclusión

Durante el Sprint 6 el sistema evolucionó principalmente en el área de reportes, métricas y análisis.

El dashboard administrativo pasó de mostrar información básica a convertirse en una herramienta con indicadores financieros, filtros y visualizaciones.

También se definió una estrategia para adaptar los dashboards según cada rol, especialmente para el Analista Cambiario.

Como mejora futura queda pendiente revisar el criterio temporal utilizado para reconocer las ganancias, evaluando el uso de la fecha de finalización de la operación en lugar de la fecha de creación.

En general, el uso de IA ayudó a mejorar la calidad de las decisiones, detectar detalles de implementación y mantener una visión más estructurada del Sprint 6.
