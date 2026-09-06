Quiero que completes ESTE PROYECTO ACTUAL de Figma Make hasta convertirlo en el PROTOTIPO VISUAL COMPLETO, NAVEGABLE Y COHERENTE de Global Exchange.

IMPORTANTE:
NO empieces de cero.
NO reconstruyas el proyecto.
NO rehagas las pantallas que ya están correctamente diseñadas.
NO cambies innecesariamente componentes existentes.

Quiero que trabajes DE FORMA INCREMENTAL sobre lo que ya existe.

============================================================
REGLA CRÍTICA — CONSERVAR TODO LO QUE YA ESTÁ BIEN
============================================================

Antes de crear o modificar cualquier cosa, revisá si ya existe.

Si algo:

- ya existe y funciona correctamente → CONSERVARLO.
- ya existe y visualmente está correcto → NO MODIFICARLO.
- existe pero está incompleto → COMPLETARLO.
- existe pero tiene un error → CORREGIR ÚNICAMENTE ESE ERROR.
- no existe → CREARLO.
- existe duplicado → reutilizar el existente y evitar crear otro.

NO quiero una reconstrucción completa del proyecto.

NO quiero que rediseñes la Landing.

NO quiero que cambies el Navbar porque ya está trabajado.

NO quiero que cambies el Footer porque ya está trabajado.

NO quiero que cambies las animaciones existentes porque sí.

NO quiero cambiar colores, tipografías, gráficos, espaciados,
componentes o layouts que ya estén correctamente implementados.

Si para agregar una nueva pantalla necesitás reutilizar un
componente existente, REUTILIZALO.

La prioridad es:

EXISTENTE Y CORRECTO
        ↓
CONSERVAR

EXISTENTE E INCOMPLETO
        ↓
COMPLETAR

EXISTENTE CON ERROR
        ↓
CORREGIR

NO EXISTE
        ↓
CREAR

============================================================
OBJETIVO FINAL
============================================================

Quiero que este proyecto pueda recorrerse visualmente como una
aplicación completa de Global Exchange.

Debe ser posible:

Landing
→ acceso
→ dashboard
→ módulo
→ submódulo
→ detalle
→ acción
→ confirmación
→ resultado
→ volver

Y esto debe poder hacerse para los diferentes roles del sistema.

NO quiero botones muertos.

NO quiero enlaces sin destino.

NO quiero opciones de menú que no tengan una pantalla.

NO quiero formularios sin estados.

NO quiero pantallas vacías cuando una funcionalidad está
representada en el menú.

============================================================
REGLA SOBRE BACKEND
============================================================

ESTE PROYECTO ES ÚNICAMENTE EL PROTOTIPO VISUAL.

NO implementar:

- Django.
- PostgreSQL.
- Keycloak real.
- APIs reales.
- autenticación real.
- autorización real.
- servicios externos reales.

Los datos pueden continuar siendo MOCK.

Las interacciones deben funcionar dentro del prototipo.

La futura arquitectura será:

Figma / React visual
        ↓
Django
        ↓
Keycloak
        ↓
Backend / APIs
        ↓
PostgreSQL

Por lo tanto, NO intentes reemplazar ni simular esta arquitectura.

============================================================
1. IDENTIDAD VISUAL
============================================================

Mantener EXACTAMENTE la identidad visual actual.

Conservar:

- modo oscuro;
- paleta actual;
- tipografías actuales;
- Fraunces;
- DM Sans;
- JetBrains Mono;
- iconos SVG lineales;
- estilo vintage moderno;
- estilo profesional;
- cards;
- tablas;
- botones;
- gráficos;
- animaciones;
- transiciones;
- espaciado;
- responsive.

Las nuevas pantallas deben parecer parte de la misma aplicación.

NO crear un diseño diferente para cada módulo.

============================================================
2. DESIGN SYSTEM
============================================================

Si ya existen Foundations y Components correctamente definidos,
reutilizarlos.

Solo completar lo que sea necesario.

Asegurar que existan componentes reutilizables para:

