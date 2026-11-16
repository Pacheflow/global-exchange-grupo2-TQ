# Sprint 6 — guía de implementación para Guillermo Benítez

## Qué entregaste

Tu parte es el núcleo financiero que usarán el dashboard de Axel y otros reportes,
junto con la validación del despliegue. Hay una API nueva y una herramienta que
revisa el servidor y deja evidencia. La documentación técnica está en
[Sprint6_Guillermo_Tecnico.md](Sprint6_Guillermo_Tecnico.md).

## 1. Qué llamamos ganancia y por qué

Confirmaste que para este sprint **ganancia significa comisión, expresada en
guaraníes (PYG)**. Cuando se realiza una operación, el sistema ya guarda cuánto
se cobró de comisión. El reporte toma ese valor: no vuelve a cobrarlo ni vuelve a
calcularlo con la categoría actual del cliente.

Ejemplo: el cliente cambia USD 100 a una tasa de PYG 7.000 por dólar. El monto
bruto es PYG 700.000. Con una comisión del 1 %, el sistema guarda PYG 7.000 de
comisión y entrega PYG 693.000. El reporte muestra:

| Indicador | Valor |
| --- | --- |
| Operaciones | 1 |
| Compras o ventas | Según el tipo guardado |
| Volumen | PYG 700.000 |
| Comisión | PYG 7.000 |
| Ganancia | PYG 7.000 |

Ese valor es ingreso por comisiones. No representa utilidad neta después de
sueldos, gastos e impuestos, y no incorpora una ganancia por spread.

Solo entran operaciones **completadas**. Una transacción pendiente todavía no
genera ganancia en este reporte. Una cancelada tampoco cuenta. La aprobación
de un pago no reemplaza el estado final de la operación.

## 2. Cómo evitamos mezclar dólares, euros y guaraníes

No se pueden sumar una comisión de USD 2 y otra de PYG 7.000 como si fueran
PYG 7.002. Para obtener una moneda común, el servicio revisa las monedas de
cada operación.

Si la moneda de destino es PYG, la comisión ya está en guaraníes y se suma
directamente. Si PYG es la moneda de origen, la comisión está en la otra moneda:
se divide por la tasa aplicada que quedó guardada en esa operación.

Ejemplo sencillo de la segunda situación: se cambian PYG 700.000, con una tasa
ilustrativa de USD 0,00014 por PYG. La comisión guardada es USD 1. Convertirla
implica `1 / 0,00014`, que resulta en PYG 7.142,857143, con el redondeo del reporte.

Si el par es USD/EUR, no hay una conversión a PYG registrada en esa transacción.
Por eso no se inventa una cotización. La operación aparece en los conteos, pero
sus montos no se suman. La API entrega una advertencia, el par afectado y cuántas
operaciones quedaron sin convertir. Un dashboard debe mostrar ese total como
**parcial**. Resolver esos casos exige registrar una conversión histórica a PYG
al operar, o acordar una fuente histórica adicional.

Cambiar la cotización comercial de hoy no altera el cálculo de una operación
anterior: la tasa utilizada es la que quedó guardada al confirmarla.

## 3. Qué significan los períodos

Podés pedir una serie diaria, semanal o mensual. Las semanas empiezan el lunes;
los meses son meses calendario. Los días sin operaciones se devuelven con cero,
para que el gráfico no omita fechas.

Las fechas que se consultan incluyen ambos extremos. Del 1 al 3 de octubre
incluye los días 1, 2 y 3 completos en el horario de Paraguay configurado por el
proyecto. Hay un límite de 366 días por consulta.

Hay una decisión que debés poder explicar al presentar el trabajo: **la operación
se ubica en la fecha en que se creó**. El modelo actual no guarda una fecha
independiente de finalización. Si se creó el lunes y se completó el martes, al
consultar después aparece en el lunes. Es un reporte de operaciones actualmente
completadas por su fecha de creación; no un libro contable de cobros del día.
La API informa esta regla para que nadie interprete mal los datos.

## 4. Qué hace cada parte del código

