Quiero realizar una migración técnica de la capa visual actual.

IMPORTANTE:

NO quiero modificar el diseño.

NO quiero rediseñar.

NO quiero mejorar visualmente.

NO quiero reinterpretar componentes.

El objetivo es una conversión 1:1 del frontend actual.

==================================================
OBJETIVO
==================================================

Convertir todo el frontend actual generado en Figma Make
desde React/Tailwind hacia:

- HTML
- CSS
- Tailwind CSS
- JavaScript solamente cuando sea necesario

Manteniendo EXACTAMENTE la misma apariencia y experiencia.

La nueva implementación debe ser una capa visual compatible
con Django Templates.

==================================================
REGLA PRINCIPAL
==================================================

El resultado debe verse idéntico al proyecto actual.

Mantener:

- estructura visual;
- layouts;
- tamaños;
- posiciones;
- colores;
- tipografías;
- sombras;
- bordes;
- transparencias;
- degradados;
- espaciados;
- iconos;
- gráficos;
- animaciones;
- transiciones;
- hover effects;
- estados activos;
- estados loading;
- responsive.

NO simplificar.

NO eliminar animaciones.

NO reemplazar componentes por versiones básicas.

NO hacer una versión aproximada.

Debe ser una conversión 1:1.

==================================================
ARQUITECTURA FINAL
==================================================

El resultado debe quedar preparado para Django.

Utilizar:

templates/
    *.html

static/
    css/
    js/
    images/

La estructura debe permitir posteriormente conectar:

- variables Django;
- URLs Django;
- sesiones Django;
- permisos Django;
- datos reales del backend.

==================================================
NO UTILIZAR
==================================================

Eliminar dependencia de:

- React;
- JSX;
- TSX;
- React Router;
- Context API;
- estados simulados;
- autenticación simulada;
- usuarios demo internos.

No crear una SPA.

No implementar un backend falso.

==================================================
DATOS DINÁMICOS
==================================================

Donde actualmente existen datos simulados, preparar la
estructura para recibir datos desde Django.

Ejemplo:

Antes:

Usuario fijo:
"Carlos"

Después:

{{ user.username }}

Pero mantener exactamente la misma apariencia.

==================================================
COMPONENTES
==================================================

Convertir los componentes actuales a bloques HTML reutilizables.

Ejemplos:

Navbar React
→ navbar.html

Sidebar React
→ sidebar.html

MarketBoard React
→ market_board.html

Cards
→ componentes HTML reutilizables

Modales
→ componentes HTML reutilizables

Tablas
→ templates Django

No perder ningún componente visual.

==================================================
ANIMACIONES
==================================================

Todas las animaciones actuales deben mantenerse.

Convertir:

React animations
→ CSS animations / transitions
→ JavaScript cuando sea estrictamente necesario.

Mantener:

- duración;
- delay;
- easing;
- comportamiento;
- interacción.

==================================================
GRÁFICOS
==================================================

Mantener exactamente:

- sparklines;
- gráficos;
- líneas;
- barras;
- indicadores;
- animaciones.

Si actualmente utilizan librerías React:

convertir a:

- SVG;
- CSS;
- JavaScript ligero.

No simplificar los gráficos.

==================================================
NAVEGACIÓN
==================================================

Mantener exactamente:

Navbar:
- diseño actual;
- estado activo;
- dropdowns;
- responsive.

Footer:
- scroll suave;
- navegación por secciones.

Sidebar:
- estados;
- colapsado;
- móvil.

Cambiar solamente la tecnología.

==================================================
RESPONSIVE
==================================================

Mantener exactamente:

Desktop:
1440x900

Mobile:
390x844

No debe existir:

- overflow;
- elementos cortados;
- botones fuera de pantalla;
- tablas inutilizables.

==================================================
FORMULARIOS
==================================================

Mantener:

- diseño;
- validaciones visuales;
- errores;
- estados;
- loading;
- éxito.

La lógica real será posteriormente conectada con Django.

==================================================
ROLES
==================================================

Mantener las vistas visuales de:

- Usuario;
- Administrador;
- Analista Cambiario;
- Cajero.

No modificar los diseños.

Solamente preparar la capa HTML para que Django controle
qué elementos mostrar según permisos.

==================================================
BACKEND
==================================================

NO modificar:

- Django;
- modelos;
- vistas;
- URLs;
- Keycloak;
- PostgreSQL;
- APIs.

Este trabajo es únicamente frontend visual.

==================================================
RESULTADO ESPERADO
==================================================

Al finalizar quiero tener:

Un frontend completo de Global Exchange convertido a:

HTML + Tailwind + CSS + JavaScript

que visualmente sea idéntico al proyecto actual de Figma.

Debe estar preparado para integrarse directamente dentro de
Django Templates.

No quiero una nueva versión.

No quiero una reinterpretación.

Quiero una migración 1:1 del frontend existente.