- Navbar;
- Sidebar;
- navegación móvil;
- selector de cliente;
- menú de usuario;
- botones;
- botones destructivos;
- inputs;
- selects;
- búsqueda;
- checkbox;
- radios;
- selección de fechas;
- filtros;
- cards;
- KPI;
- tablas;
- paginación;
- badges;
- gráficos;
- modales;
- drawers;
- confirmaciones;
- toast;
- alertas;
- skeletons;
- empty states;
- errores;
- estados 403;
- estados 404;
- sesión vencida.

No duplicar componentes que ya existen.

============================================================
3. ESTADOS DE COMPONENTES
============================================================

Todo componente interactivo nuevo debe considerar cuando
corresponda:

- Default;
- Hover;
- Focus;
- Pressed;
- Disabled;
- Loading;
- Error;
- Success.

No hace falta modificar componentes existentes si ya tienen
estos estados correctamente implementados.

============================================================
4. ROLES
============================================================

Los roles reales del sistema son:

- ADMINISTRADOR
- ANALISTA_CAMBIARIO
- CAJERO
- USUARIO

IMPORTANTE:

NO existe un rol llamado "Cliente".

Un USUARIO puede estar asociado a uno o varios Clientes.

El Cliente es el contexto en cuyo nombre el usuario puede operar.

Por eso utilizar:

"Panel de usuario"

y cuando corresponda:

"Cliente activo: KNG S.A."

y no:

"Rol: Cliente"

El selector de roles DEMO puede continuar existiendo dentro
de este prototipo para poder visualizar las diferentes
interfaces.

Esto NO representa la autenticación real.

============================================================
5. LANDING
============================================================

CONSERVAR la Landing actual si ya está correctamente diseñada.

No rediseñarla.

Debe mantener:

- Hero;
- Market Board;
- cotizaciones;
- gráficos;
- conversor;
- cómo funciona;
- beneficios;
- seguridad;
- monedas;
- Footer;
- animaciones.

Solo corregir información si es necesario para que los mocks
no se presenten como información real.

Cuando corresponda utilizar:

"Datos de demostración"

"Última actualización de prueba"

"En desarrollo"

NO afirmar que los valores mock son datos en tiempo real.

============================================================
6. HISTÓRICO PÚBLICO DE TASAS
============================================================

Si esta pantalla todavía no existe, CREARLA.

Debe incluir:

- moneda/par;
- hoy;
- 7 días;
- 30 días;
- 90 días;
- año;
- rango personalizado;
- gráfico;
- compra;
- venta;
- fuente;
- fecha;
- hora;
- estado vigente/desactualizado;
- sin información;
- servicio no disponible.

Utilizar MOCK.

============================================================
7. CONVERSOR
============================================================

CONSERVAR el conversor actual si ya está correcto.

Completar solamente lo que falte.

Debe permitir:

- moneda origen;
- moneda destino;
- monto;
- invertir monedas;
- resultado;
- tasa utilizada;
- tipo de tasa;
- fecha/hora;
- aviso de simulación.

La simulación NO debe:

- crear transacciones;
- reservar tasas;
- generar pagos;
- generar facturas.

============================================================
8. KEYCLOAK / IDENTIDAD
============================================================

Representar visualmente el flujo de identidad, sin implementar
Keycloak real.

Si ya existe un login visual correcto, conservarlo.

Cuando corresponda, representar:

- continuar al acceso seguro;
- login;
- registro;
- verificación de correo;
- reenvío;
- recuperación;
- acceso rechazado;
- cuenta no verificada;
- enlace vencido;
- Keycloak no disponible;
- sesión expirada;
- logout.

El login debe entenderse visualmente como parte del flujo
de identidad externo.

============================================================
9. APLICACIÓN AUTENTICADA
============================================================

Todos los dashboards autenticados deben compartir:

- usuario;
- email;
- rol;
- cliente activo;
- selector de cliente;
- logout;
- mensajes;
- acceso denegado.

Representar:

CASO 1:
Usuario con un cliente.

CASO 2:
Usuario con varios clientes.

CASO 3:
Usuario sin clientes.

En el caso sin cliente:

