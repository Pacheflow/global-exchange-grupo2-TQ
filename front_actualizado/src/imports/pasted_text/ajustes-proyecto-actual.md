Quiero hacer unos ajustes puntuales sobre el proyecto ACTUAL.

IMPORTANTE:
NO rehagas el proyecto.
NO rediseñes las pantallas existentes.
NO cambies la Landing.
NO cambies el Navbar principal.
NO cambies el Footer.
NO cambies colores, tipografías, animaciones, gráficos ni
componentes que ya estén correctamente implementados.

Estos cambios son ÚNICAMENTE de organización de vistas y
navegación.

============================================================
1. RESÚMENES / DASHBOARDS POR ROL
============================================================

Quiero que los dashboards/resúmenes de cada rol funcionen como
el lugar principal donde se muestran las métricas y gráficos
informativos.

Si un gráfico o información solamente sirve para visualizar
datos y NO requiere una pantalla propia ni acciones específicas,
debe mostrarse dentro del RESUMEN del rol correspondiente.

NO crear una pantalla independiente únicamente para mostrar
un gráfico que puede estar dentro del dashboard.

Esto aplica a:

- históricos;
- ganancias;
- estadísticas;
- tendencias;
- KPIs;
- gráficos de actividad;
- gráficos de cotizaciones;
- gráficos de rendimiento;
- cualquier otra visualización meramente informativa.

============================================================
2. ANALISTA CAMBIARIO
============================================================

Para el ANALISTA CAMBIARIO quiero que el resumen/dashboard
concentre la información visual importante.

El resumen puede incluir:

- cotizaciones relevantes;
- evolución de cotizaciones;
- históricos;
- ganancias;
- tendencias;
- indicadores;
- gráficos;
- estadísticas;
- alertas relevantes.

Si "Histórico" o "Ganancias" actualmente aparecen como
pantallas separadas únicamente porque contienen gráficos,
integrar esos gráficos dentro del RESUMEN del Analista cuando
no exista una acción específica que justifique una pantalla
independiente.

IMPORTANTE:

Si una pantalla de Histórico o Ganancias tiene funcionalidades
propias, filtros, tablas, búsqueda, exportación o acciones que
sí justifican una pantalla independiente, CONSERVAR esa pantalla.

La regla es:

INFORMACIÓN VISUAL SIMPLE
→ Resumen

MÓDULO CON FUNCIONALIDAD PROPIA
→ Pantalla independiente

============================================================
3. RESTO DE ROLES
============================================================

Aplicar el mismo criterio al resto de dashboards:

ADMINISTRADOR
CAJERO
USUARIO
ANALISTA CAMBIARIO

Los gráficos puramente informativos deben aparecer dentro del
Resumen/Dashboard correspondiente.

NO crear pantallas independientes solamente para mostrar
gráficos.

Sin embargo, si un módulo necesita acciones propias, mantener
su pantalla.

Ejemplo:

"Ganancias"
Si solamente muestra un gráfico:
→ mostrarlo en Resumen.

Si permite:
- seleccionar período;
- filtrar;
- consultar detalles;
- generar reporte;
- descargar información;

→ mantener una pantalla independiente.

============================================================
4. PANEL DE ADMINISTRADOR
============================================================

Revisar el panel actual del ADMINISTRADOR.

La navegación principal debe seguir siendo el sistema de
navegación que ya existe para el dashboard.

Hay una barra secundaria como la mostrada en la referencia:

Dashboard | Clientes | Usuarios | Roles | Divisas | Tasas | Pagos

QUIERO ELIMINAR ESA BARRA SECUNDARIA DEL PANEL DE ADMINISTRADOR.

No reemplazarla por otra barra horizontal.

No crear otra navegación horizontal equivalente.

El acceso a estos módulos debe realizarse mediante el sistema
de navegación principal existente del dashboard/sidebar.

IMPORTANTE:

NO eliminar las pantallas:

- Clientes
- Usuarios
- Roles
- Divisas/Monedas
- Tasas
- Pagos

SOLAMENTE eliminar la barra horizontal secundaria que las
presenta como navegación.

Las funcionalidades siguen existiendo.

============================================================
5. SIDEBAR / NAVEGACIÓN PRINCIPAL
============================================================

Utilizar el Sidebar existente como navegación principal.

NO crear un segundo sistema de navegación.

El usuario debe poder acceder desde el Sidebar a los módulos
que correspondan a su rol.

Mantener la organización visual actual.

============================================================
6. ADMINISTRADOR
============================================================

El administrador debe poder acceder visualmente a:

- Dashboard / Resumen
- Usuarios
- Clientes
- Roles / permisos
- Monedas
- Cotizaciones
- Tasas
- Medios de pago
- Transacciones
- Facturación
- Cajas
- Reportes

según los módulos que ya estén contemplados en el proyecto.

NO agregar módulos nuevos que no correspondan.

============================================================
7. USUARIO
============================================================

Mantener el panel de usuario actual si ya está correcto.

El Resumen puede concentrar:

- cotizaciones;
- operaciones recientes;
- actividad;
- información del cliente activo;
- gráficos informativos;
- estadísticas.

No crear pantallas separadas únicamente para gráficos.

Las funcionalidades accionables sí deben conservar sus
pantallas:

- operaciones;
- conversor;
- historial;
- perfil;
- etc.

============================================================
8. CAJERO
============================================================

Mantener el dashboard actual.

El Resumen puede mostrar:

- estado de caja;
- operaciones;
- movimientos;
- estadísticas;
- indicadores;
- gráficos informativos.

Las acciones propias deben continuar teniendo sus pantallas:

- apertura;
- movimientos;
- arqueo;
- cierre;
- historial.

============================================================
9. ANALISTA
============================================================

El dashboard del Analista debe funcionar como su centro de
información.

Priorizar dentro del Resumen:

- cotizaciones;
- tendencias;
- históricos;
- ganancias;
- indicadores;
- gráficos;
- estadísticas.

No crear pantallas independientes solamente para gráficos.

============================================================
10. NO MODIFICAR ELEMENTOS YA APROBADOS
============================================================

MUY IMPORTANTE:

NO tocar:

- Landing;
- Hero;
- Market Board;
- Conversor actual;
- Navbar;
- Footer;
- animaciones;
- tipografías;
- colores;
- iconografía;
- componentes;
- responsive;
- estilos;
- gráficos existentes;

salvo que sea ABSOLUTAMENTE NECESARIO para realizar los cambios
indicados anteriormente.

No aprovechar esta tarea para hacer mejoras adicionales.

NO hacer cambios "por conveniencia".

============================================================
11. REGLA FINAL
============================================================

Realizar SOLAMENTE estos cambios:

1. Integrar gráficos puramente informativos dentro de los
   Resúmenes/Dashboards correspondientes.

2. Mantener como pantallas independientes únicamente los módulos
   que tengan funcionalidades propias.

3. Eliminar del panel de Administrador la barra horizontal:

   Dashboard | Clientes | Usuarios | Roles | Divisas | Tasas | Pagos

4. Mantener esos módulos disponibles mediante el Sidebar/
   navegación principal.

5. Mantener intacto todo lo demás.

Antes de finalizar, comprobar que ninguna pantalla existente
haya sido rediseñada innecesariamente.

Al finalizar indicame exactamente:

- qué gráficos fueron integrados a los resúmenes;
- qué pantallas se conservaron como módulos independientes;
- qué barra fue eliminada;
- qué navegación se mantiene;
- qué elementos NO fueron modificados.