# HU-29 / HU-30 - Facturas disponibles en la web

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
6. Las facturas generadas se consultan en Mis facturas y permiten visualizar
   el PDF y descargar PDF/XML desde la web. No se envían correos.

Los bloqueos se liberan antes de la API. Los fallos de facturación no modifican ni eliminan
transacciones, movimientos, pagos ni facturas. Errores inesperados se registran
con códigos controlados; no se publican respuestas técnicas ni secretos.

## Consulta y permisos

En `/facturas/` (Mis facturas del menú de usuario) se muestran únicamente facturas
de clientes con asociación activa a la identidad OIDC. Se revalida en cada detalle,
visualización y descarga; no se confía en IDs aportados por el navegador.

- RESPONSABLE, OPERADOR y CONSULTA: consulta, visualización y descarga de facturas de clientes asociados.
- Sin asociación activa o sin sesión: no accede al comprobante.

El alcance acordado el 30/10/2026 por indicación de Axel y confirmado por Elías
reemplaza el envío por correo por disponibilidad dentro de la web. Se retiraron
las rutas de envío y configuración, formularios, botones y llamadas SMTP.
La HU-30 original y la guía incluían correo: este documento registra el cambio
de alcance y no lo presenta como cumplimiento literal de aquellos criterios.
Corresponde reflejar el acuerdo en Jira y los criterios del sprint.

PDF/XML se obtienen del adaptador existente y se sirven con permisos y sin caché
pública. No se almacenan archivos en MEDIA ni se generan comprobantes ficticios.
La disponibilidad de descarga depende del proveedor; los metadatos permanecen
consultables aunque éste falle. Falta validar visualmente un KuDE real.

## Compatibilidad con la versión anterior

Las migraciones ya publicadas no se reescriben. Se conservan el modelo histórico
EnvioFactura y el campo correo_facturacion para no eliminar datos existentes.
No tienen pantallas, formularios, rutas, registro en el admin de envíos ni
servicios activos en facturación. El procesador no crea ni reintenta envíos.
No se modifica el correo utilizado por otros módulos del proyecto.

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

El ajuste a facturas web no requiere nuevas migraciones. Se mantiene el esquema
publicado y las restricciones de unicidad y estados de Factura. Las pruebas usan una base aislada y proveedores
simulados; no envían correos reales ni emiten documentos externos.

El cierre de las HUs requiere además completar el contrato, consulta/persistencia
de estados fiscales, programar el procesador, probar emisión, consulta y descargas reales en TEST y
realizar QA visual del flujo con los roles acordados.