puede consultar tasas y utilizar el conversor,

pero no debe poder comprar ni vender.

============================================================
10. CRUD DE MONEDAS — SPRINT 2
============================================================

ESTA ES UNA PRIORIDAD.

Crear o completar las vistas necesarias para:

- listado;
- búsqueda;
- filtros;
- detalle;
- crear;
- editar;
- activar/desactivar;
- confirmación;
- éxito;
- error;
- estado vacío.

Campos:

- código;
- nombre;
- símbolo;
- estado.

Flujos:

Monedas
→ listado
→ Nueva moneda
→ formulario
→ guardar
→ confirmación
→ listado

Y:

Monedas
→ listado
→ detalle
→ editar
→ guardar
→ confirmación

Una moneda inactiva no debe aparecer visualmente como opción
para nuevas operaciones, pero debe permanecer visible en
históricos.

============================================================
11. CRUD DE COTIZACIONES — SPRINT 2
============================================================

Crear o completar:

- listado;
- búsqueda;
- filtros;
- detalle;
- crear;
- editar;
- confirmación;
- histórico;
- estados.

Mostrar:

- moneda/par;
- compra;
- venta;
- variación;
- fecha;
- hora;
- estado.

IMPORTANTE:

SUBE:
↑ verde

BAJA:
↓ rojo

SIN CAMBIO:
= neutro

Utilizar iconos SVG profesionales.

NO utilizar emojis.

Mantener los gráficos existentes.

============================================================
12. VISUALIZACIÓN DE TASAS — SPRINT 2
============================================================

Crear/completar una pantalla de tasas.

Diferenciar claramente:

- tasa externa de referencia;
- tasa comercial de compra;
- tasa comercial de venta.

Mostrar:

- par;
- tipo;
- fuente;
- fecha;
- hora;
- vigencia;
- estado;
- desactualizada.

NO permitir editar manualmente la tasa externa de referencia.

Utilizar MOCK.

============================================================
13. ADMINISTRACIÓN DE TASAS
============================================================

Si ya existe, conservarla.

Si falta, agregarla.

Para usuario autorizado:

- listado;
- editar compra;
- editar venta;
- validar valores > 0;
- comparar tasa anterior;
- confirmar;
- histórico;
- usuario responsable;
- fecha/hora;
- cancelar.

Representar:

- éxito;
- error;
- acceso denegado.

============================================================
14. CRUD DE MEDIOS DE PAGO — SPRINT 2
============================================================

Crear/completar:

- listado;
- agregar;
- detalle;
- editar;
- activar/desactivar;
- eliminar cuando corresponda;
- confirmación;
- éxito;
- error;
- estado vacío.

Campos:

- nombre;
- tipo;
- estado.

Flujos:

Medios de pago
→ agregar
→ formulario
→ guardar
→ confirmación

Y:

Medios de pago
→ detalle
→ editar
→ guardar

Y:

Medios de pago
→ desactivar
→ confirmación.

Un método deshabilitado no debe aparecer para nuevas
operaciones, pero debe permanecer en históricos.

============================================================
15. PANEL DE USUARIO
============================================================

Revisar el dashboard actual.

NO rehacerlo si está correcto.

Completar las vistas faltantes.

Si existen:

- Operaciones;
- Cotizaciones;
- Conversor;
- Historial;
- Perfil;

cada una debe tener su pantalla.

============================================================
16. OPERACIONES
============================================================

Si ya existe parcialmente, completar.

Representar:

Nueva compra
Nueva venta

Flujo:

Datos
→ cotización
→ resumen
→ confirmación
→ transacción pendiente
→ pago
→ completada
→ factura

Campos:

- cliente activo;
- comprar/vender;
- moneda origen;
- moneda destino;
- monto;
- tasa;
- importe;
- comisión;
- medio de pago;
- resumen.

Estados de transacción:

- Pendiente;
- Completada;
- Cancelada;
- Anulada.

NO utilizar "COMPLETADA" como estado de transacción.

============================================================
17. DETALLE DE TRANSACCIÓN
============================================================

