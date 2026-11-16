# Sprint 6 — Guillermo Benítez: documentación técnica

## Alcance y decisiones

Fuente: `Plan_Sprint_6_Global_Exchange.md` proporcionado por Guillermo. Historias
HU-S6-02 (cálculo y reporte de ganancias) y HU-S6-05 (validación productiva).
El usuario confirmó expresamente **comisiones en PYG** como definición de ganancia.
No se calcula spread ni utilidad neta contable: no hay costo de adquisición,
gastos operativos ni posición de inventario histórica suficiente para ello.

La implementación conserva los flujos del sprint 5. No agrega tablas ni exige
migraciones. El dashboard visual corresponde a Axel; el reporte administrativo
con filtros de clientes y paginación corresponde a Elena; las series de tasas a
Elías. Esta entrega proporciona el servicio común que pueden consumir.

## Arquitectura y archivos

| Archivo | Responsabilidad |
| --- | --- |
| `operaciones/finanzas.py` | Conversión y cálculo único; acumulación y serialización del contrato |
| `operaciones/finanzas_views.py` | Validación de consulta, permisos y respuesta JSON |
| `operaciones/urls.py` | Publicación de la API |
| `operaciones/test_finanzas.py` | Pruebas de cálculo, contrato, permisos y consulta SQL |
| `scripts/validate-production.py` | Validación estática o de entorno productivo; evidencia JSON sin secretos |
| `scripts/test_validate_production.py` | Pruebas del validador sin Docker ni SSH |

Los consumidores deben llamar a `reporte_financiero(desde=..., hasta=...,
agrupacion=...)` o a su API; no duplicar las fórmulas en JavaScript o en otra vista.

## Reglas y fórmulas

Solo se incluyen `Transaccion.estado == COMPLETADA`. Pagos aprobados de una
operación pendiente no bastan para reconocer comisión. Una operación cancelada
no contribuye ni al monto ni al conteo.

`importe_comision` ya está expresado en **moneda_destino**, de acuerdo con
`operaciones.services._calcular_operacion`. No se vuelve a aplicar el porcentaje.
`monto_origen` y `tasa_aplicada` son valores guardados en la operación.

| Par de la operación | Volumen bruto en PYG | Comisión / ganancia en PYG |
| --- | --- | --- |
| Destino PYG | `monto_origen × tasa_aplicada` | `importe_comision` |
| Origen PYG | `monto_origen` | `importe_comision ÷ tasa_aplicada` |
| Ninguna pata PYG | Sin conversión | Sin conversión |

El volumen representa **una sola pata bruta** del intercambio: no se suman ambos
lados, ni se suma una comisión nuevamente al volumen. Compra y venta son los
tipos almacenados; los conteos incluyen también las operaciones no convertibles.

Para pares sin PYG no se emplean tasas actuales, tasas comerciales mutables,
caminos indirectos ni tasas deducidas sin respaldo. Se incrementan
`operaciones_sin_conversion` y `sin_conversion`, el campo `completo` es falso y
se agrega una advertencia. Los importes son entonces **parciales**, aunque las
cantidades sí incluyen todas las operaciones completadas del rango.

Se usa `Decimal`, contexto de precisión 64, y redondeo `ROUND_HALF_UP` a seis
decimales al terminar cada acumulación. Los importes JSON son cadenas para
conservar precisión. La suma de importes de buckets ya redondeados puede diferir
mínimamente del total redondeado una sola vez; el total es el valor autorizado.

## Fechas y agregación

La imputación es por **fecha de creación** de la transacción, y la API lo declara
como `fecha_imputacion=fecha_creacion`. Es una vista de cohortes de operaciones
actualmente completadas. **No equivale a ingresos liquidados durante ese día**.
El modelo no guarda una fecha de finalización independiente, y
`fecha_actualizacion` puede cambiar por otras razones; no se infiere una fecha
contable a partir de ella. Si una operación creada ayer se completa hoy, se
agrega al bucket de ayer. Los reportes históricos pueden cambiar al completarse
operaciones o corregirse datos.

Se utiliza la zona configurada en Django (`America/Asuncion` actualmente). Los
límites `desde` y `hasta` son fechas inclusivas locales; en SQL se consulta desde
medianoche inicial inclusive hasta medianoche del día posterior exclusiva.

- `dia`: cada día local.
- `semana`: lunes a domingo; `inicio` identifica el lunes.
- `mes`: mes calendario; `inicio` identifica el primer día.

Se incluyen buckets vacíos en cero. En extremos parciales, `desde` y `hasta` del
bucket indican el intervalo realmente consultado. El rango máximo es de 366 días
inclusivos; la restricción limita el trabajo temporal y el tamaño de la serie.

## Contrato HTTP para Axel y reportes

```http
GET /api/operaciones/metricas-financieras/?desde=2026-10-01&hasta=2026-10-03&agrupacion=dia
```

