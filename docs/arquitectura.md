# Arquitectura — Global Exchange

> Documentación técnica derivada del estado real verificado.
> Rama `fix/keycloak-session-and-default-role`, HEAD `9085a47`.
> Última actualización: 2026-09-11.

## Stack de tecnología

| Capa | Tecnología |
|---|---|
| Backend | Django 6.1 (Python 3.13) |
| Persistencia | PostgreSQL 17 (Psycopg 3) |
| Identidad / IAM | Keycloak 26.7.2 (OIDC Authorization Code + PKCE, JWT RS256/JWKS, Admin API) |
| Frontend activo | Templates Django + HTML + `static/js/*` + `static/css/*` (Material, CSS lineal) |
| Correo (pruebas) | Mailpit (SMTP interno, puerto 1025) |
| Orquestación | Docker Compose (dev: `compose.yaml`) |
| Producción local | Gunicorn + WhiteNoise + `compose.prod.yaml`, validada localmente; no equivale a producción pública endurecida |

## Aplicaciones Django

| App | Función | Modelos |
|---|---|---|
| `usuarios` | Identidad OIDC, login/logout, dashboard, CRUD de usuarios vía Keycloak Admin API | Ninguno (identidad vive en Keycloak) |
| `clientes` | CRUD de clientes, baja lógica, segmentación, asociación Usuario–Cliente | `CategoriaCliente`, `Cliente`, `UsuarioCliente` |
| `monedas` | Catálogo de monedas (escritura ADMINISTRADOR, lectura de activas todos los roles) | `Moneda` |
| `metodos_pago` | Métodos de pago por cliente (dual HTML/JSON, ADMINISTRADOR) | `MetodoPago` |
| `tasas` | Tasas de referencia (proveedor externo), tasas comerciales (versionado), simulador de conversiones | `ConsultaProveedorTasas`, `TasaReferencia`, `TasaComercial` |

## Grafo de dependencias entre apps

```
usuarios (base, sin imports locales de negocio)
   ↑
   ├── clientes → usuarios (decorators, views)
   ├── monedas → usuarios
   ├── tasas → usuarios + monedas (FK Moneda en TasaReferencia y TasaComercial)
   └── metodos_pago → usuarios + clientes (FK Cliente)
```

## Montaje de URLs (`config/urls.py`)

| Prefijo | Destino |
|---|---|
| `admin/` | Django Admin |
| `clientes/` | `clientes.urls` (web: CRUD) |
| `api/clientes/` | `clientes.api_urls` (JSON API) |
| `api/usuarios/` | `usuarios.api_urls` (JSON API) |
| `api/monedas/` | `monedas.urls` (API JSON) |
| `api/metodos-pago/` | `metodos_pago.urls` (API JSON o HTML, dual) |
| `api/tasas/` | `tasas.urls` (API JSON) |
| (raíz) | `usuarios.urls` (web: home, OIDC, panel, screens) |

## Estructura de directorios