Crear/completar:

- ID;
- usuario;
- cliente;
- compra/venta;
- monedas;
- monto origen;
- monto destino;
- tasa;
- fecha/hora;
- estado;
- pago;
- factura;
- historial.

============================================================
18. CANCELACIÓN Y ANULACIÓN
============================================================

Representar dos flujos diferentes.

CANCELAR:

solo transacción pendiente.

ANULAR:

transacción completada,
con permiso,
motivo obligatorio.

Ambos:

→ confirmación
→ resultado

Nunca eliminar visualmente una transacción del historial.

============================================================
19. PAGOS
============================================================

Crear/completar visualmente:

- métodos habilitados;
- selección;
- cambio;
- procesando;
- aprobado;
- rechazado;
- error;
- reintento;
- referencia externa;
- prevención de doble envío.

NO mencionar proveedores concretos como definitivos.

Utilizar nombres genéricos.

============================================================
20. FACTURACIÓN
============================================================

Crear/completar:

- generación;
- factura disponible;
- detalle;
- descargar;
- enviar;
- reintentar;
- error;
- anulación;
- motivo;
- factura anulada.

Si falla la facturación:

la transacción no debe desaparecer.

============================================================
21. PANEL ADMINISTRADOR
============================================================

Revisar el dashboard existente.

Conservar lo que ya esté correcto.

Completar las vistas necesarias para:

- usuarios;
- clientes;
- monedas;
- cotizaciones;
- tasas;
- medios de pago;
- transacciones;
- facturación;
- cajas;
- reportes.

Solo cuando correspondan al alcance actual.

============================================================
22. USUARIOS Y ACCESOS
============================================================

Crear/completar:

- listado;
- búsqueda;
- filtros;
- detalle;
- crear;
- editar;
- asignar roles;
- habilitar/deshabilitar;
- confirmación;
- éxito;
- error;
- acceso denegado.

Campos:

- username;
- nombre;
- apellido;
- email;
- contraseña temporal;
- estado;
- roles.

La matriz visual de permisos NO debe presentarse como
contrato funcional definitivo.

============================================================
23. CLIENTES
============================================================

Crear/completar:

- listado;
- búsqueda;
- alta;
- detalle;
- edición;
- segmentación;
- baja lógica;
- usuarios asociados;
- crear asociación;
- modificar asociación;
- quitar asociación;
- seleccionar cliente;
- cambiar cliente;
- deseleccionar.

Campos:

- nombre/razón social;
- persona física/jurídica;
- documento;
- categoría;
- estado;
- fecha de registro.

Categorías:

- Minorista;
- Corporativo;
- VIP.

============================================================
24. PANEL ANALISTA
============================================================

Completar las vistas faltantes del Analista.

Priorizar cuando correspondan:

- cotizaciones;
- tasas;
- históricos;
- análisis;
- reportes;
- ganancias.

No inventar módulos ajenos al proyecto.

============================================================
25. GANANCIAS Y REPORTES
============================================================

Crear/completar:

Ganancias:

- global;
- por moneda;
- período;
- comparación;
- tabla;
- gráficos;
- sin datos.

Reportes:

- período;
- vista previa;
- ganancias;
- desglose;
- generar;
- descargar;
- error;
- acceso restringido.

============================================================
26. HISTORIAL
============================================================

Crear/completar:

- tabla;
- filtros;
- fecha;
- cliente;
- moneda;
- tipo;
- estado;
- búsqueda;
- detalle;
- exportar PDF;
- exportar Excel;
- sin resultados;
- error.

============================================================
27. PANEL CAJERO
============================================================

Completar las vistas correspondientes al Cajero.

NO agregar "Transferencias".

NO agregar "Control de billetes".

Las funcionalidades de caja deben centrarse en:

- operaciones;
- caja;
- apertura;
- cierre;
- arqueo;
- movimientos;
- historial.

============================================================
28. CAJAS
============================================================

Administrador:

- listado;
- crear;
- editar;
- habilitar/deshabilitar;
- detalle;
- historial.

============================================================
29. APERTURA DE CAJA
============================================================