Autenticación: sesión OIDC verificada y vigente. Rol efectivo autorizado:
`ADMINISTRADOR`, igual que el acceso global a información administrativa del
proyecto. Los roles de cliente, cajero y operador no tienen acceso a este endpoint.
No requiere un cliente seleccionado. Respuesta `Cache-Control: no-store`.

| Parámetro | Tipo | Valor por defecto |
| --- | --- | --- |
| `desde` | Fecha estricta `YYYY-MM-DD` | Hoy menos 29 días |
| `hasta` | Fecha estricta `YYYY-MM-DD` | Hoy |
| `agrupacion` | `dia`, `semana`, `mes` | `dia` |

Se rechazan parámetros desconocidos, duplicados, fechas inválidas, rangos
invertidos o superiores al máximo. Si se proporciona una sola fecha, la otra
conserva su valor por defecto y se valida el rango resultante.

Ejemplo abreviado de respuesta (la respuesta real incluye todos los buckets):

```json
{
  "version": 1,
  "moneda": "PYG",
  "definicion_ganancia": "COMISIONES",
  "fecha_imputacion": "fecha_creacion",
  "estado": "COMPLETADA",
  "zona_horaria": "America/Asuncion",
  "desde": "2026-10-01",
  "hasta": "2026-10-03",
  "agrupacion": "dia",
  "totales": {
    "operaciones": 1,
    "compras": 1,
    "ventas": 0,
    "operaciones_convertidas": 1,
    "operaciones_sin_conversion": 0,
    "volumen": "700000.000000",
    "comisiones": "7000.000000",
    "ganancia": "7000.000000",
    "completo": true
  },
  "periodos": [
    {
      "inicio": "2026-10-01",
      "desde": "2026-10-01",
      "hasta": "2026-10-01",
      "operaciones": 1,
      "compras": 1,
      "ventas": 0,
      "operaciones_convertidas": 1,
      "operaciones_sin_conversion": 0,
      "volumen": "700000.000000",
      "comisiones": "7000.000000",
      "ganancia": "7000.000000",
      "completo": true
    }
  ],
  "sin_conversion": [],
  "advertencias": []
}
```

Estados: `200` consulta válida (también sin datos), `400` consulta inválida con
`error`, `401` sesión ausente o vencida, `403` rol no permitido, `405` método
diferente de GET para una sesión autorizada. Los permisos se comprueban antes
de atender la consulta.

Para las tarjetas de ganancia diaria, semanal y mensual: consultar el rango
correspondiente y leer `totales.ganancia`. Para series: usar `periodos` y la
agrupación deseada. La semana actual empieza el lunes, el mes actual el día 1;
los períodos actuales terminan hoy. No confundir semana calendario con últimos
siete días. Mostrar siempre PYG y advertir si `totales.completo` es falso. Un
resultado vacío se muestra como cero, no como error. El gráfico debe respetar
la fecha que entrega la API; convertir `YYYY-MM-DD` a UTC en JavaScript puede
desplazar el día mostrado en algunas zonas horarias.

Ejemplo desde una pantalla autenticada del mismo origen:

```javascript
const params = new URLSearchParams({
  desde: '2026-10-01', hasta: '2026-10-31', agrupacion: 'dia'
});
const response = await fetch(`/api/operaciones/metricas-financieras/?${params}`, {
  credentials: 'same-origin'
});
const data = await response.json();
if (!response.ok) throw new Error(data.error || 'No se pudo consultar el reporte');
// Renderizar data.totales y data.periodos; atender data.advertencias.
```

## Rendimiento y límites

Una consulta SQL selecciona operaciones y sus dos monedas mediante
`select_related`. `iterator(chunk_size=1000)` evita cargar todas las operaciones
en memoria. Los acumuladores ocupan espacio proporcional al número de períodos
y pares sin conversión. El cálculo sigue siendo O(N) respecto de las operaciones
del rango; no hay materialización, caché, cierre contable ni promesa de latencia
para grandes volúmenes. No se crean índices sin medir primero un plan de ejecución.

## Pruebas y reproducibilidad

En el entorno oficial de desarrollo:

```bash
docker compose exec -T web python manage.py test operaciones.test_finanzas
docker compose exec -T web python manage.py test
python3 -m unittest discover -s scripts -p test_validate_production.py -v
node --test static/js/tests/*.test.cjs
```

Los tests financieros crean sus datos, no llaman proveedores y comprueban:
monedas de origen/destino, tasa histórica aplicada, parciales, estados, límites
locales, buckets vacíos, semana/mes/año, precisión acumulada, validación,
autorización OIDC, métodos HTTP, contrato JSON y una consulta sin N+1.

La evidencia de ejecución y las limitaciones productivas están en
[Sprint6_Guillermo_Validacion.md](Sprint6_Guillermo_Validacion.md).
