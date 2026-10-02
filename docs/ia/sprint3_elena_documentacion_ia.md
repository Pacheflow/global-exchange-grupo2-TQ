# Documentación de conversaciones con IA --- Sprint 3


### Pregunta 1

**Usuario:**\
\> ¿Podemos revisar primero qué modelos existentes tenemos para
construir la parte de Operaciones sin duplicar información?

**IA:**\
Sí. Antes de crear `Transaccion` conviene revisar las entidades
existentes y reutilizarlas.

Los modelos relevantes fueron:

-   `Cliente`
-   `UsuarioCliente`
-   `MetodoPago`
-   `Moneda`
-   `TasaComercial`
-   `TasaReferencia`

`Cliente` permite saber quién realiza la operación y tiene estado
`ACTIVO/INACTIVO`.

`UsuarioCliente` relaciona la identidad de Keycloak con un cliente y
permite determinar qué clientes puede operar un usuario.

`MetodoPago` funciona como catálogo global.

`Moneda` tiene estados de activación.

`TasaComercial` contiene las tasas comerciales de compra y venta y está
versionada.

Esto permite que `Transaccion` mantenga relaciones con esos modelos y
almacene snapshots de los valores que deben permanecer históricos.

### Pregunta 2

**Usuario:**\
\> ¿Cómo sabemos si un usuario realmente puede operar sobre un cliente?

**IA:**\
El patrón existente utiliza `UsuarioCliente`.

Para usuarios que no son administradores se comprueba que exista una
asociación:

-   con el cliente solicitado;
-   con el `keycloak_user_id` de la sesión;
-   con `activo=True`.

La validación debe hacerse nuevamente en el backend al confirmar la
operación.

------------------------------------------------------------------------
## 3. Diseño del modelo Transaccion

### Pregunta 3

**Usuario:**\
\> ¿Qué debería guardar `Transaccion` para que el historial no cambie si
después cambia la cotización?

**IA:**\
La transacción debe conservar snapshots de los valores utilizados en el
momento de la operación:

-   `monto_origen`;
-   `monto_destino`;
-   `tasa_aplicada`;
-   `porcentaje_comision`;
-   `importe_comision`;
-   `metodo_pago_nombre`.

También conserva las referencias a cliente, monedas, tasa comercial y
método de pago.

De esta manera, el historial no necesita recalcular una operación
histórica usando una tasa actual.

### Pregunta 4

**Usuario:**\
\> ¿Qué hacemos si alguien intenta borrar una moneda, cliente, método de
pago o tasa que ya fue utilizada en una transacción?

**IA:**\
Para conservar la trazabilidad histórica se decidió utilizar `PROTECT`
en las relaciones de `Transaccion`.

Esto evita que una eliminación física rompa las referencias históricas.

### Pregunta 5

**Usuario:**\
\> ¿Qué estados necesitamos para este Sprint 3?

**IA:**\
Para el alcance definido del Sprint 3 se utilizaron:

-   `PENDIENTE`
-   `COMPLETADA`
-   `CANCELADA`

El flujo normal confirma una operación válida directamente como
`COMPLETADA`. `PENDIENTE` se conserva para HU-25 y escenarios heredados o
futuros que pueden pasar a `CANCELADA`.

### Pregunta 6

**Usuario:**\
\> ¿Qué restricciones conviene poner directamente en la base de datos?

**IA:**\
Las reglas estructurales que pueden garantizarse mediante la base de
datos deben expresarse mediante `CheckConstraint` o restricciones
únicas.

Se implementaron:

-   `clave_idempotencia` única;
-   monedas de origen y destino diferentes;
-   monto de origen positivo;
-   monto de destino positivo;
-   tasa aplicada positiva;
-   porcentaje de comisión entre 0 y 100;
-   importe de comisión no negativo;
-   una operación `CANCELADA` debe tener los datos de cancelación;
-   una operación que no está `CANCELADA` no debe tener datos de cancelación.

Las reglas que dependen de otras entidades o procesos permanecen en
`services.py`.

------------------------------------------------------------------------

## 4. Primera etapa: modelo y migración

### Pregunta 7

**Usuario:**\
\> ¿Es mejor que el agente implemente primero solamente `models.py` y la
migración antes de hacer `services.py`?

**IA:**\
Sí. Es más seguro porque `Transaccion` será la base utilizada por
compra, venta, cancelación e historial.

Primero conviene:

1.  crear `operaciones/models.py`;
2.  generar `0001_initial.py`;
3.  revisar campos;
4.  revisar relaciones;
5.  revisar `on_delete`;
6.  revisar constraints;
7.  comparar con la guía y la ERS;
8.  recién después implementar los servicios.

### Pregunta 8

