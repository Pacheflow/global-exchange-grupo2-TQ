# Dashboard administrativo — Sprint 6, integración financiera

## Dashboard dinámico — implementación vigente (19/11/2026)

La segunda solicitud de Axel reemplaza expresamente los conteos históricos y
los tres KPI temporales por métricas coordinadas del período y divisa elegidos.
Esta sección es vigente; las etapas siguientes se conservan como antecedentes.

### Arquitectura y seguridad

Django renderiza el panel inicial con el mismo contrato JSON que entrega
`GET /api/operaciones/dashboard/metricas/` (`operaciones:dashboard_metricas`).
`usuarios.dashboard` valida filtros y compone un reporte y cinco recientes.
`operaciones.finanzas.operaciones_completadas` comparte estado, rango local y
selección de divisa entre ambas lecturas. Se reutilizan `reporte_financiero` e
`importes_pyg`: sin duplicar cálculos, sin tasas actuales, sin cambios de
imputación (`fecha_creacion`, COMPLETADA). La API anterior
`/api/operaciones/metricas-financieras/` mantiene parámetros y contrato.

El endpoint usa el rol efectivo ADMINISTRADOR y sesión OIDC vigente: 401 para
anónimo/expirada, 403 para otros roles, 405 para métodos distintos de GET,
400 para filtros inválidos, 503 para error de base de datos. Respuestas
`no-store`; sin escrituras de negocio. Dos consultas de transacciones,
independientes de la cantidad de filas, más catálogo/sesión. No se promete una
fotografía transaccional exacta entre las dos lecturas concurrentes.

### Filtros

- `periodo=hoy|semana|mes|3meses|6meses|12meses|personalizado`; defecto `mes`.
  Hoy incluye el día local completo; semana, lunes a hoy; mes, día 1 a hoy;
  N meses, primer día del mes de hace N−1 meses hasta hoy.
- Personalizado: ambas fechas ISO inclusivas, hasta 366 días. Se infiere
  `personalizado` si llegan desde/hasta sin período. Parámetros desconocidos,
  duplicados, fechas incompletas y combinación de fechas no vacías con presets
  se rechazan. No se impone un límite arbitrario de pasado/futuro.
- `divisa=` o ausencia significa Todas. Opciones obtenidas del catálogo activo,
  excluyendo PYG. El backend rechaza divisas desconocidas/inactivas; una URL
  histórica puede dejar de ser válida si se desactiva su moneda.
- Regla exacta: `moneda_origen.codigo == divisa OR moneda_destino.codigo == divisa`.
  USD→PYG y PYG→USD pertenecen ambas a USD. El OR entre FK simples no duplica
  filas. Cruces sin PYG también conservan conteos/actividad si contienen la
  divisa elegida; se excluyen de importes sin conversión fiable.
- Todos los KPI, evolución, distribución y actividad usan la misma selección.
  Actividad: máximo cinco, orden creación DESC y PK DESC. El enlace al reporte
  completo conserva su comportamiento previo; el reporte no fue modificado.
- Evolución: días para hoy/semana/mes y personalizados de hasta 62 días; meses
  para 3/6/12 meses y personalizados más amplios. Buckets vacíos cero, extremos
  parciales identificados; como máximo 62 puntos diarios o 13 mensuales.

### Contrato

Respuesta: `version`, `filtros` (selección, fechas efectivas, granularidad y zona
horaria), `resumen`, `evolucion`, `distribucion`, `actividad_reciente`,
`advertencias`, `fecha_imputacion`.

Resumen: `ganancia_pyg`, `volumen_pyg` como strings decimales, `operaciones`,
`compras`, `ventas`, `excluidas`, `moneda=PYG`. Importes son subtotales de las
operaciones convertibles y se rotulan cuando existen exclusiones; los conteos
las incluyen. No disponible por error no se representa como cero.

Distribución Todas: comisión PYG por divisa distinta de PYG del par, porcentajes
sobre la suma convertible del rango; categorías cero omitidas. Divisa específica:
Compras vs Ventas por cantidad de operaciones. Importes conservan precisión del
servicio; presentación monetaria entera HALF_UP, puntos de miles, sufijo PYG.

### Frontend

