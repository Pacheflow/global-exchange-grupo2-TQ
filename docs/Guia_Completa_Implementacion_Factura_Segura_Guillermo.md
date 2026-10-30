# Guía completa de la integración con Factura Segura

## Global Exchange — Sprint 5 — trabajo de Guillermo Benítez

Esta guía explica qué se implementó, cómo funciona internamente, cómo se conecta
con el resto de Global Exchange, cómo se prueba y qué falta para realizar una
prueba real contra Factura Segura TEST.

La explicación corresponde al código de la rama:

```text
feature/hu-28-integracion-factura-segura
```

## 1. Resumen ejecutivo

La implementación agrega una frontera técnica entre Django y la API ESI de
Factura Segura. Su responsabilidad es:

1. Leer configuración y secretos exclusivamente del backend.
2. Validar la configuración antes de realizar llamadas externas.
3. Enviar solicitudes HTTPS con el formato requerido por Factura Segura.
4. Interpretar respuestas sin confundir “solicitud procesada” con “factura
   aprobada por SIFEN”.
5. Diferenciar errores locales, autenticación, proveedor, red y resultados
   indeterminados.
6. Evitar una segunda emisión cuando una llamada se repite o queda en timeout.
7. Consultar el estado de un CDC.
8. Descargar KuDE y XML con límites de seguridad.
9. Dejar un contrato estable para que HU-29/HU-30 creen el modelo funcional de
   factura, sus pantallas, correo y permisos.

La integración crea automáticamente una `Factura` local cuando la operación
queda `COMPLETADA`. La emisión externa se ejecuta de forma controlada mediante
`procesar_facturas`; no ocurre dentro de la liquidación financiera. El contrato
TEST incluido construye el DE con una política explícita y configurable, y está
limitado al ambiente y rango habilitados para el equipo 2 TQ.

## 2. Componentes y responsabilidades

| Archivo | Responsabilidad |
|---|---|
| `facturacion/apps.py` | Registra la aplicación Django. |
| `facturacion/models.py` | Factura, intento técnico, rango y número fiscal asignado. |
| `facturacion/migrations/` | Tablas funcionales, ledger técnico y numeración. |
| `facturacion/contracts/factura_segura_test.py` | Construye el JSON resumido ESI y extrae el DE calculado. |
| `facturacion/services/factura_segura.py` | Cliente HTTP y contrato con Factura Segura. |
| `facturacion/services/emision.py` | Coordinador persistente que evita emisiones duplicadas. |
| `facturacion/services/facturas.py` | Prepara, emite y descarga facturas del dominio. |
| `facturacion/signals.py` | Prepara una factura después de confirmar la operación. |
| `facturacion/management/commands/procesar_facturas.py` | Procesador recuperable de pendientes. |
| `facturacion/views.py` y `urls.py` | Consulta y descarga privada desde la web. |
| `facturacion/services/__init__.py` | Expone la interfaz pública para otros módulos. |
| `facturacion/admin.py` | Permite consultar intentos desde Django Admin en modo lectura. |
| `facturacion/test_factura_segura.py` | Pruebas sin acceso real a Internet. |
| `config/settings.py` | Lee las variables de entorno. |
| `compose.yaml` | Inyecta configuración en desarrollo. |
| `compose.prod.yaml` | Inyecta configuración en producción. |

## 3. Conceptos que no deben confundirse

### 3.1 Transacción

Es la compra o venta de divisas registrada en Global Exchange. Conserva cliente,
monedas, montos, tasa, comisión, canal y estado.

### 3.2 Pago

Indica cómo se abonó una compra. Stripe TEST puede devolver `APROBADO`, pero eso
no significa que exista una factura ni que SIFEN la haya aprobado.

### 3.3 Liquidación o finalización

Es el impacto financiero dentro de Global Exchange. Dependiendo del canal puede
intervenir Caja o el módulo de fondos online. La operación llega a
`COMPLETADA` después de esa finalización.

### 3.4 Documento electrónico y factura

El DE es el documento enviado a Factura Segura. La factura funcional debe tener
su propio modelo y estados. El proveedor puede generar un CDC y SIFEN todavía
puede mantenerlo pendiente, aprobarlo, observarlo, rechazarlo o cancelarlo.

```text
Pago aprobado != operación completada != DE generado != factura aprobada
```

## 4. Flujo general esperado

El flujo final del sistema debería ser:

```text
Usuario crea operación
        |
        v
Selecciona método de pago
        |
        v
Stripe TEST / efectivo
        |
        v
Pago aprobado o recepción confirmada
        |
        v
Caja o fondos online finalizan la operación
        |
        v
Transacción COMPLETADA
        |
        v
HU-29 arma y valida datos fiscales
        |
        v
Factura Segura: calcular_de
        |
        v
Reserva idempotente local
        |
        v
Factura Segura: generar_de
        |
        v
Guardar CDC e ID ESI
        |
        v
Consultar get_estado_sifen posteriormente
        |
        v
HU-30 permite ver/descargar/enviar
```

La parte implementada en esta rama comienza cuando HU-29 ya posee un JSON fiscal
válido y termina devolviendo resultados técnicos seguros.

## 5. Configuración

### 5.1 Variables disponibles

```env
FACTURA_SEGURA_API_URL=https://apitest.facturasegura.com.py/misife00/v1/esi
FACTURA_SEGURA_TOKEN=
FACTURA_SEGURA_RUC=
FACTURA_SEGURA_TIMEOUT_SECONDS=30
FACTURA_SEGURA_MAX_DOWNLOAD_BYTES=15728640
```

