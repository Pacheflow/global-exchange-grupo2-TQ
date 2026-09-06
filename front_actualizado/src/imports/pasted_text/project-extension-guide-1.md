Quiero que continúes trabajando SOBRE EL PROYECTO ACTUAL.

NO quiero que empieces de cero.

NO quiero que reemplaces ni rehagas las partes que ya están
correctamente implementadas.

Quiero que revises el proyecto mientras trabajás y que:

- si una vista ya existe y está correctamente implementada,
  CONSERVARLA;
- si una funcionalidad ya existe y funciona correctamente,
  CONSERVARLA;
- si un componente ya existe y está correctamente diseñado,
  REUTILIZARLO;
- si una sección ya está completa,
  NO volver a crearla;
- si falta una vista, AGREGARLA;
- si falta una pantalla dentro de un flujo, AGREGARLA;
- si falta conectar visualmente un botón, COMPLETARLO;
- si falta un estado, AGREGARLO;
- si existe una implementación incompleta, COMPLETARLA;
- si existe un problema de navegación, CORREGIRLO.

El objetivo es EXTENDER lo que ya tenemos, no reemplazarlo.

==================================================
OBJETIVO
==================================================

Quiero que este proyecto quede como un PROTOTIPO VISUAL
COMPLETO Y NAVEGABLE de Global Exchange.

Todo lo que el usuario pueda seleccionar, pulsar o utilizar
debe tener una respuesta visual coherente.

No quiero botones sin función visual.

No quiero enlaces muertos.

No quiero opciones del menú sin pantalla.

No quiero formularios sin estados.

No quiero módulos importantes sin sus vistas.

==================================================
ALCANCE PRIORITARIO — SPRINT 2
==================================================

Asegurate de que el proyecto tenga las vistas necesarias para:

1. CRUD DE MONEDAS
2. CRUD DE COTIZACIONES
3. CRUD DE MEDIOS DE PAGO DEL CLIENTE
4. VISUALIZACIÓN DE TASAS
5. SIMULADOR DE CONVERSIÓN

Si alguna de estas funcionalidades YA ESTÁ COMPLETA:

NO la rehagas.

CONSERVÁ lo existente.

Si está incompleta:

COMPLETALA.

Si falta:

AGREGALA.

==================================================
CRUD DE MONEDAS
==================================================

Debe poder recorrerse visualmente:

Monedas
→ listado
→ crear moneda
→ formulario
→ guardar
→ confirmación

y:

Monedas
→ listado
→ detalle
→ editar
→ guardar
→ confirmación

También representar:

- búsqueda;
- filtros;
- estado;
- activar/desactivar;
- eliminación si corresponde;
- estado vacío;
- éxito;
- error.

==================================================
CRUD DE COTIZACIONES
==================================================

Debe poder recorrerse:

Cotizaciones
→ listado
→ crear
→ formulario
→ confirmar
→ resultado

y:

Cotizaciones
→ listado
→ detalle
→ editar
→ guardar

Representar correctamente:

SUBE:
↑ verde

BAJA:
↓ rojo

SIN CAMBIO:
= neutro

Utilizar SVG profesionales.

Si la pantalla ya existe, conservarla y solamente completar
lo que falte.

==================================================
CRUD DE MEDIOS DE PAGO DEL CLIENTE
==================================================

Debe poder recorrerse:

Medios de pago
→ listado
→ agregar
→ formulario
→ guardar
→ confirmación

También:

→ editar
→ eliminar/desactivar
→ confirmación

Si ya existe alguna de estas pantallas, conservarla.

==================================================
VISUALIZACIÓN DE TASAS
==================================================

Debe existir una pantalla completa para visualizar tasas.

Representar:

- moneda;
- compra;
- venta;
- variación;
- actualización;
- histórico si corresponde;
- filtros/periodos si ya forman parte del diseño.

Utilizar datos MOCK.

==================================================
SIMULADOR DE CONVERSIÓN
==================================================

Mantener/completar el simulador existente.

Debe permitir:

- seleccionar moneda origen;
- seleccionar moneda destino;
- ingresar monto;
- invertir monedas;
- visualizar resultado;
- visualizar tipo de cambio;
- mostrar última actualización;
- mostrar aviso de simulación.

