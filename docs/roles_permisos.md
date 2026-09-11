# Roles y permisos — Global Exchange

> Matriz alineada con ERS, Jira y backend el 10/09/2026.

Los únicos roles de negocio son `USUARIO`, `CAJERO`, `ANALISTA_CAMBIARIO` y `ADMINISTRADOR`. Los roles técnicos de Keycloak no son actores funcionales.

| Función hasta Sprint 2 | USUARIO | CAJERO | ANALISTA | ADMIN |
|---|:---:|:---:|:---:|:---:|
| Perfil, login, logout y sesión | Sí | Sí | Sí | Sí |
| Tasas de referencia y simulador HU-19 | Sí | Sí | Sí | Sí |
| Monedas activas | Sí | Sí | Sí | Sí |
| Clientes asociados y selección | Sí | Sí | Sí | Sí |
| CRUD global de clientes | — | — | — | Sí |
| Segmentar clientes | — | — | — | Sí |
| Asociar usuario–cliente | — | — | — | Sí |
| CRUD de usuarios y roles | — | — | — | Sí |
| Administrar monedas | — | — | — | Sí |
| Administrar tasas comerciales | — | — | Sí | — |
| Histórico comercial | — | — | Sí | Sí |
| Administrar métodos de pago | — | — | — | Sí |

Las tasas de referencia, el catálogo de monedas activas y el simulador basado en referencia también son públicos. Visitante y usuario autenticado comparten el endpoint y la lógica de HU-19; el simulador no requiere cliente ni tipo de operación. Esto no abre endpoints de administración.

En la interfaz autenticada, `Conversor` y `Mi cliente` se muestran únicamente al rol efectivo `USUARIO`. `CAJERO` y `ANALISTA_CAMBIARIO` no reciben esos accesos en sidebar ni navbar. Las rutas compartidas continúan técnicamente protegidas por la autorización existente; esta decisión de experiencia no amplió ni restringió permisos backend.

La autorización es RBAC de aplicación a partir de roles de realm validados en el token. La ERS usa la expresión “roles y permisos”, pero el alcance funcional verificado de Sprint 1 no demuestra un criterio que obligue a adoptar Authorization Services, policies o scopes de Keycloak. Esa ampliación arquitectónica no se realizó.

Funciones como operaciones, transacciones, pagos reales, cajas, arqueos, ganancias, reportes, facturación y notificaciones pertenecen a Sprints futuros. En navegación se presentan como `Pendiente` o no se muestran; no conceden acceso accidental.

El logout actual limpia la sesión Django y redirige al endpoint OIDC de cierre de sesión de Keycloak. La sesión server-side renueva tokens mediante refresh token sin exponerlos al navegador.