Chart.js 4.5.1 UMD local con licencia MIT, origen/hash en
`static/vendor/chartjs/README.md`. No requiere CDN en runtime. Se usa
[actualización de instancias Chart.js](https://www.chartjs.org/docs/latest/developers/updates.html)
y [contenedores responsive](https://www.chartjs.org/docs/latest/configuration/responsive.html).
Los valores aproximados Number solo alimentan canvas/animación; textos finales,
leyendas y tooltips formatean strings con BigInt, sin perder precisión financiera.

- Fetch de la respuesta completa sin reload; cancelación y secuencia para
  descartar respuestas/errores antiguos. Carga discreta con `aria-busy` y estado
  anunciado. En error se conservan datos, títulos y controles de última consulta
  exitosa; aviso y reintento con Aplicar filtros. No se exponen detalles internos.
- Barras y dona persistentes actualizadas con transición de 800 ms easeOutQuart.
  Entrada desde cero y dibujo progresivo de dona; contador KPI de 800 ms con
  valor final exacto. `prefers-reduced-motion` desactiva animación, también cuando
  la preferencia cambia con el panel abierto.
- Tooltips de período/categoría, importe PYG o cantidad y porcentaje; tabla de
  evolución y leyenda visible permiten consultar sin depender del hover/canvas.
- Query params actualizados después de cada éxito; atrás/adelante consulta sin
  agregar historial. Si falla, restaura la URL de los datos conservados.
- Editar período, divisa o fechas solo prepara la selección. La consulta se
  ejecuta al enviar Aplicar filtros (también con Enter). Limpiar restablece Este
  mes/Todas y carga inmediatamente sus datos; personalizados habilitan
  dos fechas. Desktop
  dos gráficos; tablet/móvil apilados. Tablas con scroll local, sin overflow de
  página por gráficos. Sin librería se mantienen tabla, leyenda y KPI disponibles.

### Archivos de esta evolución

`operaciones/finanzas.py`, `operaciones/dashboard_views.py`, `operaciones/urls.py`,
`usuarios/dashboard.py`, `usuarios/graficos.py`, `usuarios/views.py`,
`templates/frontend/dashboard_administrador.html`,
`templates/frontend/partials/dashboard_graficos.html`,
`static/css/dashboard-graficos.css`, `static/js/dashboard.js`,
`static/js/tests/dashboard.test.cjs`, `static/vendor/chartjs/` (distribución,
licencia y procedencia), `usuarios/test_dashboard.py`, `usuarios/test_graficos.py`
y este documento. Se preservan los cambios previos de filtro/importes y tests.

### Validación de esta evolución

- 44/44 pruebas focales Django OK (3,332 s): dashboard, gráficos, importes y
  finanzas. Subtests cubren todos los presets, personalizados/límites, USD/EUR/
  Todas, ambas direcciones, exclusiones, actividad, permisos y parámetros.
- JavaScript: 84/84 OK (1.427 ms); 16 son del tablero. Incluye transiciones y
  tooltips con doble del motor Chart.js, counters, movimiento reducido, fetch
  fuera de orden, errores, URL y cleanup. No equivale a render de canvas real.
- Regresión amplia usuarios/operaciones: 309 ejecutadas, 308 exitosas y 1 falla
  en descarga PDF existente por reportlab ausente (68,387 s). Requirements ya
  declara reportlab 4.4.9; no se instaló ni se modificó facturación/reportes.
- `manage.py check` sin incidencias; `git diff --check` correcto. Detector sin
  hallazgos; resolución del enlace CSS static de Django limitada.
- Runtime tras recargar solo web: nueve peticiones de prueba en memoria a API
  con datos locales reales, todas 200; panel renderizado 200 con filtros,
  referencias Chart.js y JSON inicial. CSS, JS y Chart.js servidos HTTP 200.
- Inspección manual en navegador, canvas real, hover real, breakpoints y consola
  pendientes: el host de navegador sigue indisponible. No se afirma que se
  completó la lista de QA manual de la solicitud.
- Sin commit, push, tag ni modificación de Jira. Rama conservada
  `feature/admin-dashboard-graficos-pyg`, base `6dbe9f9`.

---

## Etapa previa — gráficos SSR del 19/11/2026

Esta sección reemplaza el comportamiento de presentación descrito en las notas
históricas del 16/11 cuando difieran. Base revisada: `develop` en `6dbe9f9`,
árbol limpio; trabajo en `feature/admin-dashboard-graficos-pyg`, sin commit/push.

- Se mantienen KPI, conteos históricos, actividad, enlaces y permisos. Ganancia
  día/semana/mes muestra la suma de comisiones convertibles a PYG, con aviso de
  subtotal y cantidad excluida por período si faltan conversiones. Volumen
  conserva el criterio previo: no disponible si su cobertura es incompleta.
- Barras: seis meses calendario, incluido el actual hasta hoy; períodos sin
  comisiones se completan con cero. Tabla desplegable con mes/año, PYG y
  exclusiones. Sin ganancias positivas se presenta estado vacío.
- Dona: comisiones PYG agrupadas por divisa distinta de PYG del par, tanto
  origen extranjero → PYG como PYG → destino extranjero. Porcentaje = comisión
  PYG de la divisa / suma de comisiones PYG del mismo período. No se representan
  categorías de comisión cero. Pares sin PYG se excluyen de ambos gráficos.
- `operaciones.finanzas.reporte_financiero` agrega distribución solo con la
  opción interna `incluir_distribucion=True`. La API actual conserva su
  respuesta por defecto. Se reutiliza `importes_pyg`, tasa aplicada histórica y
  `Decimal`; no se consultan tasas actuales ni se crean conversiones faltantes.
- Imputación por `fecha_creacion`, estado COMPLETADA, zona horaria del sistema,
  igual que el servicio previo. No se cambia a fecha de liquidación.
- `usuarios.graficos` adapta los datos a SVG renderizado en servidor, sin JS ni
  CDN nuevos. `usuarios.views.dashboard` consulta gráficos solo para ADMINISTRADOR
  y aísla su error de base de datos de los KPI y la actividad.
- Filtro dedicado `importe_pyg`: guaraníes enteros, miles con puntos y redondeo
  visual HALF_UP. JSON y cálculos mantienen su precisión; `importe_legible`
  conserva su comportamiento para actividad y reportes.

Archivos: `operaciones/finanzas.py`, `usuarios/dashboard.py`, `usuarios/graficos.py`,
`usuarios/views.py`, `usuarios/templatetags/importes.py`,
`templates/frontend/dashboard_administrador.html`,
`templates/frontend/partials/dashboard_graficos.html`,
`static/css/dashboard-graficos.css`, `usuarios/test_dashboard.py`,
`usuarios/test_graficos.py`, `usuarios/test_importes.py` y este documento.

Verificación actual:

- `docker compose exec -T web python manage.py test usuarios.test_dashboard usuarios.test_importes usuarios.test_graficos operaciones.test_finanzas --noinput`:
  **50 ejecutadas / 50 exitosas**, 3,795 s.
- Regresión `manage.py test usuarios operaciones --noinput`: **317 ejecutadas,
  316 exitosas y 1 fallida**, 56,179 s. Fallo en descarga PDF existente por
  `ModuleNotFoundError: reportlab` en el contenedor. Esta ejecución incluyó
  pruebas importadas duplicadas en el primer borrador del archivo nuevo; luego
  se corrigió el descubrimiento, ver ejecución focal final anterior. No se
  suman las cantidades de ejecuciones distintas.
- `manage.py check`: sin incidencias. `git diff --check`: correcto.
- Detector Impeccable: sin hallazgos; no resuelve el enlace CSS mediante static
  de Django, por lo que su comprobación de estilos es parcial.
- QA visual pendiente: host de navegador no disponible; intento de acceso a
  ventana nativa agotó el tiempo de autorización. Los tests HTML/SVG no
  sustituyen inspección visual de escritorio y móvil.
- Recargado únicamente web local. Render directo de vista con petición de prueba
  en memoria y datos locales: 200, títulos de ambos gráficos presentes.
- Jira no consultado ni modificado: el alcance proviene de la solicitud explícita
  del usuario, sin afirmar estados de HU o Definition of Done.

---

## Alcance histórico

`GET /panel/` conserva la selección de panel por rol efectivo. Únicamente
ADMINISTRADOR recibe el dashboard administrativo y ejecuta su consulta.
USUARIO, CAJERO y ANALISTA_CAMBIARIO conservan sus paneles.

Los conteos de operaciones, compras y ventas abarcan **todo el histórico de
Transaccion con estado COMPLETADA**, sin filtro temporal. No representan el
mes actual ni la fecha de liquidación. Los parámetros GET no cambian ese
alcance. Esta elección está identificada en pantalla.

La actividad muestra hasta cinco transacciones COMPLETADA ordenadas por
`fecha_creacion DESC, pk DESC`. La fecha mostrada es la de creación. Se
mantienen los importes originales y sus monedas, sin conversiones. Cada fila
enlaza al detalle administrativo existente y la sección enlaza al reporte
completo; no se duplica su filtrado ni su paginación.

## Contrato de presentación

`usuarios.dashboard.consultar_dashboard_administrativo` entrega un resumen y
una lista acotada de operaciones. El resumen se renderiza en servidor y queda
serializado mediante `json_script` en `dashboard-resumen`, con las métricas del
servicio financiero compartido. El dashboard sigue siendo
SSR: no hace llamadas HTTP internas ni introduce un endpoint adicional.

```json
{
  "ganancia_dia": "0.000000",
  "ganancia_semana": "0.000000",
  "ganancia_mes": "0.000000",
  "operaciones": 0,
  "compras": 0,
  "ventas": 0,
  "volumen": "0.000000",
  "moneda": "PYG"
}
```

Los valores del ejemplo corresponden a un histórico sin completadas. `null`
se presenta como «No disponible»; un importe `"0.000000"` es un resultado
disponible de cero. Los conteos son enteros. PYG es moneda de presentación,
no una conversión de los importes de actividad.

Un error de lectura presenta un aviso con recuperación por recarga y deja
también los conteos en null: no muestra ceros ni estado vacío falsos. Una
lectura exitosa sin completadas presenta conteos cero y estado vacío. No se
necesita estado de carga asíncrona porque la respuesta contiene todo el HTML.

## Fuente financiera integrada (16/11/2026)

Al revisar el árbol se encontró un merge en curso de
`origin/feature/sprint6-guillermo-finanzas` (MERGE_HEAD eec3b99) sobre
`feature/axel-sprint6-metricas` (HEAD cdcf70c), sin conflictos pendientes.
Se preservó ese estado: el merge no se finaliza porque no se autoriza commit.
El diff staged contiene 20 archivos de Guillermo; el reporte de Elena se conserva.
Su rama incluye documentación, validadores y exposición local de PostgreSQL en
`compose.yaml` mediante `DB_LOCAL_PORT` en `.env.example` (127.0.0.1:5433 por
defecto). Son cambios importados de Guillermo; no se recrearon servicios ni se
aplicó ese cambio a la infraestructura en ejecución.

Fuente de verdad: `operaciones.finanzas.reporte_financiero(desde, hasta,
agrupacion="dia")`. API existente: `GET /api/operaciones/metricas-financieras/`,
con fechas ISO inclusivas, agrupación dia/semana/mes, máximo 366 días, por defecto
últimos 30 días. Se conserva su contrato, sin renombrar campos en el backend:
metadatos version/moneda/definicion_ganancia/fecha_imputacion/estado/zona_horaria,
desde/hasta/agrupacion, totales, periodos, sin_conversion y advertencias.
Totales y períodos contienen operaciones/compras/ventas, operaciones_convertidas,
operaciones_sin_conversion, volumen/comisiones/ganancia como strings de seis
decimales, y completo booleano.

El adaptador del dashboard llama al mismo servicio tres veces, sin recalcular
fórmulas ni sumar importes: hoy; lunes a hoy; día 1 del mes a hoy. Todos usan
la zona horaria vigente del sistema y fecha_creacion, como Guillermo. Mapea
`totales.ganancia` a ganancia_dia/semana/mes y `totales.volumen` del mes a volumen.
Volumen es **mensual**, rotulado en pantalla; conteos y actividad siguen siendo
históricos. La moneda proviene del reporte mensual (PYG).

Ganancia significa comisiones, no utilidad por spread. Guillermo convierte usando
la tasa_aplicada histórica y acumula con Decimal, redondeando al final. Volumen
bruto contabiliza una sola pata del intercambio. Si un rango incluye pares sin
PYG, el servicio devuelve importes parciales y completo=false; el dashboard
presenta null / No disponible para las métricas de ese rango. No muestra el
subtotal como total ni lo convierte a cero. Un rango vacío completo sí muestra
"0.000000". No se cambian las fórmulas del backend ni se consultan tasas actuales.

El endpoint exige sesión OIDC vigente y rol efectivo ADMINISTRADOR en backend:
401 para anónimo/expirado, 403 para USUARIO/CAJERO/ANALISTA_CAMBIARIO, 200 para
ADMINISTRADOR. El dashboard conserva sus permisos y paneles por rol.

## Verificación

### Ajustes finales de presentación (16/11/2026)

El filtro común `usuarios.templatetags.importes.importe_legible` usa Decimal y
el agrupador de Django (`django.utils.numberformat.format`), sin float,
redondeo ni modificación del valor original. Aplica puntos para miles, coma
decimal y elimina únicamente ceros decimales finales: `51660.000000` se ve
como `51.660`, `0.000000` como `0`, y `1234.560000` como `1.234,56`.
Los decimales significativos se conservan también en PYG, sin redondear
silenciosamente una comisión fraccionaria. El JSON conserva los strings de
seis decimales del servicio; null sigue siendo «No disponible».

Se revisó `cajas.templatetags.importes_caja.importe_inicial`: está limitado a
importes por operación menores de 10^12 y hasta seis decimales; fuera de ese
rango devuelve el texto original. Por eso no se reutiliza para sumas financieras
que pueden superar ese límite. No se cambia Caja; el nuevo filtro común sirve
a las tarjetas, actividad reciente y montos/comisiones del listado y detalle
del reporte. Tasas, porcentajes, filtros y lógica del reporte siguen intactos.

La pantalla resume: «Ganancias por comisión · Valores en PYG · Períodos por
fecha de creación». Se mantienen los períodos de cada tarjeta y el alcance
histórico explícito de los conteos. El sidebar de administrador excluye listado
y detalle del reporte al activar Operaciones: ambas rutas activan únicamente
Transacciones; los otros roles y entradas conservan sus condiciones.

**Diferencia temporal pendiente:** la preferencia expresada por reconocimiento
al finalizar no coincide con la implementación de Guillermo. El servicio filtra
y agrupa por `Transaccion.fecha_creacion`, estado actual COMPLETADA, zona horaria
local; no consulta `fondos.OperacionCompletada.fecha`. Ese evento existe y se
crea en los flujos de finalización online y liquidación, pero sustituir la
fecha exige revisar su cobertura en datos históricos y acordar el tratamiento
de completadas sin evento. Las pruebas financieras actuales también crean
completadas directamente sin evento. No se usa `fecha_actualizacion` como
sustituto ni se cambia silenciosamente la fecha: una operación creada ayer y
completada hoy sigue imputándose a ayer. Cualquier cambio de reconocimiento
requiere alcance separado, tests y autorización.

Validación de estos ajustes: 65 tests OK en 4,771 s (formato, sidebar,
dashboard, reporte y finanzas), `manage.py check` sin incidencias y ambos
diff checks sin errores. Detector de templates sin hallazgos; no resuelve
los enlaces CSS mediante tags static de Django y no sustituye QA en navegador.

`usuarios.test_dashboard` cubre permisos, contrato, conteos, estados, alcance
histórico, límite y orden de actividad, enlaces, cero frente a null y error de
lectura. Verifica ausencia de escrituras SQL y llamadas HTTP al cargar el
dashboard con sesión vigente, además de cinco lecturas de operaciones sin N+1
(conteos, tres rangos y actividad).

Comandos de validación:

```text
docker compose exec web python manage.py check
docker compose exec web python manage.py test operaciones.test_finanzas usuarios.test_dashboard usuarios.tests operaciones.test_reporte_administrativo operaciones.tests operaciones.test_efectivo --noinput
git diff --check
```

Validación de integración del 16/11/2026: 53 tests OK en 4,679 s
(`operaciones.test_finanzas`: 14; `usuarios.test_dashboard`: 20;
`operaciones.test_reporte_administrativo`: 19). `manage.py check` sin incidencias;
`git diff --check` y `git diff --cached --check` sin errores. Además,
`python -m unittest discover -s scripts -p test_validate_production.py`: 6 OK;
`node --test static/js/tests/*.test.cjs`: 68 OK.
Regresión completa: `docker compose exec -T web python manage.py test --noinput`,
721 tests ejecutados y exitosos en 167,033 s; base de pruebas destruida por el runner.

Evidencia histórica Fase 1 del 16/11/2026: Django check sin incidencias; 203 tests OK en
34,727 s. Tras reforzar el orden por fecha frente a ID: 15 tests específicos
del dashboard OK en 1,272 s. `git diff --check` sin errores.
La inspección visual en navegador no pudo realizarse porque el host
de acceso del navegador estaba indisponible. Los tests verifican HTML y
comportamiento; no sustituyen la inspección visual.


## Cierre técnico previo al PR — 19/11/2026

Regresión final de la rama:415/415 pruebas Django (`usuarios tasas operaciones`)
y98/98 JavaScript exitosas. Django check y diffcheck correctos. Incluye métricas
administrativas, dashboard analista, tasas, histórico, filtros, permisos y PDF.
La dependencia PDF faltante de la imagen local fue reparada; no requiere cambios
adicionales al generador ni a requirements, donde ya estaba declarada.

Los filtros se aplican al enviar el formulario; Limpiar consulta inmediatamente
Este mes/Todas. Se conserva la animación inicial original: el intento posterior
de posponerla por visibilidad fue retirado por solicitud del usuario. No se
acredita QA visual en navegador. La documentación del analista detalla su alcance.
