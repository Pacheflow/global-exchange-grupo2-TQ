# Dashboard administrativo — Sprint 6, fase 1

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
serializado mediante `json_script` en `dashboard-resumen`, preparado para una
integración posterior. Esta fase no introduce endpoint ni llamada asíncrona.

```json
{
  "ganancia_dia": null,
  "ganancia_semana": null,
  "ganancia_mes": null,
  "operaciones": 0,
  "compras": 0,
  "ventas": 0,
  "volumen": null,
  "moneda": "PYG"
}
```

Los valores del ejemplo corresponden a un histórico sin completadas. `null`
se presenta como «No disponible»; un importe futuro `"0"` es un resultado
disponible de cero. Los conteos son enteros. PYG es moneda de presentación,
no una conversión de los importes de actividad.

Un error de lectura presenta un aviso con recuperación por recarga y deja
también los conteos en null: no muestra ceros ni estado vacío falsos. Una
lectura exitosa sin completadas presenta conteos cero y estado vacío. No se
necesita estado de carga asíncrona porque la respuesta contiene todo el HTML.

## Dependencia financiera pendiente

No hay fórmula de ganancia, suma de comisiones ni cálculo de volumen. Antes
de conectar el backend financiero deben acordarse definición de ganancia,
períodos de día/semana/mes, fecha de reconocimiento, conversiones históricas,
redondeo, cobertura incompleta y definición de volumen. Los períodos de esas
métricas deberán documentarse aparte del histórico utilizado por los conteos.
El frontend únicamente presentará los importes y moneda recibidos.

## Verificación

`usuarios.test_dashboard` cubre permisos, contrato, conteos, estados, alcance
histórico, límite y orden de actividad, enlaces, cero frente a null y error de
lectura. Verifica ausencia de escrituras SQL y llamadas HTTP al cargar el
dashboard con sesión vigente, además de dos lecturas de operaciones sin N+1.

Comandos de validación:

```text
docker compose exec web python manage.py check
docker compose exec web python manage.py test usuarios.test_dashboard usuarios.tests operaciones.test_reporte_administrativo operaciones.tests operaciones.test_efectivo --noinput
git diff --check
```

Ejecución del 16/11/2026: Django check sin incidencias; 203 tests OK en
34,727 s. Tras reforzar el orden por fecha frente a ID: 15 tests específicos
del dashboard OK en 1,272 s. `git diff --check` sin errores.
La inspección visual en navegador no pudo realizarse porque el host
de acceso del navegador estaba indisponible. Los tests verifican HTML y
comportamiento; no sustituyen la inspección visual.
