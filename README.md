# global-exchange

## Verificación de correo de usuarios (HU-02)

La aplicación utiliza Keycloak como proveedor de identidad para gestionar el registro y la verificación de correo de los usuarios.

## Configuración implementada

- Realm configurado: `global-exchange`

- Verificación de correo habilitada en Keycloak.

- Servidor SMTP configurado mediante Mailpit.

- Host SMTP: `mailpit`

- Puerto SMTP: `1025`

- Correo remitente: `noreply@globalexchange.com`

## Flujo de verificación

1. El usuario inicia el registro desde la aplicación.

2. Django redirige el proceso de registro hacia Keycloak.

3. Keycloak crea la cuenta del usuario.

4. Keycloak envía un correo de verificación.

5. El usuario abre el enlace recibido.

6. La cuenta queda marcada como verificada.

## Entorno de pruebas

Los correos enviados por Keycloak pueden visualizarse mediante Mailpit:

http://localhost:8025

## Configuración persistente

La configuración del Realm se encuentra exportada en:

```text
keycloak/global-exchange-realm.json
```

y es cargada automáticamente mediante Docker Compose:

```powershell
docker compose up -d
```

# Global Exchange

## Entorno completo con Docker

No es necesario instalar Python ni PostgreSQL en la computadora. El entorno incluye:

- Django sobre Python 3.13.

- PostgreSQL 17 con almacenamiento persistente.

- Keycloak 26.7.2 conectado a PostgreSQL.

- Instalación automática de dependencias Python.

- Migraciones automáticas de Django.

- Importación automática del realm de Keycloak durante el primer inicio.

## Inicio rápido

1. Instalar e iniciar Docker Desktop.

2. Opcionalmente, copiar `.env.example` como `.env` y cambiar las contraseñas.

3. Desde la raíz del repositorio ejecutar:

```powershell
docker compose up --build -d
```

4. Consultar el estado:

```powershell
docker compose ps
docker compose logs -f web
```

La aplicación queda disponible en:

```text
http://localhost:8000
```

y Keycloak en:

```text
http://localhost:8080
```

Para ejecutar comandos Django:

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
```

## Fuente de verdad del entorno de desarrollo

El entorno oficial y reproducible del proyecto es Docker Compose. Django,
PostgreSQL, Keycloak y Mailpit deben ejecutarse como servicios del mismo entorno.

El comando oficial para ejecutar la suite completa es:

```powershell
docker compose exec web python manage.py test
```

Al ejecutarlo, Django utiliza el host interno `postgres:5432`, crea la base temporal
de pruebas en el PostgreSQL del contenedor y la elimina al finalizar.

No se debe asumir que `python manage.py test` ejecutado directamente desde Windows
es equivalente. Una configuración local con `DB_HOST=localhost` puede conectarse a
un PostgreSQL instalado en Windows y producir resultados distintos a los de la
aplicación ejecutada con Docker.

Para automatización o terminales sin TTY se puede usar la variante:

```powershell
docker compose exec -T web python manage.py test
```

Las cuentas de la aplicación se administran mediante Keycloak. No es necesario
crear superusuarios de Django para utilizar Global Exchange.

## Documentación automática del código (pdoc)

La documentación API en HTML se genera con `pdoc` a partir de los módulos
reales de las aplicaciones `usuarios`, `clientes`, `monedas`, `metodos_pago`,
`tasas` y de `config`.

Para regenerarla dentro del contenedor oficial:

```powershell
docker compose exec web python scripts/generate_docs.py
```

La documentación cubre modelos, vistas, servicios, funciones auxiliares y
clases principales. No documenta migraciones, archivos generados,
`__pycache__` ni archivos temporales. La salida queda en:

```text
docs/generated/
```

El script configura el entorno Django antes de invocar `pdoc.pdoc()`, por lo
que no requiere PostgreSQL ni Keycloak para importar los módulos.

## Producción en una VM

Producción utiliza un Compose separado con Gunicorn, WhiteNoise, PostgreSQL
persistente, Keycloak en modo `start` y Nginx como única entrada pública. Los
servicios `web`, `keycloak` y `postgres` no publican puertos del host.

El despliegue admite dos configuraciones controladas por entorno:

- demostración HTTP por IP/hostname (aplicación en 80 y Keycloak detrás de
  Nginx en 8080);
- HTTPS por dominios (aplicación y Keycloak por virtual hosts en 443).

Inicio básico, después de copiar y completar `.env.production.example`:

```bash
docker compose --env-file .env.production -f compose.prod.yaml config --quiet
docker compose --env-file .env.production -f compose.prod.yaml up --build -d
docker compose --env-file .env.production -f compose.prod.yaml ps
```

Mailpit no forma parte del stack real. Solo se habilita para una demostración
con `--profile demo`. La guía completa de variables, certificados, firewall,
correo, validación, actualización, rollback, backup y restore está en
[docs/deployment_vm.md](docs/deployment_vm.md).

Para detener los contenedores conservando el volumen:

```bash
docker compose --env-file .env.production -f compose.prod.yaml down
```

No usar `down --volumes` en producción: elimina los datos persistentes.

---

# Autenticación y usuarios

## HU-01 - Registro de usuario

### Descripción

El registro de usuarios se realiza mediante Keycloak como proveedor externo de identidad.

La aplicación Django no crea usuarios directamente, sino que redirige al usuario hacia el formulario de registro administrado por Keycloak.

### Flujo de registro

1. El usuario accede a la opción de registro desde la aplicación.

2. Django genera la URL de registro de Keycloak.

3. El usuario completa sus datos en Keycloak.

4. Keycloak procesa la creación del usuario.

5. El usuario queda registrado en el Realm configurado.

### Configuración utilizada

- Proveedor de identidad: Keycloak.

- Realm: `global-exchange`.

- Cliente: `global-exchange-web`.

- Flujo utilizado: OpenID Connect Authorization Code Flow.

### Implementación

La lógica del registro se encuentra en:

```text
usuarios/views.py
```

La función `registro()` genera la URL de registro de Keycloak utilizando la configuración definida en Django.

### Pruebas realizadas

Se implementaron pruebas automáticas para verificar:

- Existencia de la ruta de registro.

- Redirección hacia Keycloak.

- Uso del endpoint correcto.

- Uso del cliente configurado.

- Parámetros necesarios del flujo OpenID Connect.

Resultado:

**7 tests ejecutados correctamente.**

---

## Evidencias

### HU-01

Las evidencias de la prueba manual del registro se encuentran en:

```text
docs/evidencias/HU-01/
```

Incluyen:

- Registro mediante Keycloak.

- Usuario creado correctamente.
