# Documentación de conversaciones con IA — Sprint 4


**Integrante:** Elena Gisselle Ramirez Medina




### Pregunta 1

**Usuario:**
> ¿Qué datos mínimos necesita una Caja?

**IA:**
Se acordaron código, nombre, estado HABILITADA/DESHABILITADA y trazabilidad de creación y actualización. El código se normaliza a mayúsculas y se eliminan espacios externos. Es único en la base de datos. Código de hasta 30 caracteres y nombre de hasta 100 son decisiones de diseño, no campos exigidos literalmente por Jira.

### Pregunta 2

**Usuario:**
> ¿Basta con ocultar el botón de crear a los demás roles?

**IA:**
No. Las vistas y los servicios deben exigir ADMINISTRADOR efectivo. También se revisaron accesos directos y usuarios multirrol. Se mantuvo la prioridad de roles existente: administrador, analista, cajero y usuario.

### Pregunta 3

**Usuario:**
> ¿Cómo se habilita o deshabilita una caja de forma segura?

**IA:**
Mediante POST con CSRF, validación backend y una transacción que bloquea la fila de Caja con select_for_update(). No se implementó eliminación. El bloqueo se reutilizó en HU-39 para coordinar cambios de estado con aperturas.

### Pregunta 4

**Usuario:**
> ¿De dónde obtenemos el creador y las fechas?

**IA:**
La identidad y el username proceden del contexto autenticado de Keycloak; las fechas se generan en el servidor. No se aceptan estos datos desde campos del formulario. Se conserva el creador original y se registra el último actor; esto no equivale a un historial completo de auditoría.

### Pregunta 5

**Usuario:**
> ¿Cómo comprobamos errores, duplicados y registros parciales?

**IA:**
Se probaron formularios inválidos, códigos normalizados duplicados, restricciones de BD y fallos simulados durante la escritura. Los errores inesperados muestran mensajes controlados y las transacciones revierten las escrituras. HU-38 terminó con 30 pruebas de Caja y 233 de regresión aprobadas según el reporte del agente.



### Pregunta 6

**Usuario:**
> ¿Debemos guardar la apertura directamente dentro de Caja?

**IA:**
Se separaron Caja y PeriodoCaja. Caja conserva su habilitación; PeriodoCaja representa el período operativo y registra responsable y fecha de apertura. SaldoInicialCaja conserva un importe por moneda y período. ABIERTO/CERRADO se definieron como estados, pero el cierre quedó reservado para una HU posterior.

### Pregunta 7

**Usuario:**
> ¿Qué monedas debe incluir la apertura? ¿Se permiten todos los saldos en cero?

**IA:**
Se acordó exigir un importe explícito por cada moneda activa. Se permiten todos los importes en cero. Sin monedas activas se impide abrir y no se crea ningún registro. Se rechazan omisiones, duplicados y monedas inactivas. Estas precisiones son acuerdos del proyecto separados del texto general de la ERS.

### Pregunta 8

**Usuario:**
> ¿Qué precisión usamos para los importes?

**IA:**
DecimalField(18, 6), siguiendo la precisión existente en Operaciones. Se rechazan negativos, valores no finitos, exceso de decimales y valores fuera de capacidad, sin redondeo silencioso. La captura y confirmación muestran el importe completo; no se usa float para cálculos monetarios.

### Pregunta 9

**Usuario:**
> ¿Qué ocurre si cambian las monedas entre captura y confirmación?

**IA:**
El formulario incorpora un dato firmado con los pares (id, codigo) activos. El backend compara ese conjunto con el catálogo consultado dentro de la transacción. Si difiere, exige revisar el formulario actualizado sin guardar período ni saldos. Cambios de nombre o símbolo no invalidan la apertura.

### Pregunta 10

**Usuario:**
> ¿Hace falta bloquear toda la tabla de monedas?

**IA:**
Se eligió la alternativa menor: la consulta del catálogo dentro de la transacción es el instante de validación. Un cambio posterior no altera los saldos históricos ya validados. No se garantiza que el catálogo permanezca igual hasta el commit ni se bloquea toda la tabla.

### Pregunta 11

**Usuario:**
> ¿Cómo impedimos dos aperturas simultáneas?

**IA:**
La apertura usa transaction.atomic(), bloquea Caja y vuelve a validar habilitación y ausencia de período abierto. Una restricción condicional de unicidad garantiza un único período ABIERTO por Caja. Período y saldos se guardan juntos. Se probaron carreras reales con conexiones PostgreSQL independientes.

### Pregunta 12