| Variable | Significado |
|---|---|
| `FACTURA_SEGURA_API_URL` | Endpoint ESI de TEST o producción. El cliente exige HTTPS. |
| `FACTURA_SEGURA_TOKEN` | Token técnico ESI. No es un token Keycloak. |
| `FACTURA_SEGURA_RUC` | RUC emisor, únicamente dígitos y sin DV. |
| `FACTURA_SEGURA_TIMEOUT_SECONDS` | Tiempo máximo de cada llamada, entre 0 y 60 segundos. |
| `FACTURA_SEGURA_MAX_DOWNLOAD_BYTES` | Máximo permitido para KuDE/XML, 15 MiB por defecto. |

### 5.2 Dónde configurarlas

Desarrollo local:

```text
.env
```

Servidor:

```text
.env.production
```

Los archivos `.env.example` contienen únicamente nombres y valores no secretos.
El token nunca debe subirse a Git, copiarse al frontend ni mostrarse en logs.

### 5.3 Cómo llega la configuración a Django

```text
.env / .env.production
        |
        v
Docker Compose environment
        |
        v
config/settings.py
        |
        v
obtener_factura_segura_client()
        |
        v
FacturaSeguraClient
```

La aplicación puede iniciar con token y RUC vacíos. La validación se realiza al
construir el cliente, evitando que la ausencia temporal de credenciales bloquee
otros módulos.

## 6. Autenticación y seguridad

Cada llamada incluye:

```http
Authentication-Token: TOKEN_ESI
```

El cuerpo no contiene el token:

```json
{
  "operation": "calcular_de",
  "params": {
    "DE": {}
  }
}
```

Protecciones implementadas:

- La URL debe ser HTTPS.
- No se admiten usuario o contraseña dentro de la URL.
- No se admiten query strings ni fragmentos configurados en la URL base.
- No se siguen redirecciones HTTP autenticadas.
- El token no puede estar vacío ni contener espacios.
- El RUC solo admite dígitos.
- El JSON debe ser serializable y no admite `NaN`.
- Los mensajes de excepción no contienen el token, el payload completo ni el
  mensaje interno de `requests`.
- KuDE y XML se descargan por streaming y poseen límite de tamaño.
- Se comprueba el `Content-Type` antes de entregar el archivo.

## 7. Cliente HTTP `FacturaSeguraClient`

### 7.1 Creación mediante factory

```python
from facturacion.services import obtener_factura_segura_client

client = obtener_factura_segura_client()
```

La factory toma todos los valores desde `django.conf.settings`. Otros módulos no
deben construir URLs ni leer tokens directamente.

### 7.2 `calcular_de`

```python
resultado = client.calcular_de(de_resumido)
```

Solicitud:

```json
{
  "operation": "calcular_de",
  "params": {
    "DE": "JSON resumido"
  }
}
```

Esta operación completa cálculos y estructura tributaria, pero no emite. Un
timeout de cálculo es reintentable porque todavía no debería existir una
emisión fiscal.

El adaptador devuelve `ResultadoOperacion`:

```python
resultado.codigo
resultado.descripcion
resultado.operacion_id
resultado.resultados
```

El contrato exacto del DE calculado debe verificarse con el ambiente autorizado.

### 7.3 `generar_de`

Llamada de bajo nivel:

```python
resultado = client.generar_de(de_calculado)
```

Devuelve `ResultadoGeneracion`, que agrega:

```python
resultado.cdc
```

El cliente exige que la primera entrada de `results` contenga un CDC válido. Sin
CDC, la respuesta se considera inválida.

No conviene invocar este método directamente desde vistas. Debe usarse el
coordinador idempotente explicado en la sección siguiente.

### 7.4 `consultar_estado`

```python
resultado = client.consultar_estado(cdc)
```

Envía:

```json
{
  "operation": "get_estado_sifen",
  "params": {
    "CDC": "...",
    "dRucEm": "RUC_SIN_DV"
  }
}
```

Regla fundamental:

```text
code >= 0 significa que la operación API fue atendida.
No significa automáticamente que SIFEN aprobó la factura.
```

La capa funcional debe revisar, en este orden:

1. `estado_inu`.
2. `estado_can`.
3. `estado_sifen`.

### 7.5 Descargas

```python
kude = client.descargar_kude(cdc)
xml = client.descargar_xml(cdc)
```

Cada resultado es un `ArchivoFactura`:

```python
archivo.contenido
archivo.content_type
archivo.nombre
```

KuDE debe ser `application/pdf`. XML admite `application/xml` o `text/xml`.
Las vistas de HU-30 deberán comprobar nuevamente que el usuario tenga acceso al
cliente dueño de la factura antes de devolver estos bytes.

## 8. Idempotencia persistente

### 8.1 Por qué hace falta

Supongamos que Django llama a `generar_de` y la conexión se corta. Existen dos
posibilidades:

1. Factura Segura nunca recibió la petición.
2. Factura Segura generó el documento, pero la respuesta no llegó a Django.

Repetir inmediatamente podría generar un documento duplicado. Por eso un timeout
de generación no se trata como un error común.

### 8.2 Modelo técnico

La tabla creada por `IntentoEmisionFacturaSegura` contiene:

| Campo | Uso |
|---|---|
| `clave_idempotencia` | Identidad única de la emisión. |
| `huella_documento` | SHA-256 del JSON canónico. |
| `estado` | Estado técnico del intento. |
| `cdc` | Identificador fiscal retornado. Único cuando existe. |
| `operacion_id` | ID ESI para auditoría o soporte. |
| `codigo_proveedor` | `code` retornado por Factura Segura. |
| `descripcion_proveedor` | Descripción exacta para diagnóstico interno. |
| `creado_en`, `actualizado_en` | Trazabilidad temporal. |

Esta tabla no reemplaza `Factura` ni `DetalleFactura`. Es un ledger técnico.

### 8.3 Uso correcto

```python
from facturacion.services import generar_documento_una_vez

resultado = generar_documento_una_vez(
    clave_idempotencia=f"factura:transaccion:{transaccion.id}:v1",
    de_calculado=de_calculado,
)

intento = resultado.intento
print(intento.estado)
print(resultado.reutilizado)
```

### 8.4 Cómo se calcula la huella

El documento se convierte a JSON canónico:

- claves ordenadas;
- separadores estables;
- codificación ASCII reproducible.

Luego se calcula SHA-256. El documento completo no se guarda en el ledger.

### 8.5 Comportamiento ante repeticiones

| Situación | Comportamiento |
|---|---|
| Clave nueva | Reserva registro y llama una vez al proveedor. |
| Misma clave y mismo JSON | Devuelve el intento anterior con `reutilizado=True`. |
| Misma clave y JSON distinto | Rechaza la solicitud. |
| Timeout anterior | Conserva `INDETERMINADA`; no vuelve a emitir. |
| Emisión anterior exitosa | Devuelve CDC anterior; no vuelve a emitir. |

La restricción `UNIQUE` de PostgreSQL protege incluso cuando dos procesos
intentan reservar la misma clave simultáneamente.

## 9. Estados técnicos

| Estado | Significado | Qué hacer |
|---|---|---|
| `EN_PROCESO` | Se reservó la emisión y todavía no se cerró. | Esperar o investigar un proceso abandonado. No reemitir. |
| `GENERADA` | El proveedor devolvió CDC válido. | Crear/enlazar Factura y programar consulta SIFEN. |
| `INDETERMINADA` | Timeout, conexión, `5xx` o respuesta inutilizable después de intentar emitir. | Conciliar con proveedor o soporte. No crear otra clave para evadir el bloqueo. |
| `ERROR` | Rechazo confirmado, autenticación o configuración inválida. | Revisar causa y definir una recuperación explícita. |

`GENERADA` significa generado por Factura Segura, no necesariamente aprobado por
SIFEN.

## 10. Errores controlados

| Excepción | Origen típico | ¿Se hizo IO? |
|---|---|---|
| `FacturaSeguraConfiguracionError` | URL/token/RUC/timeout inválidos. | No necesariamente. |
| `FacturaSeguraValidacionError` | DE, CDC o clave local inválidos. | No. |
| `FacturaSeguraAutenticacionError` | HTTP 401/403. | Sí, pero el proveedor rechazó autenticación. |
| `FacturaSeguraNoDisponible` | Timeout/red/5xx al calcular, consultar o descargar. | Incierto, pero no es emisión. |
| `FacturaSeguraResultadoIndeterminado` | Timeout/red/5xx durante generación. | No se conoce el resultado. |
| `FacturaSeguraRespuestaInvalida` | JSON, redirección, CDC, MIME o estructura inesperada. | Sí o hubo respuesta HTTP. |
| `FacturaSeguraProveedorError` | `code` negativo. | Sí; conserva código, descripción e ID. |

No debe mostrarse `descripcion_proveedor` directamente a clientes. Puede incluir
detalles internos y debe transformarse en un mensaje funcional controlado.

## 11. Relación con Django Admin

El modelo técnico se registra en `/admin/` en modo lectura:

- permite filtrar por estado;
- permite buscar por clave, CDC e ID ESI;
- no permite crear;
- no permite editar;
- no permite eliminar.

Esto evita alterar manualmente evidencia de idempotencia.

## 12. Migración y despliegue

La migración es:

```text
facturacion/migrations/0001_initial.py
```

Comprobar:

```bash
docker compose exec web python manage.py showmigrations facturacion
```

Aplicar:

```bash
docker compose exec web python manage.py migrate
```

En producción:

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  exec web python manage.py migrate
```

Verificar la tabla:

```sql
SELECT
    id,
    clave_idempotencia,
    estado,
    cdc,
    operacion_id,
    codigo_proveedor,
    creado_en,
    actualizado_en
FROM facturacion_intentoemisionfacturasegura
ORDER BY id DESC;
```

## 13. Cómo funcionan las pruebas automáticas

### 13.1 No llaman a Factura Segura

Las pruebas reemplazan `requests.Session` por `Mock`. Una clase
`RespuestaFalsa` simula:

- código HTTP;
- JSON;
- cabeceras;
- contenido de archivos;
- lectura por chunks.

Esto permite ejecutar la suite sin token, RUC ni acceso a Internet.

### 13.2 `SimpleTestCase`

Las pruebas del cliente HTTP usan `SimpleTestCase` porque no necesitan base de
datos. Verifican el adaptador como una unidad aislada.

Ejemplo conceptual:

```python
session = mock.Mock()
session.post.return_value = RespuestaFalsa(payload={
    "code": 0,
    "description": "Calculado",
    "results": [],
})

