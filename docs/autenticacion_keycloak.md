# Autenticación Keycloak — Global Exchange

> Estado real verificado, rama `frontend-integration`, HEAD `590f131`.

## Identidad: Keycloak como proveedor único

Global Exchange **no crea usuarios directamente**. Toda identidad (registro, login, logout, verificación de correo, roles) vive en Keycloak. Django gestiona la sesión local y valida tokens JWT.

## Flujo OIDC

```
Usuario → Django (login/) → Keycloak (OIDC Authorization Code + PKCE)
  → Keycloak autentica → redirige a callback/ con code + state
  → Django intercambia code por token (S256 verifier)
  → Valida token RS256: issuer, audience, expiración, JWKS
  → Guarda claims en sesión (sub, email, nombre, roles, realm)
  → Redirige a panel/ o destino configurado
```

### PKCE (Proof Key for Code Exchange)

- `code_verifier` aleatorio generado en login, almacenado en sesión.
- `code_challenge = S256(code_verifier)` enviado a Keycloak.
- En callback se verifica el `state` y se intercambia el código con el `code_verifier`.

### Validación del token

- **Firma**: RS256, validada contra JWKS del realm (`/.well-known/openid-configuration` → `jwks_uri`).
- **Issuer**: `KEYCLOAK_EXPECTED_ISSUER` (default `http://localhost:8080/realms/global-exchange`).
- **Audience**: `KEYCLOAK_CLIENT_ID` (default `global-exchange-web`).
- **Expiración**: verificada automáticamente por PyJWT.

## Configuración Keycloak

| Campo | Valor (dev) |
|---|---|
| Realm | `global-exchange` |
| Client ID (web) | `global-exchange-web` |
| Client ID (admin API) | `global-exchange-admin-api` |
| Auth server | `http://localhost:8080` |
| Expected issuer | `http://localhost:8080/realms/global-exchange` |
| Realm export | `keycloak/global-exchange-realm.json` |

Las credenciales están en `.env` y no se exponen en documentación pública.

## Servicio Admin API (`usuarios/services/keycloak.py`)

Cliente HTTP que usa `KEYCLOAK_ADMIN_CLIENT_ID` y `KEYCLOAK_ADMIN_CLIENT_SECRET` para obtener un token de servicio (client_credentials) y ejecutar operaciones administrativas:

- Listar usuarios del realm
- Crear usuario (con contraseña temporal)
- Editar atributos de usuario
- Deshabilitar usuario
- Asignar/quitar roles de realm

## Decoradores de autorización (`usuarios/decorators.py`)

| Decorador | Comportamiento |
|---|---|
| `@requiere_autenticacion` | Verifica sesión activa; si no, redirige a login OIDC |
| `@requiere_rol(rol)` | Verifica que el usuario tenga el rol indicado; 403 si no |
| `@requiere_alguno_de_roles(*roles)` | Verifica al menos uno de los roles indicados |
| `@requiere_roles_web` | Para endpoints web que requieren al menos un rol en panel |

Estos decoradores se aplican a vistas API y web. **Backend siempre valida**; ocultar opciones de UI no es suficiente.

## Roles de negocio

| Rol | Acceso principal |
|---|---|
| `ADMINISTRADOR` | Todo el panel: usuarios, clientes, monedas, métodos de pago, tasas (lectura), roles |
| `ANALISTA_CAMBIARIO` | Tasas comerciales (escritura), tasas de referencia (lectura), simulador |
| `CAJERO` | Panel general (pendiente de cajas) |
| `USUARIO` | Consulta básica del panel |

Los roles se configuran en el realm de Keycloak y se asignan a usuarios. El backend los lee del token JWT (claim `realm_access.roles`).

## Sesión Django

| Configuración | Valor |
|---|---|
| `SESSION_COOKIE_HTTPONLY` | `True` |
| `SESSION_COOKIE_SECURE` | `False` (dev) |
| `SESSION_COOKIE_SAMESITE` | `Lax` |
| `CSRF_COOKIE_SECURE` | `False` (dev) |

La sesión Django almacena los claims del token para acceso rápido sin reconsultar Keycloak.

## Límites conocidos

- **No hay permisos granulares** (policies/scopes de negocio). Solo roles a nivel de realm.
- El alta administrativa de usuarios **no dispara automáticamente el correo de verificación**; el autorregistro externo sí.
- No hay invalidación de sesión en Keycloak al hacer logout desde Django (solo sesión local se destruye).
