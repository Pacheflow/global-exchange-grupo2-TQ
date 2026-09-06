Quiero que MODIFIQUES EL PROTOTIPO ACTUAL de Global Exchange.

IMPORTANTE:

NO rediseñes toda la aplicación desde cero.
NO cambies la identidad visual general que ya construiste.
NO reemplaces las secciones que ya funcionan correctamente.

La dirección visual actual me gusta.

Quiero conservar:

- el Dark Mode actual;
- la paleta azul;
- la estética financiera/editorial;
- la tipografía general;
- la estructura de la Landing;
- el navbar;
- la tabla de Cotizaciones del Día;
- la estructura general del Conversor;
- la estética del Login;
- el Design System existente.

Realiza únicamente las siguientes correcciones y mejoras.

==================================================
1. HERO — CONSERVAR ESTÉTICA, MEJORAR COMPOSICIÓN
==================================================

La sección principal actual tiene una buena dirección visual.

Mantener el concepto:

"Líderes en cambios en Paraguay"

pero mejorar su composición para que se vea todavía más profesional, equilibrada y premium.

Actualmente el texto:

Líderes en
cambios
en Paraguay

funciona conceptualmente, pero quiero mejorar:

- jerarquía;
- espaciado;
- alineación;
- balance entre texto y mapa;
- proporción del headline;
- relación entre título, subtítulo y CTAs.

No reducir la importancia del mensaje.

Debe seguir siendo uno de los elementos más importantes de toda la Landing.

Mantener un enfoque editorial:

Líderes en
cambios
en Paraguay

o una composición similar que aproveche la mezcla entre serif y sans-serif.

"Paraguay" puede seguir teniendo un tratamiento tipográfico especial.

Mantener los CTAs:

Ver cotizaciones
Convertir moneda

==================================================
2. REEMPLAZAR EL GLOBO ACTUAL POR MAPCN
==================================================

Quiero reemplazar el globo ilustrado actual por un mapa interactivo inspirado directamente en:

MapCN
https://www.mapcn.dev/docs/arcs

Utilizar preferentemente el componente de mapa/arcos de MapCN si la integración técnica está disponible.

Quiero un mapa oscuro que combine con Global Exchange y que muestre conexiones mediante ARCOS entre distintas ciudades o regiones.

La estética debe ser similar a la referencia de MapCN:

- mapa oscuro;
- continentes discretos;
- líneas geográficas sutiles;
- puntos luminosos;
- arcos azules;
- pequeñas etiquetas geográficas;
- sensación de conexión internacional.

NO debe parecer una plataforma de criptomonedas.

Debe representar:

- intercambio internacional;
- movimiento de divisas;
- conectividad;
- mercado cambiario;
- flujo entre Paraguay y otros mercados.

==================================================
3. PARAGUAY COMO PUNTO CENTRAL
==================================================

Adaptar el mapa a la identidad de Global Exchange.

Paraguay / Asunción debe tener relevancia visual y funcionar como punto principal de referencia.

Crear conexiones conceptuales como:

Asunción → Nueva York
Asunción → Londres
Asunción → São Paulo
Asunción → Buenos Aires
Asunción → Madrid

No es obligatorio utilizar exactamente todos estos puntos, pero Paraguay debe aparecer claramente como centro visual del sistema.

Los arcos deben aparecer progresivamente mediante animación.

==================================================
4. MOSTRAR LOS PARES DE MONEDAS SOBRE EL MAPA
==================================================

Además de las ciudades, puntos y arcos, quiero que el mapa muestre visualmente los principales pares o "versus" de monedas que maneja Global Exchange.

Mostrar indicadores financieros flotantes alrededor del mapa.

Ejemplos:

USD / PYG
EUR / PYG
BRL / PYG
ARS / PYG

Cada indicador puede mostrar:

Par de monedas

Ejemplo:
USD / PYG

Cotización o valor de referencia:

7.480

Variación:

+0.42%

o:

-0.18%

Utilizar:

verde para variación positiva;
rojo para variación negativa;
azul o neutro si no existe cambio significativo.

IMPORTANTE:

Estos indicadores deben sentirse relacionados con el mapa y las rutas internacionales.

No colocarlos de forma aleatoria solamente como decoración.

Por ejemplo:

USD / PYG puede aparecer visualmente cerca de una conexión relacionada con Estados Unidos.

BRL / PYG cerca de una conexión con Brasil.

