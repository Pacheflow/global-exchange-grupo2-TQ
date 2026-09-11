# Sprint 1 — Estado verificado

> Revisión de código y requisitos realizada el 10/09/2026 sobre la rama de corrección vigente.

| HU | Funcionalidad | Estado |
|---|---|---|
| HU-01 | Autorregistro | Parcial: redirección al registro Keycloak y retorno OIDC implementados; la entrega real depende del SMTP configurado |
| HU-02 | Verificación de correo | Parcial: `verifyEmail` y acción `VERIFY_EMAIL` están configurados; el alta administrativa deja `emailVerified=false`, pero no solicita automáticamente el envío |
| HU-03 | Login, sesión y logout | Implementado: Authorization Code + PKCE, JWT RS256/JWKS, refresh server-side y cierre OIDC |
| HU-04 | Acceso por rol | Implementado para el alcance RBAC comprobado; no se infiere una obligación de policies/scopes granulares |
| HU-05 a HU-08 | Usuarios y roles | Implementado mediante Admin API de Keycloak |
| HU-09 a HU-12 | CRUD y baja lógica de clientes | Implementado |
| HU-13 | Segmentación de clientes | Implementado y restringido a ADMINISTRADOR según ERS/Jira |
| HU-14 | Asociación usuario–cliente | Implementado |
| HU-15 y HU-16 | Seleccionar/cambiar contexto | Implementado para todos los roles, limitado por asociación salvo ADMINISTRADOR |

## Observaciones abiertas

- Mailpit permite verificar el flujo en desarrollo, pero no demuestra entrega a correo externo.
- El reenvío explícito de correo de verificación no tiene una función propia en la aplicación; no se amplió el alcance sin un criterio de aceptación inequívoco.
- El alta administrativa y la verificación siguen siendo pasos separados.
- `pdoc` está incluido en dependencias, existe `scripts/generate_docs.py` y hay documentación generada; la nota histórica que lo marcaba ausente quedó obsoleta.
