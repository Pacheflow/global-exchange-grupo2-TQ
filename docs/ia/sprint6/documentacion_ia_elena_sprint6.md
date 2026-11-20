\# Documentación de uso de IA — Sprint 6



\*\*Integrante:\*\* Elena Gisselle Ramirez Medina



\## Consultas y decisiones



\### 1. ¿Qué parte del Sprint 6 corresponde a Elena?



\*\*Respuesta resumida de la IA:\*\* Comparar la guía del proyecto, la ERS, el plan del Sprint 6 y las historias de Jira para distinguir el alcance general del equipo de la responsabilidad individual de Elena.



\*\*Aplicación:\*\* Elena quedó responsable de construir un reporte administrativo de transacciones independiente del historial normal del usuario y del dashboard financiero.



El cálculo de ganancias, los agregados financieros, el dashboard y el gráfico histórico de tasas quedaron asignados a otros integrantes.



\---



\### 2. ¿El reporte de Elena depende de la implementación de ganancias de otro integrante?



\*\*Respuesta resumida de la IA:\*\* El reporte puede consultar directamente las operaciones registradas. Solo dependería de la lógica financiera común si tuviera que calcular o mostrar ganancias globales.



\*\*Decisión:\*\* El reporte administrativo se implementó de forma independiente. Muestra las operaciones y sus datos históricos, incluida la comisión individual, pero no calcula ganancias ni agrega importes de diferentes monedas.



\---



\### 3. ¿Qué roles deben acceder al reporte administrativo?



\*\*Respuesta resumida de la IA:\*\* El reporte global contiene información operativa de todos los clientes, por lo que debe restringirse mediante permisos de backend. El historial particular del usuario, las consultas de Caja y los reportes financieros deben permanecer en sus módulos correspondientes.



\*\*Decisión:\*\* Solo el rol efectivo `ADMINISTRADOR` puede acceder al reporte administrativo.



No tienen acceso:



\- `USUARIO`;

\- `CAJERO`;

\- `ANALISTA\_CAMBIARIO`;

\- visitantes sin autenticación.



\*\*Aplicación:\*\* La autorización se verifica en backend tanto en el listado como en el detalle. Ocultar la opción del menú no se utiliza como única protección.



Se conserva la prioridad multirrol existente:



\- `ADMINISTRADOR + CAJERO` puede acceder;

\- `ANALISTA\_CAMBIARIO + CAJERO` no puede acceder.



\---



\### 4. ¿Qué información debe mostrar el reporte?



\*\*Respuesta resumida de la IA:\*\* Mostrar los datos necesarios para revisar una operación sin obligar al administrador a ingresar en distintos módulos.



\*\*Aplicación:\*\* La tabla muestra:



\- ID de operación;

\- fecha y hora;

\- cliente;

\- tipo de operación;

\- moneda e importe de origen;

\- moneda e importe de destino;

\- tasa aplicada;

\- comisión y su moneda;

\- método de pago;

\- naturaleza histórica;

\- estado;

\- actor o cajero cuando existe información registrada;

\- acceso al detalle.



El reporte incluye operaciones online y presenciales.



\---



\### 5. ¿Cómo deben tratarse los importes, tasas y comisiones?



\*\*Respuesta resumida de la IA:\*\* Un reporte histórico no debe recalcular las condiciones económicas utilizando las tasas, preferencias o configuraciones actuales.



\*\*Aplicación:\*\* Los importes, la tasa aplicada y la comisión se obtienen directamente de la operación registrada.



No se recalculan utilizando:



\- tasas actuales;

\- comisiones actuales;

\- método preferido actual;

\- configuración actual del catálogo.



La comisión se presenta con la moneda correspondiente. No se suman comisiones de monedas diferentes como si representaran una única ganancia.



\---



\### 6. ¿Cómo deben mostrarse las operaciones heredadas?



\*\*Respuesta resumida de la IA:\*\* No se debe deducir la naturaleza histórica de una operación utilizando únicamente la clasificación actual del método de pago.



\*\*Aplicación:\*\* El reporte utiliza la naturaleza histórica persistida en la operación. Cuando un registro heredado no tiene una clasificación confiable, se muestra:



\*\*Sin clasificación histórica\*\*



Las operaciones antiguas no se excluyen del reporte por esta razón.



\---



\### 7. ¿Qué filtros necesita el reporte?



\*\*Respuesta resumida de la IA:\*\* Incluir filtros suficientes para consultar la actividad operativa sin agregar opciones secundarias que amplíen innecesariamente el alcance.



\*\*Aplicación:\*\* Se implementaron los siguientes filtros:



\- fecha desde;

\- fecha hasta;

\- cliente;

\- tipo de operación;

\- estado;

\- naturaleza histórica;

\- moneda.