**Usuario:**\
\> ¿Podemos pedirle al agente que nos muestre `models.py` y
`0001_initial.py` sin modificar nada?

**IA:**\
Sí. Para una revisión segura se puede solicitar:

-   contenido de `operaciones/models.py`;
-   contenido de `operaciones/migrations/0001_initial.py`;
-   diff respecto de `HEAD`;
-   ninguna modificación adicional.

Después de revisar el modelo se puede autorizar la siguiente etapa.

**Resultado:** el modelo y la migración fueron revisados y considerados
consistentes con la guía y la ERS disponibles.

------------------------------------------------------------------------

## 5. Comisión por categoría

### Pregunta 9

**Usuario:**\
\> La guía habla de comisión del 1%, pero no dice claramente sobre qué
monto se calcula. ¿Qué hacemos?

**IA:**\
No conviene inventar la fórmula si la documentación no la define.

Se identificaron tres posibilidades:

1.  descontar la comisión del monto convertido;
2.  calcularla sobre el convertido e informarla aparte;
3.  calcularla sobre el monto de origen.

Era necesario que el equipo definiera la regla funcional.

### Pregunta 10

**Usuario:**\
\> ¿Cómo manejan normalmente las casas de cambio reales la comisión?

**IA:**\
Existen diferentes modelos comerciales. Algunas incorporan el margen en
la tasa, otras cobran una comisión separada y otras combinan ambos
mecanismos.

Para el proyecto no conviene elegir una fórmula solamente por analogía
con una casa de cambio real. La fórmula debe responder a la
especificación funcional del sistema.

### Pregunta 11

**Usuario:**\
\> ¿Cuál vamos a utilizar en nuestro proyecto?

**IA:**\
Se definió que la comisión se descuenta del monto convertido y se
informa explícitamente.

La fórmula acordada fue:

``` text
monto_convertido = monto_origen × tasa_aplicada
importe_comision = monto_convertido × porcentaje_comision / 100
monto_destino = monto_convertido − importe_comision
```

### Pregunta 12

**Usuario:**\
\> ¿Qué porcentajes de comisión vamos a utilizar?

**IA:**

  Categoría       Comisión
  ------------- ----------
  Minorista            10%
  Corporativo           7%
  VIP                   5%

La comisión se obtiene desde `Cliente.categoria`. No se utiliza
`tipo_persona`.

### Pregunta 13

**Usuario:**\
\> ¿Qué pasa si un cliente no tiene categoría? No quiero que aparezca
simplemente una comisión de 0%.

**IA:**\
La operación debe rechazarse si el cliente no tiene categoría o si la
categoría no tiene una comisión configurada. No se aplica 0%
silenciosamente.

------------------------------------------------------------------------

## 6. Previsualización

### Pregunta 14

**Usuario:**\
\> ¿Qué debería hacer `previsualizar_operacion()`?

**IA:**\
Debe validar y calcular, pero no persistir una `Transaccion`.

El flujo es:

1.  validar identidad;
2.  validar tipo;
3.  obtener cliente activo;
4.  validar asociación `UsuarioCliente`;
5.  validar monedas activas;
6.  validar que sean diferentes;
7.  validar monto;
8.  obtener tasa comercial vigente;
9.  seleccionar compra o venta;
10. validar método de pago activo;
11. obtener comisión;
12. calcular resultado;
13. devolver un objeto de preview.

Una prueba importante verifica que la preview no cree registros.

### Pregunta 15

**Usuario:**\
\> ¿Qué tasa debe utilizar una operación?

**IA:**\
En el núcleo de Operaciones se utiliza `TasaComercial` vigente para el
par solicitado.

-   `COMPRA` → tasa de compra;
-   `VENTA` → tasa de venta.

El proyecto también tiene `TasaReferencia` y proveedores externos para
obtener tasas de referencia. La separación entre tasa externa/de
referencia y tasa comercial debe respetarse según el flujo definido por
el proyecto.

------------------------------------------------------------------------

## 7. Confirmación y cambio de cotización

### Pregunta 16

**Usuario:**\
\> ¿Por qué no podemos confiar en la tasa que manda el frontend?

**IA:**\
Porque el frontend puede enviar información obsoleta o modificada.

La confirmación vuelve a consultar la tasa en backend y recalcula los
valores. El frontend sirve para mostrar la preview, pero el backend es
la fuente de verdad para confirmar.

### Pregunta 17

**Usuario:**\
\> ¿Cómo detectamos que cambió la cotización antes de confirmar?

**IA:**\
La `TasaComercial` tiene versionado. La fuente de verdad es:

``` text
version_preview
```

contra:

``` text
tasa_comercial.version
```