**Usuario:**
> ¿Qué cajero puede abrir cada caja?

**IA:**
Se confirmó que el rol efectivo CAJERO puede abrir cualquier caja habilitada sin período abierto, sin asignación individual Cajero–Caja. ADMINISTRADOR o ANALISTA con un rol adicional CAJERO no actúan como cajero, conforme a la prioridad vigente. Esta política fue un acuerdo funcional explícito.

### Pregunta 13

**Usuario:**
> ¿Puede un administrador deshabilitar una caja que está abierta?

**IA:**
No. El cambio de estado adquiere el mismo bloqueo de Caja y rechaza la deshabilitación si existe un período abierto. No se implementaron arqueo ni cierre como parte de esta regla.

### Pregunta 14

**Usuario:**
> La validación funciona, pero la pantalla se refresca sin avisar. ¿Qué debe corregirse?

**IA:**
El QA manual detectó falta de mensajes visibles ante cambios de catálogo y deshabilitación de una caja abierta. Se corrigió la navegación para mostrar los avisos. El rechazo de deshabilitación pasó a POST → redirección → GET; el mensaje aparece una vez y desaparece con el temporizador existente de cinco segundos. Recargar no reenvía el formulario.

### Pregunta 15

**Usuario:**
> ¿Son necesarias tantas pruebas nuevas?

**IA:**
Se revisaron y consolidaron pruebas que podían compartir escenario, manteniendo cobertura de permisos, CSRF, importes, catálogo firmado, trazabilidad, restricciones, rollback y concurrencia. HU-39 quedó con 42 pruebas, además de las 30 de HU-38: 72 de Caja y 275 de regresión aprobadas.



### Pregunta 16

**Usuario:**
> ¿La ERS y Jira indican exactamente qué variación debemos avisar?

**IA:**
Exigen detectar variaciones según un criterio configurado, identificar moneda o tasa, enviar correo, no avisar si no corresponde y registrar fallos. Las políticas concretas se definieron con la usuaria: tasas comerciales, compra y venta, subidas y bajadas, umbral global inicial del 3 % configurable por administrador y usuarios activos con correo verificado.

### Pregunta 17

**Usuario:**
> ¿Comparamos contra la tasa anterior o acumulamos cambios?

**IA:**
Se decidió acumular desde la base de la última notificación exitosa, por destinatario, par y lado. La variación se calcula con Decimal: abs(tasa_actual - base) / base × 100, para una base positiva. El límite es inclusivo: alcanzar el 3 % cumple. La primera tasa no genera correo; la inicialización sin una notificación previa utiliza la tasa anterior vigente disponible.

### Pregunta 18

**Usuario:**
> ¿Cuándo avanzan las bases de comparación?

**IA:**
Un envío exitoso avanza únicamente los lados incluidos en el correo. Los cambios inferiores al umbral conservan su base para acumularse. Si el envío falla, las bases no avanzan. Cambiar el umbral por sí solo no envía avisos retrospectivos.

### Pregunta 19

**Usuario:**
> ¿Necesitamos revisar las tasas cada hora?

**IA:**
No para el alcance acordado. La detección ocurre al guardar una actualización comercial, después de confirmar la escritura en BD. No se añadieron scheduler, Celery ni consultas periódicas al proveedor. Las tasas externas de referencia no generan estas notificaciones.

### Pregunta 20

**Usuario:**
> ¿Agrupamos cambios y hacemos reintentos?

**IA:**
Compra y venta relevantes de una misma actualización se incluyen en un correo individual por destinatario. No hay ventana temporal para agrupar guardados separados. Los fallos se registran sin reintentos automáticos. Una actualización posterior puede volver a cumplir el criterio porque la base del envío fallido se conserva.

### Pregunta 21

**Usuario:**
> ¿De dónde obtenemos los correos?

**IA:**
De Keycloak, recorriendo los usuarios con paginación y seleccionando cuentas activas con correo verificado y válido. No se crean usuarios de negocio Django ni se limita el envío a usuarios asociados con clientes. Cada destinatario recibe su propio correo.

## Mailpit y diagnóstico del envío

### Pregunta 22

**Usuario:**
> Nosotros usamos Mailpit. ¿Para qué sirve configurar MAILERS en Django?

**IA:**
Django configura cómo enviar; Mailpit recibe y permite inspeccionar los mensajes en desarrollo. Se verificó SMTP hacia mailpit:1025 desde Docker, sin autenticación, TLS ni SSL, con timeout de ocho segundos. Producción conserva su configuración por variables de entorno. Las pruebas automatizadas usan correo en memoria o mocks.

