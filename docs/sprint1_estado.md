# Sprint 1 — Estado Final

> Rama `frontend-integration`, HEAD `590f131`. Estado real verificado por código, pruebas y Jira.

## Resumen

El Sprint 1 está **funcionalmente completo**. Incluye la base técnica, identidad/Keycloak, usuarios, clientes, asociación Usuario–Cliente y la infraestructura Docker.

## HU implementadas

| HU | Funcionalidad | Estado real |
|---|---|---|
| HU-01 | Registro de usuario | Parcialmente implementado (flujo OIDC vía Keycloak; verificación de correo por Mailpit en dev) |
| HU-02 | Verificación de correo | Parcialmente implementado (flujo funcional con Mailpit; alta admin no dispara verificación) |
| HU-03 | Login SSO | Implementado (OIDC Authorization Code + PKCE, JWT RS256/JWKS, sesión, logout) |
| HU-04 | Accesos/roles | Parcialmente implementado (roles backend funcionales; sin permisos granulares policies/scopes) |
| HU-05 | Crear usuario | Implementado (vía Admin API Keycloak, mock en pruebas) |
| HU-06 | Editar usuario | Implementado |
| HU-07 | Baja de usuario | Implementado (deshabilitar en Keycloak) |
| HU-08 | Asignar rol | Parcialmente implementado (funcional; depende de roles existentes en realm) |
| HU-09 | Alta de cliente | Implementado (CRUD + API JSON) |
| HU-10 | Consulta de clientes | Implementado |
| HU-11 | Edición de cliente | Implementado |
| HU-12 | Baja de cliente | Implementado (baja lógica: estado → INACTIVO) |
| HU-13 | Segmentación | Implementado (categoría por cliente) |
| HU-14 | Asociación Usuario–Cliente | Implementado |
| HU-15 | Seleccionar cliente | Implementado |
| HU-16 | Cambiar cliente | Implementado |

## Tareas técnicas

| Elemento | Estado |
|---|---|
| TASK-01 Entorno de desarrollo | Configurado |
| TASK-02 Ambiente Docker | Configurado (PostgreSQL, Keycloak, Mailpit, Django) |
| TASK-03 GitFlow | Implementado (`feature → develop → main → tag`) |
| TASK-04 Pruebas unitarias | 201 tests detectados, 201 pasando (post-corrección) |
| TASK-05 Documentación técnica | Parcialmente (docs/ generada; pdoc no instalado) |
| TASK-06 QA y cierre | Pendiente de verificación integral |
| ASK-07 CHIA | Documentos en `docs/ia/` |

## Pruebas

- 201 tests ejecutados, 0 fallos (post-corrección 2026-09-06).
- `manage.py check`: 0 incidencias.
- `makemigrations --check --dry-run`: sin cambios.

## Git

- Cierre de Sprint 1 etiquetado como `v1.0.0` en commit `d7e8f8e` en rama `main`.
- `develop` en `943375b`, ancestro de `main`.

## Pendientes conocidos

- Permisos granulares (policies/scopes) no implementados.
- Verificación de correo por alta administrativa no dispara automáticamente el envío.
- pdoc no configurado ni generado; faltan 14 docstrings.
- E2E vivo con Keycloak real no verificado en la última sesión (servicios levantados en sesiones anteriores).