Debe funcionar visualmente.

==================================================
ROLES
==================================================

Revisar las vistas existentes para:

- Usuario;
- Administrador;
- Analista;
- Cajero.

No rehacer dashboards que ya estén correctamente implementados.

Completar únicamente las vistas faltantes.

Todas las opciones visibles de los dashboards deben poder
navegar hacia alguna pantalla correspondiente.

==================================================
NAVEGACIÓN
==================================================

Todos los botones y enlaces deben tener una respuesta.

Ejemplos:

Ver → detalle
Editar → edición
Eliminar → confirmación
Guardar → éxito
Cancelar → volver
Volver → pantalla anterior
Confirmar → resultado
Cerrar → cerrar modal

Mantener el comportamiento actual del Navbar y Footer que ya
fue corregido.

Navbar:
- un solo elemento activo;
- navegación correcta.

Footer:
- scroll suave;
- sin estado activo permanente.

NO romper estas correcciones.

==================================================
DATOS MOCK
==================================================

Este proyecto es solamente el prototipo visual.

Los datos pueden seguir siendo MOCK.

No implementar:

- Django;
- PostgreSQL;
- Keycloak;
- APIs reales;
- backend real.

No modificar la arquitectura para simular un backend real.

Los datos MOCK deben ser consistentes entre las distintas
pantallas.

==================================================
FUNCIONALIDADES FUTURAS
==================================================

Si una funcionalidad está contemplada pero todavía no puede
funcionar realmente:

mantener la interfaz.

Mostrar:

"Próximamente"

o

"En desarrollo"

según corresponda.

No eliminarla.

No fingir que está conectada a una API real.

==================================================
DISEÑO
==================================================

Mantener EXACTAMENTE la identidad visual actual.

No rehacer el diseño.

Mantener:

- modo oscuro;
- tipografías;
- colores;
- animaciones;
- gráficos;
- iconos SVG;
- cards;
- tablas;
- botones;
- espaciados;
- responsive;
- Navbar;
- Footer.

Las nuevas pantallas deben utilizar los mismos componentes y
lenguaje visual de las pantallas existentes.

No quiero que cada módulo tenga un diseño diferente.

==================================================
RESPONSIVE
==================================================

Todas las pantallas nuevas deben funcionar en:

1440×900

y:

390×844

Sin:

- overflow horizontal;
- elementos cortados;
- botones fuera de pantalla;
- modales fuera del viewport;
- tablas inutilizables.

==================================================
REGLA MÁS IMPORTANTE
==================================================

TRABAJAR DE FORMA INCREMENTAL.

ANTES DE CREAR ALGO:

revisá si ya existe.

SI YA EXISTE Y ESTÁ BIEN:
→ conservar.

SI EXISTE PERO ESTÁ INCOMPLETO:
→ completar.

SI EXISTE PERO TIENE UN ERROR:
→ corregir.

SI NO EXISTE:
→ crear.

NO DUPLICAR COMPONENTES.

NO CREAR DOS VERSIONES DE LA MISMA PANTALLA.

NO REEMPLAZAR PARTES COMPLETAS POR OTRA IMPLEMENTACIÓN.

Reutilizar los componentes existentes siempre que sea posible.

==================================================
RESULTADO
==================================================

Al finalizar quiero que el proyecto actual haya avanzado desde
su estado actual hacia un prototipo visual completo.

No quiero que me devuelvas solamente una propuesta.

QUIERO QUE IMPLEMENTES DIRECTAMENTE LOS ELEMENTOS QUE FALTEN.

Trabajá sobre lo existente y agregá únicamente lo necesario.

Al finalizar indicame:

- qué partes ya estaban completas y fueron conservadas;
- qué partes estaban incompletas y fueron completadas;
- qué vistas nuevas agregaste;
- qué botones/enlaces nuevos conectaste;
- qué flujos quedaron navegables;
- qué funcionalidades siguen siendo MOCK;
- qué funcionalidades quedaron como "En desarrollo";
- qué queda pendiente, si queda algo.

No hagas una reconstrucción desde cero.
No elimines trabajo existente.
No dupliques pantallas.
EXTIENDE EL PROYECTO ACTUAL.