Los filtros se combinan mediante una condición lógica `AND`.



No se agregaron filtros por actor, rango de monto, ID o método específico en esta entrega.



\---



\### 8. ¿Cómo debe funcionar el filtro por fecha?



\*\*Respuesta resumida de la IA:\*\* Interpretar las fechas con la zona horaria del proyecto, permitir extremos abiertos e incluir completamente la fecha final.



\*\*Aplicación:\*\* El reporte permite utilizar:



\- fecha desde y fecha hasta;

\- solamente fecha desde;

\- solamente fecha hasta.



La fecha hasta incluye el día completo.



El sistema muestra errores claros cuando:



\- una fecha es inválida;

\- la fecha desde es posterior a la fecha hasta.



Ante filtros inválidos no se devuelve silenciosamente el listado completo.



\---



\### 9. ¿Cómo debe funcionar el filtro por moneda?



\*\*Respuesta resumida de la IA:\*\* Una moneda puede participar como origen o destino de una operación, por lo que el filtro debe contemplar ambos casos sin duplicar resultados.



\*\*Aplicación:\*\* El filtro devuelve operaciones donde la moneda seleccionada aparece como:



\- moneda de origen; o

\- moneda de destino.



La consulta evita duplicar una operación cuando existe coincidencia en más de una relación.



\---



\### 10. ¿Cómo evitamos cargar todas las operaciones al mismo tiempo?



\*\*Respuesta resumida de la IA:\*\* Aplicar filtros, orden y paginación desde la base de datos, conservando los parámetros en la URL.



\*\*Aplicación:\*\* El reporte utiliza paginación backend de 25 registros por página.



El orden predeterminado es:



1\. fecha más reciente;

2\. ID descendente como desempate estable.



Los filtros se conservan al cambiar de página.



Cuando no existen coincidencias, se muestra:



> No se encontraron transacciones con los filtros seleccionados.



\---



\### 11. ¿El reporte debe permitir modificar operaciones?



\*\*Respuesta resumida de la IA:\*\* Un reporte administrativo debe mantenerse como una herramienta de consulta. El acceso a información no debe conceder permisos operativos adicionales.



\*\*Decisión:\*\* El reporte y su detalle son de solo lectura.



Desde estas pantallas no se permite:



\- cancelar operaciones;

\- cambiar métodos de pago;

\- modificar importes;

\- cambiar estados;

\- liquidar Caja;

\- reintentar pagos;

\- emitir facturas;

\- modificar Fondos.



Las consultas GET no ejecutan escrituras financieras ni recuperación de pagos.



\---



\### 12. ¿Debemos calcular ganancias dentro del reporte?



\*\*Respuesta resumida de la IA:\*\* La comisión histórica de una operación puede mostrarse, pero no debe interpretarse automáticamente como ganancia neta. Las monedas distintas tampoco pueden sumarse sin una conversión definida.



\*\*Decisión:\*\* Elena no implementó:



\- ganancia global;

\- ganancia neta;

\- suma global de comisiones;

\- conversión monetaria;

\- agregados financieros;

\- API de ganancias;

\- indicadores del dashboard.



Esta parte permanece bajo responsabilidad del integrante asignado al núcleo financiero.



\---



\### 13. ¿En qué rama debe desarrollarse el reporte?



\*\*Respuesta resumida de la IA:\*\* Cada historia debe implementarse en una rama separada creada desde `develop` actualizado.



\*\*Aplicación:\*\* El reporte administrativo se desarrolló en:



`feature/hu-s6-01-reporte-administrativo-transacciones`



La rama fue creada desde `develop` en:



`96088baf988bab3d85cdf96d89c59131a2faf0db`



Posteriormente se integró mediante el PR #58.



\---



\### 14. ¿Qué rutas se agregaron para el reporte?



\*\*Respuesta resumida de la IA:\*\* Separar el listado administrativo del detalle de consulta y proteger ambos endpoints con la misma política de autorización.



\*\*Aplicación:\*\* Se agregaron las siguientes rutas:



\- `/operaciones/reportes/transacciones/`

\- `/operaciones/reportes/transacciones/<id>/`



La primera presenta filtros, resultados y paginación. La segunda muestra el detalle administrativo de la operación seleccionada.



\---



\### 15. ¿Qué texto debe mostrar el bloque de resultados?



\*\*Respuesta resumida de la IA:\*\* Mantener la interfaz sencilla y evitar mostrar explicaciones técnicas internas dentro de una pantalla destinada al usuario.



\*\*Decisión final de Elena:\*\* Se retiró el párrafo técnico que explicaba el origen de los datos.



El bloque muestra únicamente:



\- el título \*\*Resultados\*\*;

\- la cantidad dinámica de transacciones encontradas.



Ejemplo:



> Resultados  

> 12 transacciones encontradas.



\---



