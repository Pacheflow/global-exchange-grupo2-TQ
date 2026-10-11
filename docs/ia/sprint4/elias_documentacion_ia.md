# Documentación de uso de IA - Sprint 4

## Integrante

Elías Hirano

## Historias de usuario trabajadas

- HU-42 - Realizar Arqueo
- HU-43 - Cerrar Caja
- HU-44 - Consultar Historial de Caja

## Uso de IA

Durante el Sprint 4 se utilizó IA como apoyo para comprender la estructura existente
del módulo de cajas, analizar las dependencias con las historias implementadas por
otros integrantes y proponer una implementación para las HU-42, HU-43 y HU-44.

La IA fue utilizada principalmente para orientar la implementación, revisar la lógica,
proponer casos de prueba y explicar el funcionamiento del código desarrollado.

## HU-42 - Realizar Arqueo

Para HU-42 se analizó primero la implementación existente de HU-38, HU-39, HU-40
y HU-41.

Se decidió reutilizar el cálculo de saldo existente en:

`cajas/services.py`

especialmente la función:

`_saldos_del_periodo(periodo)`

De esta manera no se creó una lógica paralela para calcular el saldo teórico.

Se implementaron los modelos:

- `ArqueoCaja`
- `DetalleArqueoCaja`

El arqueo registra:

- período de caja
- usuario responsable
- fecha y hora
- observación
- moneda
- saldo teórico
- saldo físico
- diferencia
- resultado del arqueo

La diferencia se calcula como:

`Diferencia = saldo físico - saldo teórico`

El resultado se clasifica como:

- SOBRANTE si la diferencia es mayor que cero
- FALTANTE si la diferencia es menor que cero
- SIN_DIFERENCIA si la diferencia es igual a cero

También se agregó el servicio `realizar_arqueo()`, el formulario, la vista,
la URL y la pantalla correspondiente.

## HU-43 - Cerrar Caja

Para HU-43 se implementaron:

- `CierreCaja`
- `DetalleCierreCaja`

Antes de cerrar se comprueba que el período continúe abierto y que exista
un arqueo previo.

El cierre conserva:

- saldo teórico
- saldo físico
- diferencias
- usuario responsable
- fecha y hora

Al confirmar el cierre, el estado del período cambia de `ABIERTO` a `CERRADO`.

Como los movimientos existentes utilizan `_obtener_periodo_abierto()`,
al cerrar el período los nuevos movimientos quedan bloqueados sin duplicar
la lógica existente.

También se agregó una validación para impedir cerrar utilizando un arqueo
desactualizado cuando existen movimientos posteriores al arqueo.

## HU-44 - Consultar Historial de Caja

Para HU-44 no se creó un modelo adicional porque la información histórica
ya queda almacenada mediante:

- `PeriodoCaja`
- `MovimientoCaja`
- `ArqueoCaja`
- `DetalleArqueoCaja`
- `CierreCaja`
- `DetalleCierreCaja`

Se implementó `consultar_historial_caja()` para recuperar todos los períodos
de una caja con sus aperturas, movimientos, arqueos, diferencias y cierres.

La consulta está disponible para los roles:

- CAJERO
- ADMINISTRADOR

La funcionalidad es únicamente de consulta y no modifica registros históricos.

Si una caja no posee períodos registrados, se informa que no hay información
disponible.

## Decisiones tomadas durante el desarrollo

Se evitó duplicar el cálculo de saldos realizado previamente en HU-40 y HU-41.

Se reutilizó la estructura de `PeriodoCaja` creada en HU-38 y HU-39.

Se mantuvo la validación de permisos en backend y no solamente en las vistas
o formularios.

Se utilizó `transaction.atomic()` en las operaciones de arqueo y cierre para
evitar escrituras parciales.

Se utilizó bloqueo del período durante operaciones críticas para evitar
inconsistencias con movimientos concurrentes.

Se descartó crear una tabla especial solamente para historial, ya que el historial
puede reconstruirse a partir de los registros persistidos de cada período.

## Pruebas implementadas

Se agregaron los archivos:

- `cajas/test_arqueo.py`
- `cajas/test_cierre.py`
- `cajas/test_historial.py`

### HU-42

Se probaron escenarios como:

- cálculo de sobrante y faltante
- arqueo sin diferencia
- utilización del saldo teórico actualizado con movimientos
- rechazo de saldos físicos negativos
- rechazo de arqueo sobre período cerrado
- control de rol CAJERO

### HU-43

Se probaron escenarios como:

- cierre correcto con arqueo previo
- rechazo del cierre sin arqueo
- bloqueo de movimientos después del cierre
- rechazo de un segundo cierre
- control de rol CAJERO
- rechazo del cierre cuando hubo movimientos después del último arqueo

### HU-44

Se probaron escenarios como:

- consulta de movimientos, arqueos, diferencias y cierre
- conservación de períodos históricos al abrir un nuevo período
- caja sin historial
- acceso de CAJERO y ADMINISTRADOR
- rechazo de roles no autorizados

## Verificación humana

Después de implementar las funcionalidades se realizaron verificaciones mediante
los comandos del proyecto.

Se ejecutó:

`python manage.py check`

Resultado:

`System check identified no issues`

También se verificaron las migraciones con:

`python manage.py makemigrations --check --dry-run`

sin cambios pendientes.

Las pruebas del módulo de cajas finalizaron correctamente:

`99 tests - OK`

Finalmente se ejecutó la suite completa del proyecto:

`325 tests - OK`

También se ejecutó:

`git diff --check`

sin errores de formato pendientes.

## Archivos relacionados

Los principales archivos relacionados con el trabajo fueron:

- `cajas/models.py`
- `cajas/services.py`
- `cajas/forms.py`
- `cajas/views.py`
- `cajas/urls.py`
- `cajas/test_arqueo.py`
- `cajas/test_cierre.py`
- `cajas/test_historial.py`
- `cajas/migrations/0004_arqueocaja_detallearqueocaja.py`
- `cajas/migrations/0005_cierrecaja_detallecierrecaja.py`
- `templates/frontend/caja_arqueo.html`
- `templates/frontend/caja_cierre.html`
- `templates/frontend/caja_historial.html`
- `templates/frontend/caja_saldo.html`
- `templates/frontend/cajas.html`
- `templates/frontend/cajas_operar.html`

## Resultado

La IA fue utilizada como herramienta de apoyo durante el desarrollo.

Las propuestas fueron revisadas y adaptadas a la estructura existente del proyecto,
evitando duplicar funcionalidades implementadas por otros integrantes.

El resultado final fue validado mediante revisión del código, pruebas automáticas
y comprobaciones de Django antes de integrarlo a la rama `develop`.