client = FacturaSeguraClient(..., session=session)
client.calcular_de({"dato": 1})

session.post.assert_called_once()
```

### 13.3 `TestCase`

Las pruebas de idempotencia usan `TestCase` y una base temporal. Comprueban la
restricción única y la persistencia de estados.

### 13.4 Escenarios cubiertos

1. URL HTTP rechazada.
2. Credenciales embebidas en URL rechazadas.
3. Token vacío o con espacios rechazado.
4. RUC inválido rechazado.
5. Timeout y tamaño máximo inválidos.
6. Estructura exacta de `calcular_de`.
7. Token exclusivamente en cabecera.
8. CDC retornado por `generar_de`.
9. Una sola llamada de generación.
10. Timeout de generación convertido en indeterminado.
11. Timeout de consulta convertido en no disponible.
12. Parámetros correctos para consultar estado.
13. `code` negativo con trazabilidad.
14. HTTP 401 y redirecciones.
15. JSON y DE inválidos.
16. MIME y tamaño del KuDE.
17. Factory basada en settings.
18. Reutilización de clave idempotente.
19. Conflicto entre clave y otro documento.
20. Persistencia del timeout sin reemisión.
21. Persistencia de rechazo del proveedor.

Los métodos anteriores se agrupan en 15 casos de prueba, varios con múltiples
subescenarios.

## 14. Cómo ejecutar las pruebas

Solo facturación:

```bash
docker compose run --rm web \
  python manage.py test facturacion --noinput
```

Regresión relacionada:

```bash
docker compose run --rm web \
  python manage.py test \
  facturacion pagos operaciones.test_guillermo \
  operaciones.test_efectivo operaciones.test_liquidacion_cierre \
  --noinput
```

Suite completa:

```bash
docker compose run --rm web \
  python manage.py test --noinput
```

Última evidencia de la rama integrada con `develop`:

```text
538 tests encontrados
538 tests aprobados
0 fallos
0 errores
```

Comprobar migraciones:

```bash
docker compose run --rm web \
  python manage.py makemigrations --check --dry-run
```

Debe devolver:

```text
No changes detected
```

## 15. Qué hace falta para una prueba real

### 15.1 Acceso técnico

- Usuario ESI habilitado.
- Token ESI de TEST.
- Emisor asociado al usuario ESI.
- RUC autorizado, sin DV para `FACTURA_SEGURA_RUC`.
- Confirmación de que la URL corresponde al contrato habilitado.

### 15.2 Datos fiscales

- RUC y DV del emisor.
- Timbrado.
- Establecimiento.
- Punto de expedición.
- Numeración válida.
- Actividad económica.
- Datos correctos del receptor.
- Correo obligatorio.
- Condición de operación.
- Moneda fiscal.
- Tipo de cambio cuando corresponda.
- Ítems, precio, unidad y tratamiento de IVA.

### 15.3 Definiciones todavía pendientes

- Qué concepto fiscal representa una compra/venta de divisas.
- Qué importe se factura: no debe confundirse facturación con ganancia.
- Tratamiento de IVA.
- Qué referencia de conversión a PYG debe aprobarse para operaciones cruzadas.
- Cuándo se dispara exactamente la emisión después de una transacción
  `COMPLETADA`.
- Política autorizada de recuperación de intentos `ERROR` o `INDETERMINADA`.

Sin estas definiciones se puede probar el adaptador con mocks, pero no debe
enviarse un documento fiscal inventado.

## 16. Plan seguro de prueba real

### Paso 1 — Configurar secretos

En `.env`, nunca en `.env.example`:

```env
FACTURA_SEGURA_TOKEN=TOKEN_REAL_DE_TEST
FACTURA_SEGURA_RUC=RUC_SIN_DV
```

Recrear el servicio para cargar variables:

```bash
docker compose up -d --force-recreate web
```

### Paso 2 — Verificar configuración sin imprimir el token

```bash
docker compose exec web python manage.py shell -c \
"from django.conf import settings; print({
    'url': settings.FACTURA_SEGURA_API_URL,
    'token_presente': bool(settings.FACTURA_SEGURA_TOKEN),
    'ruc_presente': bool(settings.FACTURA_SEGURA_RUC),
    'timeout': settings.FACTURA_SEGURA_TIMEOUT_SECONDS,
})"
```

### Paso 3 — Construir el cliente

```bash
docker compose exec web python manage.py shell
```

```python
from facturacion.services import obtener_factura_segura_client
client = obtener_factura_segura_client()
print(type(client).__name__)
```

Esto valida configuración, pero no llama al proveedor.

### Paso 4 — Probar primero `calcular_de`

Usar únicamente un JSON resumido validado por Factura Segura o por el equipo
tributario. `calcular_de` no emite.

```python
resultado = client.calcular_de(DE_RESUMIDO_VALIDADO)
print(resultado.codigo)
print(resultado.operacion_id)
```

No imprimir el payload completo si contiene datos personales.

### Paso 5 — Revisar el DE calculado

Validar manualmente:

- emisor;
- receptor;
- moneda;
- tipo de cambio;
- numeración;
- ítems;
- IVA;
- total.

### Paso 6 — Autorizar una única emisión TEST

Solo después de validar el documento:

```python
from facturacion.services import generar_documento_una_vez