Crear/completar:

- caja;
- responsable;
- fecha/hora;
- saldos iniciales por moneda;
- validación;
- caja deshabilitada;
- caja ya abierta;
- confirmación.

============================================================
30. CAJA ABIERTA
============================================================

Mostrar:

- estado;
- responsable;
- apertura;
- saldos por moneda;
- movimientos recientes;
- ingreso;
- egreso;
- arqueo;
- cierre.

============================================================
31. MOVIMIENTOS DE CAJA
============================================================

Representar:

- ingreso/egreso;
- moneda;
- monto;
- motivo;
- responsable;
- fecha/hora;
- fondos insuficientes;
- caja cerrada.

============================================================
32. ARQUEO
============================================================

Por moneda:

- saldo teórico;
- saldo físico;
- diferencia;
- sobrante;
- faltante;
- sin diferencia;
- observación;
- responsable;
- fecha/hora.

============================================================
33. CIERRE DE CAJA
============================================================

Mostrar:

- resultado arqueo;
- saldo teórico;
- saldo físico;
- diferencias;
- confirmación;
- cierre exitoso;
- bloqueo de nuevos movimientos.

============================================================
34. HISTORIAL DE CAJA
============================================================

Mostrar:

- aperturas;
- movimientos;
- arqueos;
- cierres;
- diferencias;
- usuario;
- fecha;
- hora;
- filtros.

============================================================
35. ALERTAS DE TASAS
============================================================

NO crear un inbox interno de notificaciones si no existe.

Representar preferentemente:

"Configuración de alertas"

con:

- moneda/par;
- criterio/umbral;
- activar/desactivar;
- último envío;
- error de entrega.

La notificación debe entenderse como correo.

============================================================
36. AUDITORÍA
============================================================

Si ya existe una pantalla de auditoría, conservarla.

Si no existe, puede crearse como propuesta visual administrativa,
pero debe quedar claramente separada de las funcionalidades
confirmadas.

Mostrar:

- usuario;
- acción;
- entidad;
- ID;
- fecha/hora;
- detalle;
- filtros;
- acceso restringido.

============================================================
37. FUNCIONALIDADES FUERA DE ALCANCE
============================================================

NO agregar al flujo principal:

- Transferencias entre cajas;
- Control de billetes;
- Transferencias bancarias automáticas;
- movimientos reales sobre billeteras;
- sucursales múltiples;
- contabilidad;
- nómina;
- criptomonedas;
- trading;
- inversiones;
- aplicación móvil nativa.

Si ya existen frames relacionados, moverlos o mantenerlos
separados como:

"Fuera de alcance"

sin conectarlos al flujo principal.

============================================================
38. TERMINAL DE AUTOSERVICIO
============================================================

La guía académica contempla esta funcionalidad posteriormente.

Si se crea, mantenerla separada como:

"Propuesta académica — pendiente de confirmación"

NO mezclarla con el flujo oficial.

Puede incluir:

- inicio;
- compra/venta;
- moneda;
- monto;
- cotización;
- confirmación;
- simulación de efectivo;
- resultado;
- comprobante.

============================================================
39. NAVEGACIÓN
============================================================

TODOS los botones importantes deben funcionar.

Ejemplos:

Ver
→ detalle

Editar
→ edición

Eliminar
→ confirmación

Guardar
→ éxito

Cancelar
→ volver

Volver
→ pantalla anterior

Confirmar
→ resultado

Cerrar
→ cerrar modal

No dejar botones muertos.

============================================================
40. NAVBAR
============================================================

NO modificarlo salvo que sea estrictamente necesario.

Debe conservar:

- un único elemento activo;
- navegación correcta;
- diseño actual;
- animaciones actuales.

============================================================
41. FOOTER
============================================================

NO modificarlo salvo que sea estrictamente necesario.

Debe conservar:

- scroll suave;
- navegación a secciones;
- ausencia de estado activo permanente.

============================================================
42. FORMULARIOS
============================================================

Todos los formularios nuevos deben tener:

- vacío;
- escribiendo;
- válido;
- error;
- loading;
- enviado;
- éxito.