Si las versiones son diferentes, se considera que la cotización cambió.

### Pregunta 18

**Usuario:**\
\> ¿Qué pasa si el valor numérico coincide pero la versión cambió?

**IA:**\
También debe considerarse un cambio. La versión representa el estado
publicado de la tasa.

### Pregunta 19

**Usuario:**\
\> ¿Qué pasa si cambia la cotización?

**IA:**\
La confirmación se rechaza y exige una nueva previsualización. No se crea una
transacción con datos obsoletos. La cancelación de una transacción ya existente
es un flujo separado de HU-25 y solo admite registros `PENDIENTE`.

------------------------------------------------------------------------

## 8. Transacciones atómicas y bloqueo

### Pregunta 20

**Usuario:**\
\> ¿Por qué usamos `select_for_update()`?

**IA:**\
Para reducir condiciones de carrera durante la confirmación.

La tasa se bloquea dentro de:

``` python
transaction.atomic()
```

con:

``` python
select_for_update()
```

Esto permite que la lectura utilizada para confirmar sea consistente con
la decisión de versión.

------------------------------------------------------------------------

## 9. Idempotencia

### Pregunta 21

**Usuario:**\
\> ¿Cómo evitamos que un doble clic o reintento cree dos operaciones?

**IA:**\
Mediante `clave_idempotencia`.

El campo es único en la base de datos. La confirmación busca una
operación existente y maneja además una posible carrera de unicidad
durante el INSERT.

Cada operación nueva conserva también una huella SHA-256 nullable del payload
canónico. Incluye usuario, cliente, tipo, monedas, monto, método, versión de
tasa, categoría del preview y porcentaje. No calcula valores económicos ni
reemplaza las validaciones del backend. Las filas históricas sin huella se
rechazan de forma genérica al reutilizar su clave.

### Pregunta 22

**Usuario:**\
\> ¿Debemos capturar cualquier `IntegrityError` y asumir que es una
repetición?

**IA:**\
No. La implementación reconoce específicamente la violación de unicidad
correspondiente a la clave de idempotencia. Otros `IntegrityError` deben
propagarse para no ocultar errores reales.

------------------------------------------------------------------------

## 10. Historial

### Pregunta 23

**Usuario:**\
\> ¿Cómo debería funcionar el historial?

**IA:**\
Debe ser solamente de consulta.

Para usuarios normales se muestran operaciones de clientes asociados
mediante `UsuarioCliente` activo. Para administradores pueden
consultarse todas.

El historial utiliza los valores guardados en la transacción y no
recalcula con tasas actuales.

### Pregunta 24

**Usuario:**\
\> ¿Por qué es importante no recalcular el historial?

**IA:**\
Porque una operación histórica debe representar exactamente lo ocurrido
en el momento de confirmación. Si la tasa cambia hoy, una operación
realizada ayer no debe cambiar.

Por eso se guardan snapshots.

------------------------------------------------------------------------

## 11. Endpoints

### Pregunta 25

**Usuario:**\
\> ¿Qué endpoints quedaron para Operaciones?

**IA:**

``` text
POST /api/operaciones/previsualizar/
POST /api/operaciones/crear/
POST /api/operaciones/cancelar/
GET  /api/operaciones/metodos-pago/
GET  /api/operaciones/historial/
GET  /api/operaciones/<id>/detalle/
```

La preview no persiste, la creación confirma y persiste, y el historial
es de solo lectura.

------------------------------------------------------------------------

## 12. Pruebas

### Pregunta 26

**Usuario:**\
\> ¿Qué pruebas deberíamos hacer para Operaciones?

**IA:**\
Las pruebas deben cubrir casos correctos, errores y reglas de seguridad.

Se implementaron pruebas para compra, venta, cálculo Decimal, comisión
por categoría, clientes y usuarios no autorizados, monedas y métodos
inactivos, tasa inexistente, preview sin persistencia, comisiones
Minorista/Corporativo/VIP, ausencia de categoría, creación, snapshots,
cambio de cotización, idempotencia, carrera de unicidad, historial
autorizado, administrador, canceladas, precisión decimal y URLs.

### Pregunta 27

**Usuario:**\
\> ¿Cómo debemos documentar los tests para que todos hagamos lo mismo?

**IA:**\
Cada test importante debe tener:

1.  un nombre descriptivo;
2.  un docstring corto;
3.  la regla que se está comprobando;
4.  la condición relevante;
5.  el resultado esperado.

Ejemplo:

``` python
def test_cambio_cotizacion_rechaza_confirmacion(self):
    """Comprueba que un cambio de cotización rechace la operación.

    Si la versión de la tasa cambió desde la previsualización, la
    confirmación no debe crear una transacción.
    """
```