resultado = generar_documento_una_vez(
    clave_idempotencia="factura:transaccion:ID_REAL:v1",
    de_calculado=DE_CALCULADO_VALIDADO,
)
print(resultado.intento.estado)
print(resultado.intento.cdc)
```

### Paso 7 — Consultar SIFEN posteriormente

No asumir aprobación inmediata:

```python
estado = client.consultar_estado(resultado.intento.cdc)
print(estado.codigo)
print(estado.resultados)
```

### Paso 8 — Descargar KuDE/XML

Solo cuando el estado lo permita:

```python
kude = client.descargar_kude(cdc)
xml = client.descargar_xml(cdc)
```

## 17. Cómo diagnosticar errores

### Configuración inválida

Revisar presencia, no valor:

```python
bool(settings.FACTURA_SEGURA_TOKEN)
bool(settings.FACTURA_SEGURA_RUC)
```

Nunca imprimir el token.

### HTTP 401/403

- token incorrecto o revocado;
- usuario ESI no autorizado;
- emisor no asociado;
- ambiente incorrecto.

### `code` negativo

Consultar:

```python
intento.codigo_proveedor
intento.descripcion_proveedor
intento.operacion_id
```

### `INDETERMINADA`

No crear una clave nueva. Revisar el ID ESI disponible, consultar al proveedor o
solicitar conciliación. El objetivo es evitar una factura duplicada.

### KuDE/XML rechazado

Verificar:

- CDC;
- estado SIFEN;
- ruta habilitada por el contrato;
- MIME retornado;
- límite de tamaño.

## 18. Qué permanece pendiente para un uso distinto de TEST

La base funcional ya contiene `Factura`, relación única con Transacción,
constructor del JSON resumido, numeración, listado, detalle y descargas privadas.
Para un uso fiscal o productivo todavía se requiere:

- confirmar con Factura Segura los datos asumidos del emisor;
- aprobación contable de concepto, IVA e importe facturable;
- validar contablemente la fuente usada para convertir toda comisión a PYG;
- tarea programada para consultar y persistir estados SIFEN;
- procedimiento de conciliación e inutilización de números;
- un rango/timbrado válido para producción;
- rotación y gestión productiva del token;
- revisión de privacidad, auditoría y operación del scheduler.

El envío de correo desde Global Exchange permanece fuera del alcance actual:
Factura Segura ya notifica según su propio flujo y la web permite consultar y
descargar el comprobante.

## 19. Preguntas frecuentes

### ¿El token ESI es el token de Keycloak?

No. Keycloak autentica personas en Global Exchange. El token ESI autentica al
backend frente a Factura Segura.

### ¿Stripe genera la factura?

No. Stripe TEST solamente procesa un pago simulado.

### ¿`code = 0` significa factura aprobada?

No. Significa que la operación de la API fue procesada correctamente según su
contrato. La aprobación fiscal se consulta a SIFEN.

### ¿Por qué no se reintenta automáticamente `generar_de`?

Porque un timeout no permite saber si el documento fue generado. Un reintento
ciego puede duplicarlo.

### ¿Por qué se guarda una huella y no todo el DE?

La huella permite detectar cambios sin duplicar datos personales o fiscales en
el ledger técnico. El modelo Factura debe decidir qué datos históricos guardar.

### ¿Se puede modificar el intento desde Django Admin?

No. Es evidencia técnica de idempotencia y se presenta en modo lectura.

### ¿Las pruebas automáticas necesitan credenciales?

No. Simulan por completo las respuestas HTTP.

### ¿Ya se puede probar contra el proveedor?

Se puede cuando existan token, emisor autorizado y un JSON fiscal validado. Sin
eso solo corresponde ejecutar pruebas simuladas.

## 20. Explicación corta para una defensa

> La integración separa el dominio de factura del proveedor externo. Django
> construye un cliente usando secretos del servidor, valida las solicitudes y
> envía el contrato operation/params por HTTPS. Antes de generar se reserva una
> clave idempotente única y una huella del documento. Si el proveedor devuelve
> un CDC, el intento queda GENERADA; si hay timeout queda INDETERMINADA y no se
> reemite automáticamente. Después se consulta SIFEN porque generar no equivale
> a aprobar. Las descargas de KuDE/XML se validan por permisos en la futura vista,
> MIME y tamaño. Todas las respuestas externas se prueban con mocks, por lo que
> la suite no necesita credenciales reales.

## 21. Checklist antes del PR o despliegue

- [ ] Migración `facturacion.0001_initial` aplicada.
- [ ] Suite `facturacion` aprobada.
- [ ] Regresión de pagos/operaciones aprobada.
- [ ] Suite completa aprobada.
- [ ] Token ausente de Git y logs.
- [ ] RUC sin DV configurado.
- [ ] Contrato del proveedor confirmado.
- [ ] Datos tributarios validados.
- [ ] Política de conciliación definida.
- [ ] HU-29 enlaza Factura con el intento técnico.
- [ ] HU-30 valida permisos antes de descargar o enviar.

## 22. Referencias internas

- `docs/HU-28_Integracion_Factura_Segura.md`
- `docs/arquitectura.md`
- `docs/pruebas.md`
- `facturacion/services/factura_segura.py`
- `facturacion/services/emision.py`
- `facturacion/models.py`
- `facturacion/test_factura_segura.py`

## 23. Actualización: contrato fiscal TEST operativo

Desde el 30/10/2026 el proyecto incluye el contrato fiscal concreto:

```text
facturacion.contracts.factura_segura_test.ContratoFacturaSeguraTest
```

Y queda seleccionado mediante:

```env
FACTURACION_CONTRATO=facturacion.contracts.factura_segura_test.ContratoFacturaSeguraTest
```

Este contrato es exclusivamente para el emisor y rango habilitados en Factura
Segura TEST. No tiene validez fiscal y no debe apuntarse a producción sin una
revisión contable, tributaria y funcional.

### 23.1 Política fiscal elegida para las pruebas

Para transformar una operación cambiaria en un documento repetible se definió
la siguiente política TEST explícita:

| Decisión | Implementación |
|---|---|
| Documento | Factura electrónica, `iTiDE=1`. |
| Concepto | Un ítem “Servicio de cambio de divisas”. |
| Importe | Comisión convertida y congelada en PYG. |
| Cantidad | Una unidad. |
| Moneda | Siempre PYG. |
| Condición | Contado. |
| COMPRA | Tipo de transacción SIFEN `6`, compra de divisas. |
| VENTA | Tipo de transacción SIFEN `5`, venta de divisas. |
| IVA TEST | Afectado 100 % al 10 %, configurable. |
| Pago efectivo | Tipo de pago `1`. |
| Pago electrónico | Tarjeta, tipo de pago `3`. |
| Presencia | Presencial, `iIndPres=1`, como valor TEST. |

El importe de comisión se calcula originalmente en la moneda destino. Al crear
el snapshot de factura se convierte a PYG y se conservan importe, tasa, fuente y
fecha de la conversión. El contrato rechaza comisiones iguales a cero o una
conversión ausente antes de reservar un número fiscal.

### 23.2 Valores confirmados por la habilitación

| Campo | Valor |
|---|---|
| Ambiente | TEST |
| Endpoint | `https://apitest.facturasegura.com.py/misife00/v1/esi` |
| `dRucEm` | `2595733` |
| `dDVEmi` | `3` |
| `iTipCont` | `1` |
| `dNumTim` | `02595733` |
| `dFeIniT` | `2025-03-27` |
| `dEst` | `001` |
| `dPunExp` | `003` |
| `dTelEmi` | `(021)5887000` |
| Desde | `0000338` |
| Hasta | `0000349` |