ARS / PYG cerca de Argentina.

EUR / PYG cerca de una conexión con Europa.

No es necesario ponerlos exactamente encima de las ciudades.

El objetivo es crear una composición visual equilibrada.

==================================================
5. INDICADORES DE MERCADO DINÁMICOS
==================================================

Los pares de monedas que aparecen alrededor del mapa deben formar parte de la animación del Hero.

Secuencia sugerida:

1. carga el fondo;
2. aparece progresivamente el mapa;
3. aparece Asunción;
4. aparecen los puntos internacionales;
5. comienzan a dibujarse los arcos;
6. aparecen las conexiones completas;
7. aparecen progresivamente los pares de monedas;
8. aparecen sus valores;
9. aparece su variación;
10. queda una animación ambiental muy sutil.

Por ejemplo:

USD / PYG
7.480
+0.42%

puede aparecer primero:

USD / PYG

después:

7.480

y finalmente:

+0.42%

Simular un pequeño contador numérico si resulta visualmente elegante.

==================================================
6. PARES DE MONEDAS PREPARADOS PARA DATOS REALES
==================================================

Los valores utilizados ahora serán datos mock para el prototipo.

Sin embargo, diseñar el componente pensando en que posteriormente el frontend obtendrá estos datos desde una API de tasas.

Crear un componente reutilizable conceptual como:

CurrencyPairIndicator

Estados:

Positive
Negative
Neutral
Loading

Ejemplos actuales:

USD / PYG
EUR / PYG
BRL / PYG
ARS / PYG

Pero dejar preparada la estructura para añadir nuevas monedas posteriormente.

==================================================
7. ANIMACIÓN DEL MAPA
==================================================

El mapa no debe aparecer completamente dibujado desde el primer frame.

Crear una secuencia premium:

1. aparece el mapa;
2. aparecen puntos geográficos;
3. aparece Asunción;
4. comienzan a dibujarse los arcos;
5. aparecen las conexiones restantes;
6. aparecen los indicadores USD/PYG, EUR/PYG, BRL/PYG y ARS/PYG;
7. aparecen sus valores y variaciones.

Utilizar animaciones suaves.

Evitar movimientos exagerados.

Puede existir un movimiento ambiental muy lento después de finalizar la animación.

==================================================
8. REUTILIZAR EXACTAMENTE EL MISMO LENGUAJE DEL MAPA
==================================================

El mapa utilizado en el Hero y el mapa utilizado en la pantalla de Login deben pertenecer al MISMO COMPONENTE VISUAL.

Actualmente existe un globo similar en ambas pantallas.

Quiero mantener esa coherencia pero reemplazando ambos por la nueva solución basada en MapCN.

NO crear dos estilos de mapa diferentes.

Crear un componente reutilizable:

GlobalExchangeMap

con variantes, por ejemplo:

Hero / Large
Authentication / Medium

En la variante Authentication puede mostrarse una versión más sencilla con menos indicadores para no competir visualmente con el formulario.

==================================================
9. LOGIN — AGREGAR REGISTRO
==================================================

La pantalla de Iniciar sesión actual tiene buena estructura visual.

Mantenerla.

Pero actualmente falta una opción clara para crear una cuenta.

Agregar debajo del formulario o debajo del botón:

¿No tienes una cuenta?
Registrarse

donde "Registrarse" sea una acción claramente clickeable.

También puede utilizarse:

¿Aún no tienes una cuenta?
Crear una cuenta

El resultado debe sentirse integrado con la interfaz, no como un botón añadido posteriormente.

Conectar esa acción con la pantalla de Registro.

==================================================
10. LOGIN — MAPA
==================================================

Sustituir el globo actual ubicado en la parte izquierda del Login por la variante del mismo mapa MapCN utilizado en la Landing.

Puede ser más pequeño y tener menos conexiones para no distraer del formulario.

Puede mantener algunos puntos y arcos.

No es necesario mostrar todos los indicadores USD/PYG, EUR/PYG, etc. en el Login si visualmente genera ruido.

Mantener debajo el mensaje institucional:

"La plataforma de cambio más confiable y transparente del mercado paraguayo."

La zona izquierda debe sentirse institucional y visual.

La zona derecha debe mantenerse enfocada en autenticación.

==================================================
11. COTIZACIONES DEL DÍA — CONSERVAR DISEÑO
==================================================

La sección actual de:

Cotizaciones del Día

ME GUSTA.

