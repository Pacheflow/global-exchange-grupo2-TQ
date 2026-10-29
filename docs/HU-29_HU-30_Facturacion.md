# HU-29 / HU-30 - Facturas y envío por correo

## Estado de esta entrega

Base funcional implementada sobre `feature/hu-28-integracion-factura-segura`
(commit base `38347f6`). **No es una integración fiscal terminada ni validada
con el proveedor real.** Falta el contrato fiscal del emisor, credenciales TEST,
interpretación de estados SIFEN y validación de los comprobantes reales.

## Flujo implementado

1. Los servicios existentes finalizan la transacción y guardan `OperacionCompletada`
   tanto para operaciones online como para efectivo presencial.
2. Después del commit se prepara una `Factura` PENDIENTE con snapshot de datos
   comerciales. Su relación única con la transacción evita duplicados.
3. `procesar_facturas` recupera eventos no preparados e intenta emitir pendientes.
   Sin `FACTURACION_CONTRATO`, registra `CONTRATO_FISCAL_PENDIENTE`, conserva
   PENDIENTE y no contacta a la API. El comando requiere ejecución por un scheduler
   para funcionar automáticamente; esta entrega no instala uno.
4. Con contrato explícito, construye el DE, llama a `calcular_de`, valida/extrae el
   DE calculado mediante ese contrato y usa `generar_documento_una_vez` de Guillermo.
   La clave es `factura:transaccion:<id>:v1`; no se cambia para sortear un error.
5. Guarda el intento técnico, CDC, estado de emisión y fecha. `GENERADA` significa
   respuesta válida del proveedor; **no significa aprobación fiscal SIFEN**.
6. El procesador intenta el primer correo de las facturas generadas. Guarda un
   `EnvioFactura` antes de descargar el PDF y contactar al servicio de correo.

Los bloqueos se liberan antes de API/SMTP. Los fallos no modifican ni eliminan
transacciones, movimientos, pagos ni facturas. Errores inesperados se registran
con códigos controlados; no se publican respuestas técnicas ni secretos.

## Consulta y permisos

En `/facturas/` (Mis facturas del menú de usuario) se muestran únicamente facturas
de clientes con asociación activa a la identidad OIDC. Se revalida en cada detalle,
visualización, descarga y envío; no se confía en IDs ni destinatarios del POST.

- RESPONSABLE: consulta, descarga, envío y configuración del correo del cliente.
- OPERADOR: consulta, descarga y envío al correo ya configurado.
- CONSULTA: consulta y descarga.
- Sin asociación activa o sin sesión: no accede al comprobante.

Se conserva el correo en `Cliente.correo_facturacion`. Inicialmente está vacío:
el responsable lo configura desde Mis facturas. No se infiere desde un usuario
de Keycloak, porque un cliente puede tener varias identidades asociadas. Este
criterio de destinatario y permisos debe revisarse con el equipo.

PDF/XML se obtienen del adaptador existente y se sirven con permisos y sin caché
pública. No se almacenan archivos en MEDIA ni se generan comprobantes ficticios.
La disponibilidad de descarga depende del proveedor; los metadatos permanecen
consultables aunque éste falle. Falta validar visualmente un KuDE real.

## Correo e idempotencia

Se utiliza `mailers.create_connection("default")`, igual que las notificaciones
de tasas. En desarrollo Compose usa Mailpit; no se cambió la configuración SMTP.
El mensaje identifica la operación y adjunta su PDF.

Un envío ENVIADO o EN_PROCESO se reutiliza. Un ERROR permite un nuevo intento
mediante POST con CSRF y autorización; el intento anterior permanece. Nunca se
vuelve a emitir la factura para reintentar correo. SMTP no garantiza entrega
exactamente una vez: si aceptó el mensaje pero la respuesta se perdió, un reintento
puede repetir el correo. Un proceso interrumpido en EN_PROCESO requiere revisión,
no se libera por tiempo transcurrido.

## Contrato fiscal pendiente

`FACTURACION_CONTRATO` es una ruta de clase Python configurada por el servidor,
nunca recibida del navegador. La clase necesita estos métodos:

```python
class ContratoFiscalConfirmado:
    def construir_de(self, datos_operacion):
        # Validar/mapear usando el esquema real del emisor.
        ...

    def extraer_de_calculado(self, resultado):
        # Validar los resultados de calcular_de y devolver el DE real.
        ...
```

Este ejemplo define una interfaz, **no una implementación usable**. No se incluye
un contrato fiscal de producción ni se asignan IVA, concepto o monto facturable.
Los mocks en tests no son documentos reales y no deben usarse con el proveedor.

Solicitar al equipo/proveedor:

- Ejemplo sanitizado de DE y respuesta `calcular_de`.
- Concepto e importe facturable para COMPRA y VENTA; tratamiento de comisión.
- Datos del emisor, timbrado, establecimiento, punto y numeración.
- Interpretación de `estado_inu`, `estado_can`, `estado_sifen` y criterio de factura válida.
- Credenciales TEST, rutas de descarga confirmadas y ejemplos de KuDE/XML.

Ante timeout de emisión se conserva INDETERMINADA, sin reintento automático.
ERROR tampoco se reemite automáticamente. EN_PROCESO abandonado, ERROR e
INDETERMINADA requieren conciliación administrativa con la evidencia del ledger;
esta entrega no implementa esa conciliación ni una interfaz para reemitir.

## Instalación y validación

```powershell
python manage.py migrate
python manage.py check
python manage.py test facturacion --noinput
python manage.py test --noinput
```

Para procesar una tanda una vez configurado el contrato fiscal:

```powershell
python manage.py procesar_facturas --limite 100
```

Migraciones nuevas: correo opcional del cliente, Factura y EnvioFactura con
restricciones de unicidad y estados. Las pruebas usan una base aislada y proveedores
simulados; no envían correos reales ni emiten documentos externos.

El cierre de las HUs requiere además completar el contrato, consulta/persistencia
de estados fiscales, programar el procesador, probar el circuito real en TEST y
realizar QA visual del flujo con los roles acordados.