### 23.3 Valores asumidos y configurables para TEST

Estos valores completan el ejemplo, pero deben reemplazarse si Factura Segura
informa los datos exactos registrados para el emisor:

| Variable | Valor TEST por defecto | Campo ESI |
|---|---|---|
| `FACTURA_EMISOR_NOMBRE` | `GLOBAL EXCHANGE TEST` | `dNomEmi` |
| `FACTURA_EMISOR_DIRECCION` | `ASUNCION` | `dDirEmi` |
| `FACTURA_EMISOR_NUMERO_CASA` | `0` | `dNumCas` |
| `FACTURA_EMISOR_DEPARTAMENTO_CODIGO` | `1` | `cDepEmi` |
| `FACTURA_EMISOR_DEPARTAMENTO` | `CAPITAL` | `dDesDepEmi` |
| `FACTURA_EMISOR_CIUDAD_CODIGO` | `1` | `cCiuEmi` |
| `FACTURA_EMISOR_CIUDAD` | `ASUNCION (DISTRITO)` | `dDesCiuEmi` |
| `FACTURA_EMISOR_EMAIL` | `axeleliezer7@fpuna.edu.py` | `dEmailE` |
| `FACTURA_EMISOR_ACTIVIDAD_CODIGO` | `64990` | `cActEco` |
| `FACTURA_EMISOR_ACTIVIDAD_DESCRIPCION` | Servicio financiero TEST | `dDesActEco` |
| `FACTURA_TIPO_IMPUESTO` | `1` | `iTImp` |
| `FACTURA_AFECTACION_IVA` | `1` | `iAfecIVA` |
| `FACTURA_PROPORCION_IVA` | `100` | `dPropIVA` |
| `FACTURA_TASA_IVA` | `10` | `dTasaIVA` |

Un rechazo de `calcular_de` relacionado con emisor o actividad debe corregirse
con los valores registrados en Factura Segura, sin avanzar la numeración a mano.

## 24. Campos enviados a `calcular_de`

### 24.1 Identidad y numeración

| Campo | Fuente | Explicación |
|---|---|---|
| `iTipEmi` | Constante `1` | Emisión normal. |
| `iTiDE` | Constante `1` | Factura electrónica. |
| `dNumTim` | `FACTURA_TIMBRADO` | Timbrado del emisor. |
| `dFeIniT` | `FACTURA_TIMBRADO_FECHA_INICIO` | Inicio de vigencia. |
| `dEst` | `FACTURA_ESTABLECIMIENTO` | Establecimiento de tres dígitos. |
| `dPunExp` | `FACTURA_PUNTO_EXPEDICION` | Expedición de tres dígitos. |
| `dNumDoc` | `NumeroFiscalAsignado` | Número persistido de siete dígitos. |
| `dFeEmiDE` | Hora local de Django | Fecha/hora ISO sin microsegundos. |

### 24.2 Operación cambiaria

