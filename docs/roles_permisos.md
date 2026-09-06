# Roles y Permisos — Global Exchange

> Estado real verificado, rama `frontend-integration`, HEAD `590f131`.

## Roles de negocio

Los cuatro roles se definen en el realm de Keycloak (`global-exchange`) y se leen del token JWT:

| Rol | Código en Keycloak | Acceso principal |
|---|---|---|
| Administrador | `ADMINISTRADOR` | Gestión total: usuarios, clientes, monedas, métodos de pago, tasas (lectura), roles |
| Analista Cambiario | `ANALISTA_CAMBIARIO` | Tasas comerciales (escritura y histórico), tasas de referencia (lectura), simulador |
| Cajero | `CAJERO` | Panel general (pendiente de cajas) |
| Usuario | `USUARIO` | Consulta básica del panel |

## Control de acceso

### Backend (decoradores)

El control de acceso se aplica en las vistas mediante decoradores centralizados en `usuarios/decorators.py`:

```python
@requiere_rol("ADMINISTRADOR")    # Verifica un rol específico
@requiere_alguno_de_roles(...)    # Verifica al menos uno
@requiere_autenticacion           # Solo requiere sesión activa
```

**Regla fundamental:** el backend siempre valida. Ocultar opciones de UI no es suficiente (RNF-02/ERS20).

### Acceso por endpoint (resumen)

| Recurso | Lectura | Escritura |
|---|---|---|
| Usuarios (CRUD) | ADMINISTRADOR | ADMINISTRADOR |
| Clientes (CRUD) | ADMINISTRADOR | ADMINISTRADOR |
| Selección de cliente | Cualquier rol autenticado | Cualquier rol autenticado |
| Monedas (listar) | Todos los roles | — |
| Monedas (crear/editar/estado) | — | ADMINISTRADOR |
| Métodos de pago (consultar) | Cualquier rol (filtrado por cliente en sesión) | — |
| Métodos de pago (registrar/editar/estado) | — | ADMINISTRADOR |
| Tasas de referencia | Todos los roles | — |
| Tasas comerciales (crear/modificar) | — | ANALISTA_CAMBIARIO |
| Tasas comerciales (histórico) | ADMINISTRADOR, ANALISTA_CAMBIARIO | — |
| Simulador | Todos los roles | — |
| Roles / Permisos (consulta) | ADMINISTRADOR | — (solo lectura) |

## Pantalla Roles / Permisos

`/roles-permisos/` (vista web, `ADMINISTRADOR`):
- Consulta los cuatro roles de negocio configurados en Keycloak.
- Indica si cada rol está configurado en el realm.
- **No modifica el realm** — es solo consulta informativa.

## Limitaciones conocidas

- **No hay permisos granulares** (policies, scopes, reglas por dominio). Solo roles a nivel de realm.
- No hay invalidación de sesión en Keycloak al hacer logout de Django.
- No hay control de acceso basado en recursos (ABAC/RBAC fina); el filtrado por cliente se hace a nivel de aplicación, no por permiso declarativo.
- Las identidades de prueba Keycloak se eliminan después de las verificaciones; no se mantienen permisos permanentes fuera de los roles de realm.