============================================================
43. TABLAS
============================================================

Las nuevas tablas deben tener cuando corresponda:

- búsqueda;
- filtros;
- ordenamiento;
- selección;
- detalle;
- edición;
- acciones;
- paginación;
- estado vacío.

============================================================
44. MODALES
============================================================

Todos los modales nuevos deben poder:

- abrir;
- cerrar;
- cancelar;
- confirmar.

Utilizar para:

- eliminar;
- cancelar;
- anular;
- confirmar operación;
- información;
- éxito;
- error.

============================================================
45. DATOS MOCK
============================================================

Utilizar datos MOCK consistentes.

Por ejemplo:

una moneda utilizada en Cotizaciones debe existir también
en Conversor y Tasas.

No usar datos aleatorios inconsistentes.

No presentar mocks como información real.

============================================================
46. RESPONSIVE
============================================================

Todas las nuevas vistas deben funcionar correctamente en:

Desktop:
1440×900

Mobile:
390×844

Comprobar:

- dashboards;
- sidebar;
- tablas;
- formularios;
- modales;
- gráficos;
- conversor;
- Navbar;
- Footer.

No permitir:

- overflow horizontal;
- botones fuera de pantalla;
- contenido cortado;
- modales fuera del viewport.

============================================================
47. ANIMACIONES
============================================================

CONSERVAR las animaciones existentes.

Para nuevas pantallas utilizar animaciones coherentes:

- entrada;
- hover;
- dropdown;
- modal;
- loading;
- éxito;
- transición.

No eliminar animaciones existentes para simplificar.

============================================================
48. ICONOGRAFÍA
============================================================

Utilizar SVG profesionales y lineales.

NO utilizar emojis.

Reutilizar el sistema de iconos existente.

============================================================
49. REGLA SOBRE FUNCIONALIDADES FUTURAS
============================================================

Si una funcionalidad está prevista pero todavía no existe
realmente:

NO eliminar su interfaz.

Representarla como:

"En desarrollo"

o

"Próximamente"

según corresponda.

NO fingir que existe backend.

============================================================
50. AUDITORÍA FINAL
============================================================

Cuando termines, recorre TODO el proyecto como usuario.

Prueba cada menú y cada flujo.

Buscar:

- botones sin acción;
- enlaces muertos;
- pantallas inexistentes;
- pantallas vacías;
- dropdowns que no funcionan;
- modales que no funcionan;
- formularios incompletos;
- botones de volver incorrectos;
- errores de navegación;
- inconsistencias entre roles;
- errores responsive.

Corregir únicamente lo necesario.

============================================================
51. COMPARACIÓN ANTES / DESPUÉS
============================================================

MUY IMPORTANTE:

Al terminar, comprobar que las partes que ya estaban
correctamente diseñadas NO hayan sido alteradas
innecesariamente.

Informar:

1. Qué partes fueron conservadas sin cambios.
2. Qué partes tuvieron correcciones necesarias.
3. Qué vistas nuevas fueron agregadas.
4. Qué vistas incompletas fueron completadas.
5. Qué componentes nuevos fueron creados.
6. Qué componentes existentes fueron reutilizados.
7. Qué botones fueron conectados.
8. Qué flujos quedaron navegables.
9. Qué funcionalidades utilizan MOCK.
10. Qué funcionalidades están "En desarrollo".
11. Qué funcionalidades están fuera de alcance.
12. Qué queda pendiente, si queda algo.

============================================================
RESULTADO FINAL
============================================================

El objetivo es que este proyecto quede como:

"PROTOTIPO VISUAL COMPLETO Y NAVEGABLE DE GLOBAL EXCHANGE"

No quiero únicamente una Landing.

Quiero que todas las funcionalidades relevantes del sistema
tengan su representación visual y puedan recorrerse.

La interfaz debe sentirse como una aplicación completa.

PERO:

NO sacrificar ni rehacer las partes que ya están correctamente
implementadas.

EXTENDER.
COMPLETAR.
CONECTAR.
NO RECONSTRUIR.