| Campo | Fuente | Explicación |
|---|---|---|
| `iTipTra` | Tipo de transacción | COMPRA=`6`, VENTA=`5`. |
| `iTImp` | `FACTURA_TIPO_IMPUESTO` | Régimen de impuesto TEST. |
| `cMoneOpe` | Constante `PYG` | Toda factura se expresa en guaraníes. |
| `dCondTiCam` | Constante `1` | Cambio global. |
| `dTiCam` | Constante `1` | PYG no necesita conversión. |

La conversión de la comisión se determina así:

1. Si la moneda destino es PYG, la tasa es `1`.
2. Si la moneda origen es PYG, se usa `1 / tasa_aplicada` porque la tasa de la
   operación representa origen → destino.
3. Si PYG no participa, se busca una `TasaReferencia` vigente directa,
   inversa o cruzada mediante una misma moneda base.
4. Si no existe referencia persistida, la factura no se emite y no se inventa
   una cotización.

No se consulta ExchangeRate-API durante la emisión: se utiliza únicamente una
referencia previamente validada y almacenada en la base de datos.

El snapshot conserva la evidencia:

| Campo interno | Significado |
|---|---|
| `importe_comision` | Comisión original en moneda destino. |
| `importe_comision_pyg` | Importe entero facturado en PYG, redondeado HALF_UP. |
| `tasa_conversion_pyg` | Cantidad de PYG por una unidad de moneda destino. |
| `fuente_conversion_pyg` | Operación original o proveedor de tasa persistida. |
| `fecha_conversion_pyg` | Momento de la operación o fecha de la referencia. |

### 24.3 Emisor

| Campo | Fuente |
|---|---|
| `dRucEm` | `FACTURA_SEGURA_RUC` |
| `dDVEmi` | `FACTURA_EMISOR_DV` |
| `iTipCont` | `FACTURA_EMISOR_TIPO_CONTRIBUYENTE` |
| `dNomEmi` | `FACTURA_EMISOR_NOMBRE` |
| `dDirEmi` | `FACTURA_EMISOR_DIRECCION` |
| `dNumCas` | `FACTURA_EMISOR_NUMERO_CASA` |
| `cDepEmi` | `FACTURA_EMISOR_DEPARTAMENTO_CODIGO` |
| `dDesDepEmi` | `FACTURA_EMISOR_DEPARTAMENTO` |
| `cCiuEmi` | `FACTURA_EMISOR_CIUDAD_CODIGO` |
| `dDesCiuEmi` | `FACTURA_EMISOR_CIUDAD` |
| `dTelEmi` | `FACTURA_EMISOR_TELEFONO` |
| `dEmailE` | `FACTURA_EMISOR_EMAIL` |
| `gActEco[0].cActEco` | `FACTURA_EMISOR_ACTIVIDAD_CODIGO` |
| `gActEco[0].dDesActEco` | `FACTURA_EMISOR_ACTIVIDAD_DESCRIPCION` |

### 24.4 Receptor

El receptor se obtiene del snapshot de la factura. `correo_facturacion` pasó a
formar parte del snapshot y es obligatorio.

Si `Cliente.documento` tiene formato `RUC-DV`, por ejemplo `1234567-8`:

| Campo | Valor |
|---|---|
| `iNatRec` | `1` contribuyente |
| `iTiOpe` | `1` B2B |
| `dRucRec` | Parte anterior al guion |
| `dDVRec` | Dígito posterior al guion |
| `iTipIDRec` | `0` |
| `dNumIDRec` | `0` |

Para otro documento alfanumérico válido:

| Campo | Valor |
|---|---|
| `iNatRec` | `2` no contribuyente |
| `iTiOpe` | `2` B2C |
| `dRucRec` / `dDVRec` | `0` |
| `iTipIDRec` | `1`, cédula TEST |
| `dNumIDRec` | Documento del cliente |

Campos comunes:

| Campo | Fuente |
|---|---|
| `cPaisRec` | Constante `PRY` |
| `iTiContRec` | FISICA=`1`, JURIDICA=`2` |
| `dNomRec` | `Cliente.nombre_razon_social` |
| `dEmailRec` | `Cliente.correo_facturacion` |
| `iIndPres` | Constante TEST `1` |

### 24.5 Pago de contado

`iCondOpe=1` indica contado y `gPaConEIni` contiene un pago por el importe de la
comisión:

| Campo | Efectivo | Electrónico |
|---|---:|---:|
| `iTiPago` | `1` | `3` |
| `dMonTiPag` | Comisión convertida a PYG | Comisión convertida a PYG |
| `cMoneTiPag` | `PYG` | `PYG` |
| `dTiCamTiPag` | `1` | `1` |
| `iDenTarj` | No enviado | `1` TEST |
| `iForProPa` | No enviado | `1` TEST |

### 24.6 Ítem

| Campo | Valor/fuente |
|---|---|
| `dCodInt` | `CAMBIO-<transaccion_id>` |
| `dDesProSer` | Servicio de cambio de divisas y número de operación |
| `cUniMed` | `77`, unidad |
| `dCantProSer` | `1` |
| `dPUniProSer` | Comisión |
| `dDescItem` | `0` |
| `dDescGloItem` | `0` |
| `dAntPreUniIt` | `0` |
| `dAntGloPreUniIt` | `0` |
| `iAfecIVA` | Configurable, predeterminado `1` |
| `dPropIVA` | Configurable, predeterminado `100` |
| `dTasaIVA` | Configurable, predeterminado `10` |

Los totales, bases e IVA calculado no se envían. `calcular_de` los incorpora al
DE completo.

