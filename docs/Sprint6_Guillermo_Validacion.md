# Sprint 6 — validación y evidencia de Guillermo Benítez

## Estado de la entrega

Actualización del 16 de noviembre de 2026: Guillermo autorizó expresamente
publicar estos cambios en GitHub y actualizar el servidor. Las secciones
siguientes conservan el estado y la evidencia de la validación previa a esa
autorización; no describen por sí solas el resultado del nuevo despliegue.
El despliegue autorizado utiliza `scripts/deploy-production.sh`, que registra
los commits anterior y nuevo junto con los backups privados en el servidor.
La validación posterior genera una nueva evidencia JSON fuera del repositorio;
los JSON anteriores de esta carpeta conservan su valor histórico.

**Código implementado localmente. Funcionalidad nueva no desplegada en producción.**
Guillermo indicó expresamente que primero quiere validar en su computadora y
que el despliegue debe esperar su autorización posterior. Las pruebas remotas
se ejecutaron en contenedores independientes, con una red y PostgreSQL temporal
propios. No se actualizaron ni reiniciaron los servicios productivos.

| Entregable | Estado |
| --- | --- |
| Definición de ganancia y moneda | Confirmadas por Guillermo: comisiones en PYG |
| Lógica financiera única y agregados día/semana/mes | Implementados |
| API común y permisos administrativos | Implementados |
| Documentación técnica, explicación y registro IA | Entregados |
| Validación estática del script productivo | Correcta |
| Validación del despliegue existente | Ejecutada; dos comprobaciones pendientes |
| Validación manual local por Guillermo | Pendiente |
| Publicación del código nuevo en producción | Pendiente de autorización explícita |

## Validación local antes de publicar

En esta computadora hay Docker, pero el usuario `guillermo` no pertenece al grupo
`docker`. El socket pertenece a `root:docker`, el acceso normal fue rechazado y
`sudo -n` requiere contraseña. El Python local es 3.12, sin Django ni `ensurepip`;
no representa el entorno oficial Python 3.13/Django 6.1. No se cambiaron permisos
del socket ni grupos del usuario.

Desde una terminal local con permisos Docker (si corresponde, anteponer `sudo`):

```bash
cd /home/guillermo/Escritorio/PROJECT/global-exchange-grupo2-TQ
sudo docker compose up --build -d
sudo docker compose exec -T web python manage.py check
sudo docker compose exec -T web python manage.py test operaciones.test_finanzas
sudo docker compose exec -T web python manage.py test
```

`up --build` es necesario para incluir los cambios si la imagen previa no los
contiene. Arranca el entorno de desarrollo local; no publica en la VM. El
entrypoint aplica las migraciones existentes. Este cambio no agrega migraciones.

Abrir `http://localhost:8000`, iniciar sesión como administrador y consultar:

```text
http://localhost:8000/api/operaciones/metricas-financieras/?desde=2026-10-01&hasta=2026-10-31&agrupacion=dia
```

Usar fechas con operaciones reales del entorno local. Una respuesta sin datos
debe mostrar ceros. El rol cliente debe recibir 403 y sin sesión debe devolver
401. Para probar montos, completar una operación mediante los flujos existentes
y comparar la comisión almacenada con el total del período.

Los escenarios detallados están en la guía y en los 14 tests financieros. La API
es el entregable de Guillermo; el dashboard visual será integrado por Axel.

## Resultados automáticos

- 14 tests financieros nuevos: correctos con Python 3.13.18, Django 6.1 y PostgreSQL.
- 6 tests del validador productivo: correctos localmente con Python estándar.
- 5 archivos de pruebas frontend: correctos con `node --test static/js/tests/*.test.cjs`.
- Compilación de módulos Python nuevos: correcta.
- `git diff --check`: correcto.
- Suite completa backend: **682 pruebas correctas en 126,324 segundos**; resultado en
  [backend-regresion.log](evidencias/sprint6/backend-regresion.log).

La primera ejecución completa descubrió 682 pruebas: 680 correctas y dos errores
de archivos ausentes en el empaquetado temporal (`.env.production.example` y
`keycloak/global-exchange-realm.json`). Se corrigió el paquete y se repitió la
suite completa. No se modificaron tests para eludir esos errores.

También se conservan [frontend-tests.log](evidencias/sprint6/frontend-tests.log)
y [validador-tests.log](evidencias/sprint6/validador-tests.log). El archivo
[SHA256SUMS](evidencias/sprint6/SHA256SUMS) identifica las fuentes nuevas y
modificadas del backend y del validador al finalizar la entrega.