```
global-exchange/
├── config/                # Proyecto Django (settings, urls raíz, wsgi)
│   ├── settings.py        # Configuración principal, carga .env via load_dotenv
│   ├── urls.py            # Montaje de apps
│   └── wsgi.py
├── usuarios/              # App identidad
│   ├── views.py           # Home, OIDC login/callback/logout, dashboard, CRUD
│   ├── api_urls.py        # API JSON de usuarios
│   ├── keycloak.py        # Cliente Admin API + JWKS
│   ├── services/keycloak.py  # Servicio de tokens admin
│   ├── decorators.py      # requiere_autenticacion, requiere_rol, requiere_alguno_de_roles
│   ├── context_processors.py # Exposición de sesión a templates
│   ├── urls.py            # Rutas web
│   └── tests.py           # 110 métodos de test
├── clientes/              # App clientes
│   ├── models.py          # CategoriaCliente, Cliente, UsuarioCliente
│   ├── views.py           # CRUD web + API JSON
│   ├── forms.py           # ClienteForm, SegmentacionClienteForm, AsignacionUsuarioClienteForm
│   ├── urls.py            # Rutas web
│   ├── api_urls.py        # API JSON
│   └── tests.py           # ~60 métodos de test
├── monedas/               # App monedas
│   ├── models.py          # Moneda
│   ├── views.py           # API JSON (listar, crear, editar, estado)
│   ├── urls.py            # Todas API JSON
│   └── tests.py           # 17 métodos de test
├── metodos_pago/          # App métodos de pago
│   ├── models.py          # MetodoPago
│   ├── views.py           # Dual: HTML render o JSON según Content-Type/Accept
│   ├── urls.py            # Rutas compartidas (HTML o JSON)
│   └── tests.py           # 20 métodos de test
├── tasas/                 # App tasas
│   ├── models.py          # ConsultaProveedorTasas, TasaReferencia, TasaComercial
│   ├── providers.py       # ProveedorTasasHTTP (adaptador configurable)
│   ├── services.py        # consultar_tasas_referencia, actualizar_tasa_comercial
│   ├── simulador.py       # simular_conversion (cruces vía tasa base)
│   ├── views.py           # API JSON (consultar, comerciales, histórico, simular)
│   ├── urls.py            # Todas API JSON
│   ├── tests.py           # Tasas comerciales
│   ├── test_reference_rates.py
│   └── test_simulator.py  # 54 métodos de test en total
├── templates/
│   ├── frontend/          # Templates del panel (post refactor figma→frontend)
│   │   ├── base.html      # Shell del panel: CSS/JS, blocks (title, extra_head, sidebar, content, extra_js)
│   │   ├── partials/      # sidebar.html, sidebar_for_role.html, currency_grid.html
│   │   ├── components/    # icon.html, market_board.html, navbar.html
│   │   ├── dashboard_*.html  # Dashboards por rol (4)
│   │   ├── usuarios.html, clientes.html, monedas.html, tasas_comerciales.html,
│   │   │   tasas.html, simulador.html, pagos.html, cajas.html, roles_permisos.html
│   │   └── ...
│   └── usuarios/          # Templates públicas (landing, login, home, forbidden, etc.)
├── static/
│   ├── js/                # app.js, navbar.js, ge-data.js, ge-app.js, frontend.js,
│   │                      # frontend-api.js, clientes.js, usuarios.js, landing.js
│   ├── css/               # app.css, navbar.css, ge-app.css, frontend.css, landing.css
│   └── react/             # Artefacto heredado no cargado por templates activos
├── frontend/              # Fuente heredada no integrada al frontend activo
├── docker/                # entrypoint.sh, keycloak/
├── keycloak/              # Realm export JSON
├── docs/                  # Documentación, evidencias, docs IA
├── .agent-context/        # Memoria privada del agente (fuera de Git)
├── compose.yaml           # Dev: Django + PostgreSQL + Keycloak + Mailpit
├── Dockerfile             # python:3.13-slim, django user, entrypoint
├── requirements.txt       # django, psycopg, requests, pyjwt, whitenoise, gunicorn, pytest, cotton, material
└── pytest.ini             # DJANGO_SETTINGS_MODULE=config.settings
```

## Variables de entorno

Las variables se cargan desde `.env` (via `load_dotenv` en `config/settings.py`). Se cargan automáticamente por Compose. La documentación completa está en `.env.example`.

Grupos principales: DB, KEYCLOAK, OIDC, TASAS, SESSION, CSRF, DJANGO (ALLOWED_HOSTS, DEBUG, SECRET_KEY).

Producción (`DJANGO_ENVIRONMENT=production`) exige `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` y `DEBUG=false`.

## Servicios Docker Compose

| Servicio | Imagen / Rol | Puerto (dev) |
|---|---|---|
| `postgres` | postgres:17-alpine | interno |
| `mailpit` | axllent/mailpit | 8025 |
| `keycloak` | quay.io/keycloak/keycloak:26.7.2 | 8080 |
| `keycloak-config` | Ejecuta `configure-admin-client.sh` una vez | — |
| `web` | Django 6.1 (Dockerfile python:3.13-slim) | 8000 |

Entrypoint (`docker/entrypoint.sh`): espera PostgreSQL → migrate → runserver 0.0.0.0:8000. Healthcheck: HTTP 127.0.0.1:8000.

## Patrones de diseño

- **Sin modelos de usuario local**: identidad 100% en Keycloak; se referencia por `keycloak_user_id` (texto).
- **API dual (metodos_pago)**: detecta `_solicita_json(request)` (Content-Type/Accept) para devolver JSON o HTML sobre las mismas URLs.
- **Decoradores de autorización** centralizados en `usuarios/decorators.py`.
- **Frontend API**: `static/js/frontend-api.js` consume las rutas API declarando `data-ge-api="namespace"` en las templates; las URLs se inyectan desde Django `{% url %}`. CSRF vía cookie.
- **Frontend activo server-side**: las vistas renderizan Django Templates y el
  comportamiento interactivo usa JavaScript convencional. Los artefactos React
  heredados permanecen en el repositorio, pero ninguna template actual los carga.