### 24.7 Campos controlados por Factura Segura

| Campo | Valor inicial |
|---|---|
| `CDC` | `0` |
| `dCodSeg` | `0` |
| `dDVId` | `0` |
| `dSisFact` | `1` |
| `dInfAdic` | Referencia TEST de la transacción |

## 25. Extracción del DE calculado

El manual establece que `calcular_de` devuelve:

```json
{
  "code": 0,
  "results": [
    {"DE": {"...": "documento completo"}}
  ]
}
```

Por eso el contrato valida y devuelve exactamente:

```python
resultado.resultados[0]["DE"]
```

Si falta `results`, el primer elemento no es un objeto o `DE` no es un objeto
no vacío, se detiene la emisión antes de llamar a `generar_de`.

## 26. Numeración persistente

La migración `0003_rangonumeracionfiscal_numerofiscalasignado.py` crea:

- `RangoNumeracionFiscal`: identidad del timbrado, límites y siguiente número.
- `NumeroFiscalAsignado`: relación uno a uno entre Factura y número reservado.

La reserva usa `transaction.atomic()` y `select_for_update()`:

```text
Factura 1 -> 0000338
Factura 2 -> 0000339
...
Factura 12 -> 0000349
Factura 13 -> error de rango agotado
```

Reprocesar la misma factura reutiliza el mismo número. Un número reservado no se
devuelve al rango si el proveedor rechaza o queda indeterminado; debe conciliarse
o inutilizarse conforme al procedimiento fiscal.

Los modelos son visibles en Django Admin en modo lectura.

## 27. Activación y prueba actualizada

Configurar como mínimo en `.env`:

```env
FACTURA_SEGURA_TOKEN=TOKEN_TEST
FACTURA_SEGURA_RUC=2595733
FACTURACION_CONTRATO=facturacion.contracts.factura_segura_test.ContratoFacturaSeguraTest
```

El cliente de una operación debe tener:

```text
documento: 1234567-8, si es RUC; o documento alfanumérico válido
correo_facturacion: correo válido y no vacío
```

La operación debe:

- terminar `COMPLETADA`;
- tener comisión mayor a cero;
- tener una conversión a PYG disponible y persistida;
- usar método `EFECTIVO` o `ELECTRONICO`.

Aplicar migraciones y recrear el backend:

```bash
docker compose up -d --force-recreate web
docker compose exec web python manage.py migrate
```

Procesar una sola factura pendiente:

```bash
docker compose exec web python manage.py procesar_facturas --limite 1
```

También puede procesarse desde `GET /facturas/`: las filas pendientes muestran
el botón **Procesar factura** para asociaciones `RESPONSABLE` u `OPERADOR`. El
formulario realiza un `POST /facturas/<factura_id>/procesar/` con CSRF. La vista
valida nuevamente sesión, rol y asociación activa y ejecuta, en este orden:

1. construcción del DE desde el snapshot inmutable;
2. `calcular_de`;
3. validación y extracción del DE calculado;
4. `generar_de` con clave idempotente por transacción;
5. persistencia del intento, estado y CDC.

Una asociación `CONSULTA` puede leer la factura, pero no ve ni puede ejecutar
la emisión. Repetir el POST sobre una factura ya procesada no genera otro DE.

Después de recibir un CDC, tanto el listado como el detalle muestran
**Actualizar estado SIFEN**. El formulario ejecuta
`POST /facturas/<factura_id>/actualizar-estado-sifen/`; el navegador nunca
envía el CDC ni datos fiscales. El backend toma el CDC persistido, llama
`get_estado_sifen` y guarda por separado:

| Campo | Evidencia persistida |
|---|---|
| `estado_sifen` | Estado fiscal informado por SIFEN. |
| `descripcion_sifen` | Descripción devuelta, por ejemplo el rechazo 1261. |
| `error_sifen` | Detalle de error fiscal, si existe. |
| `fecha_sifen` | Fecha informada por el proveedor. |
| `consultada_sifen_en` | Momento local de la última consulta. |

Esta acción es de consulta: no ejecuta `calcular_de`, `generar_de`, no cambia
el CDC y no consume otro número del rango fiscal.

Consultar resultado sin exponer secretos:

```bash
docker compose exec web python manage.py shell -c "from facturacion.models import Factura; print(list(Factura.objects.order_by('-id').values('id','transaccion_id','estado','cdc','codigo_error')[:5]))"
```

Si queda `GENERADA`, esperar aproximadamente un minuto antes de consultar SIFEN
y luego usar `/facturas/` para abrir o descargar KuDE/XML.

## 28. Pruebas del contrato

`facturacion/test_contrato_fiscal.py` comprueba:

- campos confirmados del emisor;
- primer número `0000338`;
- reutilización del número en reconstrucciones;
- mapeo COMPRA=`6`;
- receptor RUC/DV;
- conversión de comisión extranjera y factura siempre en PYG;
- IVA TEST configurable;
- extracción exacta de `results[0]["DE"]`;
- rechazo de receptor sin correo;
- conversión cruzada mediante referencias persistidas.

Comando:

```bash
docker compose exec web python manage.py test facturacion --noinput
```

Evidencia al 30/10/2026:

```text
48 pruebas de facturación
48 aprobadas
0 fallos
0 errores
```

Regresión global posterior:

```text
566 pruebas del proyecto
571 aprobadas
0 fallos
0 errores
```

