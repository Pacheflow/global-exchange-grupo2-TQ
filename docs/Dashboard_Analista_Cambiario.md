# Dashboard del Analista Cambiario

Implementación local: 19/11/2026. Alcance solicitado por Axel en el adjunto
«Quiero rediseñar y completar el dashboard del rol ANALISTA_CAMBIARIO».
La validación técnica no implica actualización de Jira ni Definition of Done.

## Arquitectura y permisos

La vista `usuarios.views.dashboard` conserva el enrutamiento por rol efectivo.
Solo su rama ANALISTA_CAMBIARIO cambia. La carga inicial usa el mismo servicio
que el endpoint JSON nuevo `GET /api/tasas/dashboard-analista/`
(`tasas:dashboard_analista`). El endpoint requiere sesión OIDC vigente y rol
efectivo ANALISTA_CAMBIARIO. Respuestas 401/403/405, validación 400 y fallo de
base 503 controlados; caché deshabilitada. No realiza escrituras, no consulta
proveedores externos y no devuelve clientes, identidades, importes de
operaciones, comisiones, ganancias ni datos de Caja.

Reutilización existente, sin modificar los contratos administrativos:

- `usuarios.dashboard`: PERIODOS, catálogo de divisas activas y validación.
- `tasas.historico.consultar_registros`: versiones comerciales por par y fechas.
- `tasas.simulador.simular_conversion`: referencias vigentes directas, inversas
  o cruzadas, con la normalización ya utilizada por el conversor.
- `operaciones.finanzas.operaciones_completadas`: solo selección de completadas
  por fecha_creacion; se leen únicamente códigos de monedas y tipo.
- Chart.js 4.5.1 local, ya incorporado al proyecto. Sin librerías adicionales.

Los endpoints públicos de tasas, monedas e histórico permanecen disponibles.
La agregación protegida evita coordinar varias solicitudes parciales en el cliente.

## Filtros y alcance

Hoy, semana desde lunes, mes, últimos 3/6/12 meses calendario incluyendo el
actual y personalizado inclusivo en la zona local. Defecto Este mes / Todas.
Máximo 366 días. Se rechazan fechas invertidas, formatos incorrectos, parámetros
repetidos/desconocidos y divisas inexistentes/inactivas. El catálogo se obtiene
de Moneda; PYG es la base y no aparece como divisa del selector.

Editar período/divisa o fechas solo prepara la selección. Aplicar filtros
(también Enter) consulta por JSON sin recargar: variaciones, evolución, actividad
agregada y tablas. El formulario valida las fechas personalizadas antes de enviar
y el backend valida el intervalo. Aplicar funciona sin JavaScript por GET.
Limpiar restaura y carga Este mes/Todas inmediatamente. La URL refleja
consultas exitosas; atrás/adelante restaura datos sin agregar historial.

Las dos tarjetas USD/PYG y EUR/PYG son **referencias vigentes globales** y están
rotuladas así: no se simula una referencia histórica ni se ocultan al seleccionar
otra divisa. Tasas vigentes, última actualización y Mercado actual son una
fotografía actual de pares comerciales DIVISA/PYG con ambas monedas activas,
filtrada por divisa, independiente del período histórico. No se incluyen pares
inversos o cruzados en el mercado PYG para evitar mezclar unidades.

## Reglas numéricas

El modelo TasaReferencia conserva la última tasa por par; no ofrece la misma
serie histórica de versiones que TasaComercial. Por ello se usa explícitamente
**compra comercial** para todas las variaciones y su KPI. No se mezcla con las
tarjetas de referencia ni con venta.

- Inicial: primera versión comercial registrada dentro del período.
- Final: última versión registrada dentro del período, no la tasa vigente fuera
  del intervalo. Si falta alguno de esos registros no se inventa un extremo.
- Absoluta = final.compra − inicial.compra.
- Porcentual = ((final.compra − inicial.compra) / inicial.compra) × 100.
- Al menos dos versiones y compra inicial positiva. Con menos datos:
  «Sin histórico suficiente». Se conserva cero como variación válida.
- Mayor variación = mayor magnitud absoluta del porcentaje, conservando signo
  y par. No significa necesariamente la mayor subida; la lista muestra subidas
  y bajadas por separado mediante +/− además del color.
- Spread = venta − compra de la misma versión vigente, con Decimal exacto.
  Compra/venta/spread comerciales conservan los decimales persistidos, sin
  mezclar el redondeo de presentación de las referencias con estas diferencias.

El JSON serializa tasas/diferencias/porcentajes como cadenas. La presentación
agrupa tasas sin convertirlas a float; Number se usa para el canvas y para el
porcentaje visual a dos decimales. Los tooltips de tasas usan el dato original.

## Gráficos y actividad

Evolución: dos líneas Compra/Venta, eje temporal proporcional y tooltip con fecha,
importe y PYG. Con Todas se grafica USD/PYG si existe USD activo; en su ausencia,
la primera divisa activa por código. Esa selección se indica sobre el gráfico.
No se promedian distintas divisas. Si el par elegido carece de datos se muestra
vacío aunque otro par tenga historia.

