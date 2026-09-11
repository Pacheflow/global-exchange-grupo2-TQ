# Autenticación Keycloak — Global Exchange

## Identidad y flujo OIDC

Keycloak es la fuente de identidad y roles. Django usa Authorization Code con
PKCE, valida el `state` y canjea el código desde el backend. El navegador nunca
recibe ni almacena los tokens.

```text
Navegador → Django /login/ → Keycloak
  → callback con code + state
  → Django canjea code + PKCE verifier
  → valida access token (RS256, issuer, azp/audience, exp y usuario verificado)
  → guarda identidad, roles, id token y refresh token en la sesión Django
  → antes de vencer el access token, Django renueva y revalida los claims
```

## Access token, refresh token y sesión Django

- El access token es corto y solo se usa en el backend para validar los claims.
  No se guarda en la sesión.
- El refresh token se guarda exclusivamente en la sesión server-side. No se
  incluye en HTML, JSON, JavaScript, URLs ni logs.
- `oidc_expires_at` conserva el `exp` del access token actual. Ya no determina
  por sí solo la duración de la sesión Django.
- Cuando faltan `OIDC_REFRESH_MARGIN_SECONDS` o menos para `exp`, Django llama
  al token endpoint con `grant_type=refresh_token`.
- Cada access token renovado pasa por la misma validación JWT que el inicial;
  la identidad y los roles se vuelven a obtener de sus claims.
- Si Keycloak rota el refresh token, Django reemplaza el anterior. El id token
  también se actualiza cuando la respuesta incluye uno nuevo.

La política local usa `OIDC_SESSION_IDLE_SECONDS` (1800 por defecto) y la limita
al `refresh_expires_in` informado por Keycloak. La cookie/sesión se prolonga al
renovar correctamente, no en cada request. Keycloak conserva la autoridad real:
su timeout idle, su lifespan máximo, el cierre de SSO, la deshabilitación del
usuario o un refresh inválido hacen fallar la renovación. Django entonces limpia
todo el contexto OIDC y exige autenticación nueva.

No se intenta calcular localmente el máximo absoluto de SSO: Keycloak lo aplica
al token endpoint. Un cliente antiguo sin refresh token conserva el comportamiento
compatible y solo es válido hasta el `exp` de su access token.

| Variable | Default | Propósito |
|---|---:|---|
| `OIDC_REFRESH_MARGIN_SECONDS` | 60 | Anticipación para renovar |
| `OIDC_SESSION_IDLE_SECONDS` | 1800 | Límite local renovable de inactividad |

## Expiración y respuestas

Las rutas bajo `/api/` responden `401` con
`{"error": "Autenticación requerida"}` cuando la sesión no puede renovarse.
No inician un redirect OIDC. El JavaScript compartido muestra un mensaje de
sesión expirada y vuelve de forma controlada a `/login/`.

Las vistas HTML protegidas mantienen el redirect `302` a login. Una falta de
rol devuelve `403`: JSON en APIs y página HTML en vistas web.

## Logout

Django conserva el `id_token` como hint para el logout OIDC. Al salir ejecuta
`request.session.flush()`, que elimina identidad, claims, roles, expiraciones,
id token y refresh token, y luego redirige al endpoint de logout de Keycloak.

## Roles de negocio y rol por defecto

Los únicos roles de negocio son `USUARIO`, `CAJERO`, `ANALISTA_CAMBIARIO` y
`ADMINISTRADOR`. El backend solo acepta esos valores desde
`realm_access.roles`.

`default-roles-global-exchange` es un rol composite y contiene `USUARIO`.
Por eso una cuenta nueva recibe `USUARIO` como rol **efectivo heredado**, aunque
la consola no lo muestre como asignación directa. No corresponde asignarlo de
nuevo usuario por usuario mediante Admin API.

Un alta con `CAJERO`, `ANALISTA_CAMBIARIO` o `ADMINISTRADOR` suma ese rol directo
al `USUARIO` heredado. Ninguno de esos tres roles elevados se hereda por defecto.
El export `keycloak/global-exchange-realm.json` y el reconciliador
`docker/keycloak/configure-admin-client.sh` mantienen esta composición de forma
reproducible.

## Seguridad preservada

- PKCE S256 y validación de `state` siguen activos.
- Todo access token inicial o renovado valida firma, issuer, audiencia/`azp`,
  expiración y correo verificado.
- Los tokens quedan fuera de respuestas, almacenamiento web y logs.
- Los secretos administrativos se toman de settings y no están documentados.
