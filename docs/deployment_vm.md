# Despliegue en una VM Linux

Esta guía describe el Compose productivo oficial. Nginx es la única entrada
pública: Django, Keycloak y PostgreSQL permanecen en la red interna de Docker.
El puerto de administración/health `9000` de Keycloak nunca se publica.

## Requisitos

- VM Linux con Docker Engine y el complemento Docker Compose.
- Repositorio clonado en la VM.
- Puertos del firewall definidos según el modo elegido.
- Un archivo `.env.production` creado desde `.env.production.example`, fuera
  del control de versiones y con secretos aleatorios.

No se debe copiar `.env.production` desde una estación compartida ni guardar
certificados o copias de base de datos en Git.

## Configuración común

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Sustituir todos los marcadores `REEMPLAZAR_*` y `CAMBIAR_*`. Estas variables
deben describir una única topología coherente:

| Ajuste | Debe coincidir con |
|---|---|
| `DJANGO_ALLOWED_HOSTS` | host público de la aplicación |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | origen completo de la aplicación |
| `BACKEND_PUBLIC_URL` | URL pública de la aplicación, sin barra final |
| `OIDC_CALLBACK_URL` | `BACKEND_PUBLIC_URL` + `/callback/` |
| `KEYCLOAK_PUBLIC_URL` | URL que utiliza el navegador para Keycloak |
| `KEYCLOAK_EXPECTED_ISSUER` | `KEYCLOAK_PUBLIC_URL` + `/realms/global-exchange` |
| `NGINX_APP_HOST` | host, sin esquema, de la aplicación |
| `NGINX_KEYCLOAK_HOST` | host, sin esquema, de Keycloak |

La comunicación servidor a servidor conserva siempre
`KEYCLOAK_INTERNAL_URL=http://keycloak:8080`; no se reemplaza por la URL
pública.

## Opción A: demostración HTTP por IP o hostname

Usar `NGINX_TLS_ENABLED=false`. Para una sola IP, asignar esa IP a
`NGINX_APP_HOST`, `NGINX_KEYCLOAK_HOST` y `DJANGO_ALLOWED_HOSTS`. Las URL son:

- aplicación: `http://IP_O_HOST`;
- Keycloak: `http://IP_O_HOST:8080`.

Mantener cookies seguras, redirección SSL, HSTS y proxy HTTPS desactivados.
Abrir en el firewall únicamente TCP 80 y 8080 para la audiencia de la demo;
restringir SSH a las direcciones administrativas. No abrir 8000, 5432 ni
9000.

Para incluir el buzón de demostración Mailpit, limitado al loopback de la VM:

```bash
docker compose --env-file .env.production -f compose.prod.yaml --profile demo up --build -d
```

Se consulta desde la propia VM o mediante un túnel SSH al puerto configurado;
no debe exponerse públicamente.

## Opción B: HTTPS por dominio

Configurar DNS para los hosts de aplicación y Keycloak. Copiar un certificado
que cubra ambos nombres a:

```text
docker/nginx/certs/fullchain.pem
docker/nginx/certs/privkey.pem
```

Los archivos están ignorados por Git. Restringir la clave privada a lectura
del administrador de la VM y del contenedor. Aplicar en `.env.production` los
valores HTTPS comentados al final del ejemplo: `NGINX_TLS_ENABLED=true`, URLs
`https://`, cookies seguras, `DJANGO_BEHIND_HTTPS_PROXY=true`, redirección SSL
y HSTS. Para la primera comprobación puede mantenerse HSTS en `0`; habilitar
un valor largo solo después de verificar certificado, hosts y subdominios.

Abrir TCP 80 y 443. Nginx redirige HTTP a HTTPS. No abrir 8000, 8080, 5432 ni
9000. La terminación TLS ocurre en Nginx; este sobrescribe los encabezados
`X-Forwarded-*` antes de pasarlos a Django o Keycloak.

## Correo

Mailpit es solo un perfil de demo. Un despliegue real debe establecer
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL` con su relay
SMTP y configurar el SMTP del realm de Keycloak con el mismo proveedor desde
la consola administrativa. No iniciar el perfil `demo` en ese escenario.

## Despliegue y comprobación

Antes de levantar servicios, validar la interpolación:

```bash
docker compose --env-file .env.production -f compose.prod.yaml config --quiet
```

Levantar el stack sin Mailpit:

```bash
docker compose --env-file .env.production -f compose.prod.yaml up --build -d
docker compose --env-file .env.production -f compose.prod.yaml ps
docker compose --env-file .env.production -f compose.prod.yaml logs --tail=100 nginx web keycloak
```

Comprobar Django dentro de la red y después las URLs públicas:

```bash
docker compose --env-file .env.production -f compose.prod.yaml exec web python manage.py check --deploy
set -a
. ./.env.production
set +a
curl -I "$BACKEND_PUBLIC_URL/"
curl -I "$KEYCLOAK_PUBLIC_URL/realms/global-exchange/.well-known/openid-configuration"
```

El servicio `keycloak-web-config` actualiza idempotentemente el cliente
`global-exchange-web` para realms nuevos o ya persistidos: URLs base, callback,
orígenes, logout, Authorization Code y PKCE S256.

## Actualización y rollback

Crear copias de ambas bases antes de actualizar. Luego obtener la versión
autorizada, reconstruir y revisar salud/logs. No usar `down --volumes`.

Si una versión falla, volver al commit/tag previamente aprobado, reconstruir
las imágenes y levantar el mismo volumen. Si hubo una migración incompatible,
restaurar ambas bases desde copias de la misma fecha; no mezclar un realm de
Keycloak nuevo con una base Django anterior.

## Backup

Crear un directorio privado fuera del repositorio. Los siguientes comandos
generan backups en formato custom de PostgreSQL:

```bash
mkdir -p ../global-exchange-backups
chmod 700 ../global-exchange-backups
docker compose --env-file .env.production -f compose.prod.yaml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > ../global-exchange-backups/django.dump
docker compose --env-file .env.production -f compose.prod.yaml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d keycloak -Fc' > ../global-exchange-backups/keycloak.dump
```

Comprobar que ambos archivos existen, no están vacíos y pueden listarse con
`pg_restore --list`. Cifrar y copiar fuera de la VM según la política del
equipo. El volumen persistente no sustituye un backup.

## Restore

La restauración reemplaza datos. Hacerla solo durante una ventana autorizada,
con una copia adicional del estado actual y con `web`, `nginx`, `keycloak` y
`keycloak-config` detenidos:

```bash
docker compose --env-file .env.production -f compose.prod.yaml stop nginx web keycloak keycloak-config
docker compose --env-file .env.production -f compose.prod.yaml exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < ../global-exchange-backups/django.dump
docker compose --env-file .env.production -f compose.prod.yaml exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d keycloak --clean --if-exists --no-owner' < ../global-exchange-backups/keycloak.dump
docker compose --env-file .env.production -f compose.prod.yaml up -d
```

Después verificar migraciones, login/logout, callback OIDC y envío de correo.
Probar periódicamente el procedimiento en un entorno aislado; un backup no
probado no garantiza recuperación.