Para acotar el canvas se muestra la última versión real de cada día y además
el primer extremo real: máximo 367 puntos por intervalo. No se crean tasas ni
se rellenan días vacíos. Los cálculos de variación consideran todos los registros.
Una sola versión puede mostrarse como punto, pero no produce una variación.

Distribución Todas: participaciones por divisa activa no PYG en operaciones
COMPLETADAS. Cada moneda se cuenta una sola vez por operación. Un cruce USD/EUR
participa en ambas categorías: los porcentajes usan la suma de participaciones,
no la cantidad única de operaciones. La cantidad única y compras/ventas se
muestran aparte. Con divisa específica: Compra vs Venta, contando cada operación
una sola vez incluso si aparece en cualquiera de sus patas. La divisa más
operada usa estos conteos del período; empates se resuelven por código.

Entrada discreta de KPI y gráficos, transiciones en las mismas instancias,
hover/tooltip, carga por opacidad, mensajes vacíos y tablas/leyenda alternativas.
`prefers-reduced-motion` desactiva animaciones y transiciones. Sin Chart.js
siguen disponibles KPI, tablas y leyenda. Responsive: 3/2/1 columnas KPI;
gráficos apilados a partir de 1200px; tablas con scroll local.

Las solicitudes anteriores se abortan y sus respuestas se ignoran por secuencia.
Errores mantienen datos/filtros de la última consulta exitosa y no exponen trazas.
Los componentes se destruyen al salir con Unpoly, sin duplicar listeners.

## Archivos de este alcance

- `tasas/dashboard_analista.py`: servicio y endpoint protegido.
- `tasas/urls.py`: ruta API.
- `usuarios/views.py`: solamente integración del rol analista para esta tarea.
- `templates/frontend/dashboard_analista.html` y
  `templates/frontend/partials/analista_kpi.html`: interfaz y fallback HTML.
- `static/css/dashboard-analista.css`: estilos aislados del rol.
- `static/js/dashboard-analista.js`: filtros, gráficos y estados.
- `tasas/test_dashboard_analista.py`: pruebas backend.
- `static/js/tests/dashboard-analista.test.cjs`: pruebas del controlador.
- Este documento.

El repositorio ya contenía cambios sin commit de solicitudes anteriores;
esos cambios se conservaron. Este alcance no cambia el dashboard administrativo,
Caja, Fondos, pagos, Stripe, facturación, reportes o fórmulas financieras.

## Verificación

- Backend focal: 28 pruebas ejecutadas y exitosas.
- JavaScript focal: 13 pruebas ejecutadas y exitosas.
- Suite JavaScript completa: 98 ejecutadas y exitosas.
- `manage.py check`: sin problemas identificados.
- Regresión completa `manage.py test tasas usuarios --noinput`: 200 pruebas
  ejecutadas, 200 exitosas (37,170 s). Incluye permisos relacionados y panel admin.
- Runtime con datos persistidos y RequestFactory/sesión de prueba solo en memoria:
  siete períodos y HTML inicial 200. Hoy/semana/mes/personalizado sin puntos;
  3/6/12 meses con dos puntos reales. Mercado actual con dos tasas. No se
  escribieron datos ni se creó una sesión persistente.
- HTTP sin autenticar: endpoint 401, CSS/JS del analista 200.
- Detector de layout: sin hallazgos en los archivos del analista; advierte que no
  resuelve automáticamente la etiqueta Django static del stylesheet enlazado.
- `git diff --check`: correcto.

La automatización del navegador informa «The browser access host is unavailable».
Por ello no se acredita validación visual real de desktop/móvil, hover,
animaciones ni consola del navegador. Los tests de controlador verifican estados,
transiciones, tooltips y reduced motion; no sustituyen esa revisión visual.


## Cierre técnico previo al PR — 19/11/2026

Se verificaron juntos los dashboards, tasas, histórico, filtros, permisos,
operaciones y endpoints de la rama: `manage.py test usuarios tasas operaciones
--noinput`, 415 pruebas ejecutadas y exitosas (73,095 s). Suite JavaScript
completa:98/98 exitosas. `manage.py check` y `git diff --check` correctos.
El PDF administrativo tiene ReportLab4.4.9 disponible en la imagen local;
las pruebas del reporte también están incluidas en la regresión exitosa.
Los archivos privados no forman parte del alcance versionado.

Estado final de filtros: editar prepara la selección; Aplicar consulta sin
recargar; Limpiar restaura y carga Este mes/Todas inmediatamente. Los accesos
a Tasas/Monedas/Histórico permanecen en el sidebar, sin duplicación en el
encabezado. La animación del panel administrativo conserva la implementación
previa al intento posterior de diferirla por visibilidad, retirado a petición
del usuario. La revisión visual en navegador sigue sin acreditarse.
