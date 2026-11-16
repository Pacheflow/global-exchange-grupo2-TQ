# Dashboard administrativo — Sprint 6, integración financiera

## Alcance

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
