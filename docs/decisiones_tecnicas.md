# Decisiones Técnicas — Global Exchange

> Decisiones confirmadas por el equipo, verificadas en código rama `frontend-integration`, HEAD `590f131`.

## 1. Identidad: Keycloak como proveedor único

- **Decisión:** Django NO crea usuarios directamente. Todo registro, login, logout, verificación de correo y roles se externalizan a Keycloak vía OIDC (Authorization Code + PKCE).
- **Estado:** Implementado y verificado.
- **Fuente:** ERS 2.0 (RNF-02), decisión del equipo.

## 2. Usuario ≠ Cliente

- **Decisión:** El usuario que accede al sistema (identidad Keycloak) es distinto de la persona física o jurídica (Cliente) en cuyo nombre se opera. Un usuario puede estar asociado a múltiples clientes y debe seleccionar contexto.
- **Estado:** Implementado con `UsuarioCliente` y mecanismo de selección en sesión.
- **Fuente:** ERS 2.0, NCR.

## 3. Tasa externa de referencia vs tasa comercial propia

- **Decisión:** Existen dos tipos de tasa. La externa es referencia; la comercial es propia y es la que rige al confirmar una operación.
- **Estado:** Implementado (`TasaReferencia` de proveedor externo, `TasaComercial` con versionado).
- **Fuente:** ERS 2.0 (RN1–RN3).

## 4. Baja lógica en clientes

- **Decisión:** La baja de un cliente es lógica (estado → INACTIVO), no física. El registro se conserva para auditoría.
- **Estado:** Implementado.
- **Fuente:** ERS 2.0.

## 5. Versionado de tasas comerciales

- **Decisión:** Las tasas comerciales se versionan. Al modificar una tasa vigente, el registro anterior se desactiva (`vigente=False`) y se crea uno nuevo con `version + 1` dentro de `transaction.atomic` + `select_for_update` para garantizar atomicidad.
- **Estado:** Implementado.
- **Fuente:** Diseño del equipo.

## 6. Frontend React como islas dentro de Django

- **Decisión:** React convive con Django como capa visual de islas. Django conserva rutas, templates base, sesión, Keycloak, roles, permisos y lógica de negocio. Los bundles se generan en `static/react/`.
- **Estado:** Compilado pero no montado en templates Django actuales. La Landing y el panel usan server-side.
- **Fuente:** Decisión del equipo 2026-09-03.

## 7. GitFlow: feature → develop → main → tag

- **Decisión:** Las features nacen de `develop`, se prueban y revisan antes de integrarse. `main` se cierra con tag de release. No se desarrolla directamente en `main`.
- **Estado:** Implementado; Sprint 1 cerrado en `main` con tag `v1.0.0`.
- **Fuente:** Guía del equipo, AGENTS.md.

## 8. Backend siempre valida autorización

- **Decisión:** Ocultar opciones de UI no basta. El backend valida roles y permisos en cada endpoint. Decoradores centralizados en `usuarios/decorators.py`.
- **Estado:** Implementado.
- **Fuente:** ERS 2.0 (RNF-02).

## 9. Dual HTML/JSON para métodos de pago

- **Decisión:** `metodos_pago` usa un patrón dual: detecta `Accept` o `Content-Type` para devolver JSON o HTML sobre las mismas URLs. Esto permite usar la misma ruta tanto para la interfaz del panel como para consumo JavaScript.
- **Estado:** Implementado.
- **Fuente:** Decisión técnica del equipo.

## 10. No incluir secrets en documentación

- **Decisión:** Las variables sensibles (SECRET_KEY, KEYCLOAK_CLIENT_SECRET, DB_PASSWORD, etc.) se documentan por su nombre y función, pero nunca por su valor. El archivo `.env` está en `.gitignore`.
- **Estado:** Política vigente.
- **Fuente:** AGENTS.md, buenas prácticas.

## 11. Refactor de nomenclatura figma→frontend

- **Decisión:** Renombrar toda la capa de presentación de "figma" a "frontend" para reflejar que el panel pertenece a la capa frontend del proyecto, no al nombre del proyecto de diseño Figma.
- **Estado:** Commit `590f131` (40 archivos, 2026-09-06). Sin cambios funcionales.
- **Exclusiones:** `frontend/src/` + `static/react/` (bundle React), `front_actualizado/` (referencia), `AGENTS.md`/`.agent-context/`.
- **Fuente:** Decisión del equipo.

## Decisiones pendientes de confirmación

- **Integración de `frontend-integration` a `develop`:** pendiente de aprobación y merge.
- **Limpieza de archivos React/TypeScript/Vite:** pendiente de decisión separada (código compilado sin uso actual).
- **Permisos granulares (policies/scopes):** definidos en diseño pero no implementados.
- **Alta administrativa de usuarios y correo de verificación:** no dispara automáticamente el envío.