### Pregunta 23

**Usuario:**
> ¿Cómo probamos el umbral y la acumulación desde la interfaz?

**IA:**
Con un par nuevo: compra 100 y venta 200 no envían aviso inicial. Compra 101 y luego 102 tampoco. Compra 103 y venta 194 cumplen +3 % y −3 % respecto de las bases y se agrupan por destinatario. La usuaria confirmó que estos escenarios funcionaban y los correos llegaban a Mailpit.

### Pregunta 24

**Usuario:**
> Con Mailpit detenido no podía guardar y, al restaurarlo, llegaron correos. ¿Eran reintentos?

**IA:**
La investigación del agente identificó solicitudes de guardado acumuladas mientras la respuesta HTTP esperaba el envío síncrono. Los eventos 8–15 registraron fallos; los seis correos recibidos correspondían al evento 18, creado antes de restaurar Mailpit y procesado después. No se identificó un mecanismo de reintento automático. Los logs no permitían atribuir cada solicitud a una acción concreta.

### Pregunta 25

**Usuario:**
> ¿Cómo se corrigió sin añadir un sistema complejo de tareas?

**IA:**
Se conservó el envío síncrono con timeout. El POST responde 201 con advertencia si falla SMTP y la tasa se conserva. Ante fallo de conexión se registran resultados fallidos sin repetir conexiones para cada destinatario; ante un fallo individual se continúa con los demás. El frontend desactiva Guardar mientras espera y bloquea solicitudes repetidas por clic o Enter.

### Pregunta 26

**Usuario:**
> ¿Qué comprobamos después de esa corrección?

**IA:**
Se repitió el QA: detener Mailpit, guardar una variación relevante, esperar la advertencia y comprobar la tasa; restaurar Mailpit solo después de terminar el POST, verificar ausencia de nuevos correos y finalmente guardar otra variación relevante. La usuaria confirmó que todo funcionaba. La consulta final de BD para verificar una sola versión y bases sin avanzar se había solicitado al agente, pero su resultado no está incluido en este registro.

### Pregunta 27

**Usuario:**
> ¿El estado ENVIADO garantiza que el usuario leyó o recibió realmente el correo?

**IA:**
No. Representa aceptación por el backend de correo. En desarrollo Mailpit captura mensajes, sin entregarlos a Gmail. SMTP y BD no garantizan exactamente una entrega ante interrupciones. Esta limitación se dejó explícita sin introducir una arquitectura distribuida fuera del alcance.

## Pruebas, Git y cierre

### Pregunta 28

**Usuario:**
> ¿Cómo documentamos y seleccionamos las pruebas?

**IA:**
Con nombres descriptivos y docstrings que expliquen condición, regla y resultado esperado. Se mantuvieron pruebas relevantes de negocio, seguridad, persistencia, fallos y concurrencia; se consolidaron casos redundantes. El QA manual se registró por separado de los tests automatizados.

### Pregunta 29

**Usuario:**
> ¿Qué resultados de verificación tenemos al cerrar esta documentación?

**IA:**
Según los reportes del agente: HU-38, 30 pruebas de Caja y 233 de regresión; HU-39, 72 de Caja y 275 de regresión; HU-20 final tras corregir SMTP/frontend, 58 de Tasas y 298 de regresión. En HU-20 también se habían ejecutado check sin incidencias y makemigrations --check --dry-run sin cambios; la corrección posterior no reportó cambios de modelos. git diff --check pasó tras la corrección.

### Pregunta 30

**Usuario:**
> ¿Qué ramas, migraciones y commits quedaron?

**IA:**
HU-38: feature/hu-38-crear-caja, migración 0001, commit 9b512ff y PR #28 integrado. HU-39: feature/hu-39-abrir-caja, migración 0002, commit b153c57 y PR #29 integrado en develop ea0ad52. HU-20: feature/hu-20-recibir-notificaciones-de-tasas desde ea0ad52, migración nueva 0004 de Tasas. Al preparar este documento, el commit y PR de HU-20 todavía no estaban confirmados.

### Pregunta 31

**Usuario:**
> ¿Qué documentación y pendientes quedan?

**IA:**
Esta documentación de IA reúne la participación de Elena en HU-38, HU-39 y HU-20. No acredita que todo el Sprint 4 del equipo esté cerrado. La actualización de Jira, verificación en VM/producción, PR de HU-20, tag del sprint y planificación del siguiente sprint no se declaran realizados. Los permisos de configuración tienen cobertura automatizada; su QA manual específico no fue confirmado separadamente en la conversación.