El docstring debe explicar el comportamiento que se protege, no repetir
solamente el nombre.

### Pregunta 28

**Usuario:**\
\> ¿Cómo debería nombrar los tests?

**IA:**\
Usar nombres que expliquen directamente el comportamiento:

``` text
test_cliente_inactivo_es_rechazado
test_metodo_pago_inactivo_es_rechazado
test_misma_clave_no_duplica_transaccion
test_cambio_cotizacion_rechaza_confirmacion
test_historial_solo_muestra_clientes_autorizados
```

------------------------------------------------------------------------

## 13. Endurecimiento final

### Pregunta 29

**Usuario:**\
\> ¿Qué mejoras deberíamos hacer después de que la funcionalidad ya
funcione?

**IA:**\
Se realizó una revisión enfocada en condiciones de carrera y
consistencia.

Se reforzaron:

-   bloqueo de la tasa durante confirmación;
-   uso de `version_preview`;
-   detección específica de conflictos de idempotencia;
-   pruebas de carrera;
-   precisión de seis decimales;
-   serialización del historial.

### Pregunta 30

**Usuario:**\
\> ¿Cómo verificamos que todo quedó bien antes del commit?

**IA:**\
Se ejecutaron verificaciones como:

``` text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test operaciones
python manage.py test
python -m compileall operaciones
git diff --check
```

Durante el desarrollo se registró:

-   `operaciones`: 39/39 OK;
-   suite completa: 155/155 OK;
-   `manage.py check`: sin problemas;
-   `makemigrations --check --dry-run`: sin cambios;
-   `compileall`: OK.

------------------------------------------------------------------------

## 14. Documentación generada

### Pregunta 31

**Usuario:**\
\> ¿También debemos documentar el nuevo módulo en `docs/generated`?

**IA:**\
Sí.

Se agregaron los módulos de Operaciones al script:

``` text
scripts/generate_docs.py
```

y se generó documentación para:

``` text
docs/generated/operaciones/models.html
docs/generated/operaciones/services.html
docs/generated/operaciones/urls.html
docs/generated/operaciones/views.html
```

------------------------------------------------------------------------

## 15. Git y Pull Request

### Pregunta 32

**Usuario:**\
\> ¿En qué rama debería poner mi implementación?

**IA:**\
Se creó:

``` text
feature/sprint3-operaciones
```

partiendo de `develop`.

La funcionalidad se dejó en un commit independiente:

``` text
feat: implementar núcleo de operaciones del sprint 3
```

### Pregunta 33

**Usuario:**\
\> ¿Qué debemos revisar antes de hacer el Pull Request?

**IA:**\
Antes del PR conviene comprobar:

-   working tree limpio;
-   commit solamente con cambios de Operaciones;
-   ausencia de archivos afectados accidentalmente por CRLF;
-   tests pasando;
-   migración correcta;
-   documentación actualizada;
-   descripción clara del PR.

------------------------------------------------------------------------

## 16. Revisión final del PR

### Pregunta 34

**Usuario:**\
\> ¿Puedes revisar si mi PR cumple con lo que implementamos?

**IA:**\
La revisión confirmó la presencia de:

-   modelo `Transaccion`;
-   migración;
-   servicios;
-   vistas;
-   URLs;
-   tests;
-   documentación generada;
-   integración en `config/settings.py`;
-   integración en `config/urls.py`.

También se verificaron las reglas principales: comisión por categoría,
descuento de comisión, idempotencia, cambio de cotización por versión,
snapshots, historial autorizado y validación de cliente y usuario.

------------------------------------------------------------------------

## 17. Decisiones funcionales del Sprint 3

### Comisión

``` text
Minorista     → 10%
Corporativo   → 7%
VIP           → 5%
```

### Fórmula

``` text
monto_convertido = monto_origen × tasa_aplicada
importe_comision = monto_convertido × porcentaje_comision / 100
monto_destino = monto_convertido − importe_comision
```

### Cliente sin categoría

La operación se rechaza. No se interpreta como comisión 0%.

### Método de pago

Se utiliza el catálogo global y debe estar activo.

### Cambio de cotización

Se determina mediante la versión de `TasaComercial`.

### Idempotencia

`clave_idempotencia` es obligatoria y única. Una huella SHA-256 persistida
comprueba además que usuario, cliente y payload lógico coincidan en reintentos
normales y carreras de unicidad.

### Historial

Es solamente de consulta y utiliza snapshots.

### Cancelación

Una transacción `PENDIENTE` existente puede pasar a `CANCELADA` mediante el
flujo HU-25. Un cambio de cotización antes de confirmar rechaza la solicitud y
no crea una transacción.

------------------------------------------------------------------------