\### 16. ¿Qué pruebas necesita el reporte administrativo?



\*\*Respuesta resumida de la IA:\*\* Cubrir permisos, filtros, paginación, históricos y ausencia de efectos secundarios, evitando pruebas duplicadas que solo repitan la implementación.



\*\*Aplicación:\*\* Se agregaron pruebas para comprobar:



\- acceso del administrador;

\- rechazo de visitantes;

\- rechazo de usuario, cajero y analista;

\- prioridad multirrol;

\- protección de las rutas directas;

\- filtros individuales y combinados;

\- fechas inclusivas y rangos inválidos;

\- moneda como origen o destino;

\- naturaleza histórica;

\- registros heredados sin clasificación;

\- paginación;

\- conservación de filtros;

\- orden estable;

\- ausencia de resultados;

\- detalle correcto;

\- ausencia de acciones financieras.



Cada prueba nueva posee un docstring breve en español.



\*\*Resultado inicial:\*\*



\- 19 pruebas específicas aprobadas;

\- 687 pruebas Django de regresión aprobadas;

\- `manage.py check` aprobado;

\- `makemigrations --check --dry-run` aprobado;

\- `migrate --check` aprobado;

\- `git diff --check` aprobado.



\---



\### 17. ¿Por qué se agregó una exportación PDF?



\*\*Respuesta resumida de la IA:\*\* La profesora solicitó que el reporte permitiera exportar las transacciones. La ERS también contempla la descarga del historial en PDF o Excel.



\*\*Decisión final de Elena:\*\* Se incorporó un único botón llamado:



\*\*Exportar transacciones\*\*



La exportación se realizó en PDF para presentar la información de manera legible y conservar una apariencia similar al reporte mostrado en la página.



\---



\### 18. ¿La exportación debe implementarse en la misma rama anterior?



\*\*Respuesta resumida de la IA:\*\* Como el reporte original ya estaba integrado en `develop`, la ampliación debía realizarse en una nueva rama para mantener un historial claro y un PR independiente.



\*\*Aplicación:\*\* La exportación se desarrolló en:



`feature/hu-s6-01-exportar-transacciones-pdf`



La rama fue creada desde `develop`, que ya contenía el reporte administrativo.



\---



\### 19. ¿Qué debe exportar el PDF?



\*\*Respuesta resumida de la IA:\*\* Reutilizar la misma validación, consulta y orden del reporte, pero exportar todos los resultados filtrados en lugar de limitarse a la página visible.



\*\*Aplicación:\*\* El PDF:



\- exige rol efectivo `ADMINISTRADOR`;

\- utiliza los filtros actuales;

\- incluye todos los resultados filtrados;

\- no se limita a los 25 registros visibles;

\- conserva el orden del reporte;

\- utiliza los datos históricos registrados;

\- no modifica operaciones;

\- no ejecuta acciones financieras.



El PDF no incluye la columna de acciones ni el enlace \*\*Ver detalle\*\*.



\---



\### 20. ¿Qué información debe incluir el PDF?



\*\*Respuesta resumida de la IA:\*\* Incluir la información necesaria para identificar las condiciones de cada operación y el contexto de la exportación.



\*\*Aplicación:\*\* El documento contiene:



\- título `Reporte de transacciones`;

\- fecha y hora de generación;

\- resumen de filtros aplicados;

\- cantidad total de transacciones;

\- tabla de resultados;

\- encabezados repetidos;

\- numeración de páginas.



La tabla incluye:



\- ID;

\- fecha y hora;

\- cliente;

\- tipo;

\- origen;

\- destino;

\- tasa aplicada;

\- comisión;

\- método;

\- naturaleza histórica;

\- estado;

\- actor relacionado.



\---



\### 21. ¿Cómo hacemos que un PDF con muchas columnas sea legible?



\*\*Respuesta resumida de la IA:\*\* Utilizar una página más amplia en orientación horizontal, agrupar datos relacionados, permitir saltos de línea y repetir los encabezados.



\*\*Aplicación:\*\* El PDF se genera con:



\- tamaño A3;

\- orientación horizontal;

\- márgenes definidos;

\- textos ajustados en celdas;

\- encabezados repetidos en cada página;

\- contraste adecuado;

\- numeración de páginas.



Se generó un PDF ficticio de tres páginas para revisar:



\- textos largos;

\- acentos;

\- importes grandes;

\- distribución de columnas;

\- encabezados;

\- numeración.



El PDF de muestra permaneció fuera del commit.



\---



\### 22. ¿Qué biblioteca usamos para generar el PDF?



\*\*Respuesta resumida de la IA:\*\* Utilizar una biblioteca estable que permita tablas multipágina, encabezados repetidos, orientación horizontal y numeración.



\*\*Aplicación:\*\* Se incorporó:



`reportlab==4.4.9`



La dependencia quedó declarada en `requirements.txt`.



El `Dockerfile` instala las dependencias mediante:



`python -m pip install -r requirements.txt`



Por lo tanto, ReportLab se instalará automáticamente cuando el equipo reconstruya la imagen Docker.



\---



\### 23. ¿Dónde debe ubicarse el botón de exportación?



\*\*Respuesta resumida de la IA:\*\* Mantener la acción visible dentro del bloque de filtros y utilizar el mismo estilo de las acciones principales del sistema.



\*\*Decisión final de Elena:\*\* El botón \*\*Exportar transacciones\*\*:



\- comparte el estilo del botón \*\*Buscar\*\*;

\- utiliza fondo azul y texto blanco;

\- se encuentra arriba a la derecha del bloque \*\*Filtros\*\*;

\- está alineado con el título del bloque;

\- se adapta a pantallas pequeñas;

\- envía los valores actuales del formulario.



El botón \*\*Buscar\*\* conserva su comportamiento original.



\---



\### 24. ¿Qué pruebas necesita la exportación?



\*\*Respuesta resumida de la IA:\*\* Comprobar permisos, respuesta PDF, filtros, exportación multipágina, datos históricos y ausencia de efectos secundarios.



\*\*Aplicación:\*\* La cobertura se amplió a 22 pruebas específicas.



Se verificó:



\- acceso del administrador;

\- rechazo de otros roles;

\- respuesta `application/pdf`;

\- nombre del archivo;

\- filtros individuales y combinados;

\- exportación de más de 25 resultados;

\- exportación de todos los resultados;

\- orden de las operaciones;

\- filtros inválidos;

\- ausencia de resultados;

\- ausencia de efectos secundarios.



\*\*Resultado final:\*\*



\- 22 pruebas específicas aprobadas;

\- 690 pruebas Django de regresión aprobadas;

\- `manage.py check` aprobado;

\- `makemigrations --check --dry-run` aprobado;

\- `git diff --check` aprobado;

\- `git diff --cached --check` aprobado.



No fue necesario agregar migraciones.



\---



\### 25. ¿Por qué apareció `ERR\_EMPTY\_RESPONSE` durante el QA?



\*\*Respuesta resumida de la IA:\*\* Revisar el estado del contenedor, los registros de Django, el puerto publicado y los errores de importación antes de reiniciar servicios o modificar datos.



\*\*Diagnóstico:\*\* El puerto `127.0.0.1:8000` estaba publicado y `runserver` seguía en ejecución, pero el hilo principal de Django había fallado durante una recarga al importar:



`operaciones.reporte\_pdf`



Antes de intervenir se comprobó que:



\- ReportLab 4.4.9 estaba instalado;

\- el módulo podía importarse;

\- no existían migraciones pendientes;

\- los datos y volúmenes estaban conservados.



\*\*Aplicación:\*\* Se reinició únicamente el servicio `web`.



Después del reinicio:



\- `localhost:8000` respondió HTTP 200;

\- Docker marcó `web` como saludable;

\- el arranque indicó `No migrations to apply`;

\- la exportación sin sesión redirigió a `/login/` con HTTP 302;

\- las 22 pruebas específicas volvieron a aprobarse.



\---



\### 26. ¿Cómo se publicó la exportación?



\*\*Respuesta resumida de la IA:\*\* Revisar el diff, excluir archivos temporales, ejecutar las verificaciones y publicar la rama sin utilizar force push.



\*\*Aplicación:\*\* Se creó el commit:



`62f0f499a6c6178790a3578547d0be2fb6a12269`



Mensaje:



`feat(reportes): exportar transacciones filtradas a PDF`



Repositorio:



`Pacheflow/global-exchange-grupo2-TQ`



Rama:



`feature/hu-s6-01-exportar-transacciones-pdf`



La rama local y la remota quedaron sincronizadas:



\- 0 commits por delante;

\- 0 commits por detrás.



\---



\### 27. ¿Qué QA manual queda pendiente?



\*\*Respuesta resumida de la IA:\*\* Verificar la descarga utilizando una sesión real de administrador y comprobar que los filtros actuales lleguen al PDF.



\*\*QA definido:\*\*



1\. Iniciar sesión como `ADMINISTRADOR`.

2\. Abrir \*\*Reportes → Transacciones\*\*.

3\. Modificar distintos filtros.

4\. Pulsar \*\*Exportar transacciones\*\*.

5\. Verificar que el PDF utilice los filtros recién editados.

6\. Confirmar que incluya todos los resultados y no solo la página visible.

7\. Revisar la legibilidad de las columnas.

8\. Revisar encabezados y numeración.

9\. Probar una combinación sin resultados.

10\. Comprobar que los demás roles no accedan al endpoint.



\---