La ejecución remota empleó la imagen ya instalada como entorno de dependencias;
montó una copia temporal del código local en `/app` en modo solo lectura,
sustituyó el entrypoint por el comando de tests y usó PostgreSQL independiente.
La base productiva no se utilizó para estas pruebas. Los contenedores y la red
temporal se eliminan al terminar por el trap de limpieza del ejecutor.

## Validación productiva observada

El repositorio de la VM estaba limpio y en el commit
`4e5c18daf347f0b5e75f5205f73a66307b823bb2`, igual que el punto de partida local.
La evidencia corresponde a **esa versión desplegada**, no al código nuevo del
sprint 6. Los timestamps de evidencia están en UTC.

[validacion-estatica.json](evidencias/sprint6/validacion-estatica.json): sintaxis
Bash y resolución de Compose correctas usando la plantilla pública. Esa prueba
no inicia contenedores ni valida credenciales.

[validacion-productiva.json](evidencias/sprint6/validacion-productiva.json):

| Comprobación | Resultado |
| --- | --- |
| Sintaxis del script de despliegue | Correcta |
| Compose con configuración productiva | Correcto |
| PostgreSQL, Keycloak, web y Nginx | Saludables |
| Migraciones aplicadas | Correcto |
| Respuesta de salud interna de Nginx | Correcta |
| Imagen web identificada con el commit del repositorio | Falla: etiqueta de revisión vacía |
| Django `check --deploy --fail-level WARNING` | Falla: cinco advertencias |

Además, consultas HTTP a la aplicación pública y al documento de descubrimiento
OIDC devolvieron **200**. No se ejecutaron pagos reales, emisión fiscal, cambios
de configuración, restore ni reinicios productivos.

Las cinco advertencias verificadas son:

- `security.W004`: HSTS sin configurar.
- `security.W008`: redirección HTTPS desactivada.
- `security.W009`: `SECRET_KEY` no cumple el criterio de fortaleza de Django.
- `security.W012`: cookie de sesión sin atributo Secure.
- `security.W016`: cookie CSRF sin atributo Secure.

La demostración HTTP explica las advertencias de transporte, pero no debe
confundirse con una validación estricta de producción HTTPS. No se cambiaron
cookies ni redirecciones a ciegas: habilitarlas sobre HTTP impediría el acceso.
La clave debe rotarse en una ventana coordinada, pues afecta a las sesiones.
No se registró su valor en la documentación.

La etiqueta vacía impide probar que la imagen en ejecución corresponde al HEAD.
El Dockerfile actual ya define `org.opencontainers.image.revision`, y el script
productivo pasa `BUILD_COMMIT` y comprueba la etiqueta; hará falta construir y
desplegar una imagen trazable cuando Guillermo autorice la publicación.

Por estos motivos, `validacion_productiva_completa=false`. No se ejecutó
`deploy-production.sh`, no se creó un release/tag y no se declaró aprobada la
producción.

## Uso reproducible del validador

Validación estática local con un archivo de salida nuevo:

```bash
python3 scripts/validate-production.py \
  --env-file .env.production.example \
  --output /tmp/sprint6-estatica-nueva.json
```

Después de validar localmente y **cuando Guillermo autorice una intervención
productiva**, ejecutar en la VM sobre el repositorio desplegado:

```bash
python3 scripts/validate-production.py \
  --env-file .env.production \
  --runtime \
  --output /tmp/sprint6-productiva-nueva.json
```

También acepta `--project-dir` y `--compose-file`. El modo runtime requiere
acceso a Docker y permisos para ejecutar comandos de lectura en los servicios.
La comprobación de Django es estricta: cualquier advertencia implica fallo.
El JSON no guarda stdout/stderr ni secretos; el archivo se crea con modo 0600,
sin sobrescribir evidencia previa. Un modo estático correcto nunca se presenta
como validación productiva completa.

Este validador comprueba configuración, infraestructura, migraciones y salud;
no sustituye QA manual de login/logout, permisos, caja, pagos y facturación,
pruebas de restauración o aceptación del equipo.

## Pasos restantes de cierre

1. Validación funcional local por Guillermo y revisión del contrato con Axel.
2. Resolver configuración HTTPS y fortaleza de clave para producción estricta.
3. Tras autorización explícita, desplegar una revisión aprobada con backups y
   etiqueta verificable mediante el procedimiento de `docs/deployment_vm.md`.
4. Repetir el validador sobre esa revisión y el QA manual de los flujos del sprint 5.
5. Entregar evidencia a Axel para el cierre de QA, Jira y release del equipo.