NO quiero rediseñar la tabla.

Mantener prácticamente el diseño actual:

Moneda
Compra
Venta
90D
Variación
Actualización

Mantener también:

Hoy
7D
30D
90D
1A

El principal cambio debe estar en las INTERACCIONES Y ANIMACIONES.

==================================================
12. SPARKLINES DINÁMICOS
==================================================

Actualmente los pequeños gráficos verdes y rojos aparecen estáticos.

Quiero que se animen.

Cuando el usuario hace scroll y la sección "Cotizaciones del Día" entra por primera vez en el viewport:

los gráficos deben comenzar sin estar completamente dibujados.

Después deben trazarse progresivamente de izquierda a derecha hasta alcanzar su posición final.

Ejemplo conceptual:

inicio:
__________

después:
_/\/\____

después:
_/\/\__/\/

hasta alcanzar el gráfico final.

Hacerlo tanto para:

- tendencias positivas;
- tendencias negativas.

El movimiento debe simular datos financieros cargándose.

NO repetir constantemente la animación mientras el usuario permanece en la sección.

Ejecutarla principalmente al entrar en viewport.

==================================================
13. ANIMAR LOS VALORES DE VARIACIÓN
==================================================

Los porcentajes tampoco deben aparecer instantáneamente.

Por ejemplo:

+0.42%

puede comenzar aproximadamente en:

+0.00%

y progresivamente llegar:

+0.11%
+0.26%
+0.35%
+0.42%

Lo mismo con valores negativos:

0.00%
-0.40%
-1.10%
-1.80%
-2.30%

Debe sentirse como un contador financiero.

Color:

positivo → verde
negativo → rojo

==================================================
14. ANIMAR COMPRA Y VENTA DE FORMA SUTIL
==================================================

También se puede aplicar una pequeña animación numérica a:

Compra
Venta

cuando cargan por primera vez.

NO exagerar.

El objetivo es transmitir:

"dato actualizado"

y no:

"animación decorativa".

==================================================
15. FILTROS TEMPORALES FUNCIONALES
==================================================

Los botones:

Hoy
7D
30D
90D
1A

deben sentirse realmente interactivos.

Actualmente 90D aparece seleccionado.

Al seleccionar otro rango:

- cambiar el estado activo;
- actualizar los sparklines;
- actualizar las variaciones;
- ejecutar una transición suave entre los datos.

Utilizar datos mock para el prototipo.

No es necesario que sean tasas reales todavía.

==================================================
16. CONVERSOR — CORREGIR REGLA FUNCIONAL
==================================================

Existe un ERROR conceptual en el Conversor actual.

Actualmente aparece:

"Inicia sesión para realizar una operación"

y un botón:

"Iniciar sesión"

ELIMINAR ESE BLOQUE DEL CONVERSOR.

El Conversor de Monedas es una FUNCIONALIDAD PÚBLICA.

Debe funcionar completamente tanto para:

- visitante;
- usuario autenticado;
- usuario autenticado sin cliente;
- usuario asociado a cliente.

NO debe exigir autenticación.

El conversor únicamente SIMULA una conversión.

NO genera una transacción.

NO compra.

NO vende.

Por lo tanto no necesita login.

==================================================
17. CONVERSOR — HACERLO MÁS GRANDE
==================================================

Actualmente el componente de conversión ocupa poco espacio.

Quiero darle más protagonismo.

Hacer el bloque del conversor considerablemente MÁS ANCHO.

Puede utilizar una distribución aproximadamente:

Texto / información:
35%–40%

Conversor:
60%–65%

o una composición visual equivalente.

Debe ser uno de los elementos importantes de la Landing.

==================================================
18. MEJORAR EL CONVERSOR
==================================================

Mantener:

TÚ ENTREGAS

1000
USD

⇄

RECIBES APROXIMADAMENTE

7.480.000
PYG

Tipo de cambio aplicado:

1 USD = 7.480 PYG

Última actualización.

Pero aprovechar el nuevo ancho para:

- inputs más grandes;
- mejor separación;
- selector de moneda más claro;
- bandera / código / nombre de moneda;
- mejor jerarquía de resultado.

==================================================
19. BOTÓN INTERCAMBIAR MONEDAS
==================================================

El botón:

⇄

debe ser realmente interactivo.

Ejemplo inicial:

USD → PYG

Al presionarlo:

PYG → USD

Aplicar una pequeña animación de rotación/transición.

Actualizar:

- monedas;
- cantidades;
- tipo de cambio;
- resultado.

No recargar la página.

==================================================
20. CONVERSOR DINÁMICO
==================================================

Cuando el usuario modifica:

1000

el resultado debe actualizarse dinámicamente.

Ejemplo:

1000 USD
→
7.480.000 PYG

500 USD
→
3.740.000 PYG

Puede utilizar datos mock.

Preparar la arquitectura visual para que posteriormente el frontend real consuma una API de tasas.

==================================================
21. NO CONFUNDIR CONVERSIÓN CON OPERACIÓN
==================================================

Regla fundamental:

CONVERSOR
=
simulación pública.

COMPRA / VENTA
=
operación privada.

Nunca tratar ambas cosas como la misma funcionalidad.

El visitante puede convertir libremente.

Posteriormente las operaciones reales de compra/venta estarán disponibles según autenticación, cliente asociado y permisos.

==================================================
22. CONSISTENCIA ENTRE LANDING Y LOGIN
==================================================

Quiero que al pasar:

Landing
→
Login

se sienta que seguimos dentro de GLOBAL EXCHANGE.

Utilizar:

- mismo logo;
- mismo mapa;
- misma paleta;
- misma tipografía;
- mismo sistema de espaciado;
- mismas animaciones;
- mismo Dark Mode.

No hacer que Keycloak parezca una página externa genérica.

==================================================
23. MODO CLARO
==================================================

Mantener también la variante Light Mode.

No es necesario modificar el concepto general.

Asegurarse de que:

- MapCN;
- arcos;
- puntos;
- indicadores de pares de monedas;
- textos;
- cotizaciones;
- gráficos;
- conversor;
- login;

tengan versiones visuales adecuadas para Light Mode.

Dark Mode continúa siendo DEFAULT.

==================================================
24. NO CAMBIAR LO QUE YA FUNCIONA
==================================================

Conservar todo aquello que no está explícitamente solicitado en este prompt.

Especialmente:

- estructura general del prototipo;
- identidad azul;
- estilo financiero;
- navegación;
- pantallas ya construidas;
- dashboards;
- componentes existentes.

Este prompt es una ITERACIÓN DE CORRECCIÓN.

NO es una solicitud para regenerar el producto completo.

==================================================
25. PRIORIDADES DE ESTA ITERACIÓN
==================================================

Prioridad 1:
Reemplazar el globo por una solución basada en MapCN.

Prioridad 2:
Mostrar sobre ese mapa los pares principales:

USD / PYG
EUR / PYG
BRL / PYG
ARS / PYG

con valores y variaciones.

Prioridad 3:
Hacer de Paraguay / Asunción el eje visual de las conexiones.

Prioridad 4:
Mejorar visualmente el Hero y su composición.

Prioridad 5:
Convertir los gráficos y variaciones de Cotizaciones en elementos dinámicos animados.

Prioridad 6:
Eliminar completamente la obligación de iniciar sesión desde el Conversor.

Prioridad 7:
Ampliar y mejorar el Conversor.

Prioridad 8:
Agregar "Registrarse" a la pantalla de Login.

Prioridad 9:
Reutilizar el mismo lenguaje de mapa MapCN en Hero y autenticación.

==================================================
26. RESULTADO ESPERADO
==================================================

Después de realizar estos cambios quiero poder probar nuevamente:

1. entrar a Global Exchange;

2. observar la animación inicial del Hero;

3. visualizar el nuevo mapa basado en MapCN;

4. identificar claramente Paraguay / Asunción;

5. observar arcos que conecten Paraguay con otros mercados;

6. ver alrededor del mapa los pares:

USD / PYG
EUR / PYG
BRL / PYG
ARS / PYG

7. observar sus valores y variaciones;

8. ver cómo estos indicadores aparecen progresivamente;

9. hacer scroll;

10. ver cómo se dibujan progresivamente los gráficos de cotización;

11. ver cómo los porcentajes alcanzan dinámicamente sus valores;

12. cambiar entre Hoy / 7D / 30D / 90D / 1A;

13. bajar al Conversor;

14. convertir monedas sin iniciar sesión;

15. utilizar el botón ⇄;

16. modificar montos dinámicamente;

17. entrar al Login;

18. encontrar una opción clara para Registrarse;

19. ver el mismo lenguaje de mapa utilizado en la Landing.

NO realices cambios adicionales fuera de estos puntos sin necesidad.