`operaciones/finanzas.py` reúne las reglas anteriores. `importes_pyg` convierte
una operación. `reporte_financiero` consulta las completadas del rango, crea los
períodos, cuenta compras y ventas, acumula importes y avisa qué no pudo convertir.
Los mismos acumuladores se usan para el total y para cada período.

La implementación usa números decimales. Redondea al final, evitando perder
fracciones en cada operación. Por ejemplo, tres comisiones que equivalen a un
tercio de guaraní suman un guaraní al final. Los importes viajan como texto en el
JSON para conservar su precisión.

`operaciones/finanzas_views.py` es la entrada HTTP. Comprueba fechas y parámetros,
llama al servicio y entrega el resultado. La protección existente de Keycloak
verifica la sesión y el rol administrador. Un cliente no puede consultar las
ganancias globales de la empresa.

`operaciones/urls.py` registra la nueva dirección:

```text
/api/operaciones/metricas-financieras/
```

`operaciones/test_finanzas.py` verifica los cálculos y el contrato desde el
backend. También verifica que consultar varias operaciones no genere una
consulta adicional por cada una. La consulta trae las monedas junto con cada
transacción.

No se agregaron tablas ni se modificaron pagos, facturación, caja o fondos.
El servicio lee los datos existentes y calcula el reporte al consultar.

## 5. Cómo probarlo vos y mostrarlo al equipo

1. En el entorno que tenga estos cambios, iniciá sesión como administrador.
2. Abrí esta URL del mismo sitio, ajustando el período a datos reales:

   ```text
   /api/operaciones/metricas-financieras/?desde=2026-10-01&hasta=2026-10-31&agrupacion=dia
   ```

3. Revisá `moneda`, `fecha_imputacion` y `totales`. Una consulta sin operaciones
   devuelve ceros. No crea datos ni modifica el estado de las operaciones.
4. Cambiá `agrupacion` por `semana` y luego por `mes`. El total se mantiene
   para el mismo rango; cambia la distribución de `periodos`.
5. Verificá `completo` y `advertencias` antes de interpretar los importes.
6. Probá con una fecha inválida: devuelve 400. Sin sesión devuelve 401; con
   un rol no autorizado, 403.

Para probar las tarjetas actuales de Axel, hay que consultar desde hoy hasta
hoy para el día, desde el lunes hasta hoy para la semana, y desde el primer día
del mes hasta hoy para el mes. En cada caso se utiliza `totales.ganancia`.
El frontend debe formatear el valor para presentación, sin recalcular el negocio.

## 6. Qué valida la herramienta de despliegue

`scripts/validate-production.py` tiene dos modos. El estático revisa la sintaxis
del script Bash existente y que Docker Compose pueda resolver la configuración.
No necesita arrancar contenedores. Con una plantilla valida estructura, no
credenciales reales ni un despliegue final.

El modo `--runtime` agrega comprobaciones de los contenedores, la revisión de
la imagen de Django, migraciones aplicadas, advertencias de configuración de
producción y la respuesta interna de Nginx. La herramienta devuelve código 1
si falla un check; código 0 si los checks solicitados pasan. El JSON distingue
si se ejecutó realmente la validación productiva.

La evidencia conserva nombres de comprobaciones y resultados, sin contraseñas,
tokens, salida completa de Docker ni contenido del archivo `.env.production`.
Crea un archivo privado y se niega a sobrescribir uno existente. Eso conserva
las evidencias previas y evita seguir enlaces hacia otros archivos.

El validador no despliega código, no reinicia servicios ni ejecuta migraciones:
`migrate --check` solo comprueba si hay pendientes. El script existente
`deploy-production.sh` sí actualiza código, realiza backups y recrea servicios;
son herramientas distintas y deben usarse con ese conocimiento.

Los resultados reales y las acciones pendientes están en
[Sprint6_Guillermo_Validacion.md](Sprint6_Guillermo_Validacion.md). El código nuevo
se probó en contenedores separados; esa prueba no significa que ya esté publicado
en la aplicación que usa la gente.
