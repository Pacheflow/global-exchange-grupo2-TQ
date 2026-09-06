# Documentación de uso de Inteligencia Artificial

**Proyecto:** Global Exchange

**Integrante:** Guillermo Benítez

**Historia de usuario:** HU-17 — Consultar y visualizar tasas

**Sprint:** 2 — Hito 4

---

## 1. Objetivo de esta documentación

Este documento registra el uso de Inteligencia Artificial como herramienta de apoyo durante el análisis, diseño, implementación y validación del backend de la **HU-17 — Consultar y visualizar tasas**.

La IA fue utilizada para interpretar la guía del Sprint 2, delimitar la responsabilidad de Guillermo, revisar la dependencia con HU-36, diseñar la integración con un proveedor externo, definir la persistencia y el fallback, implementar pruebas con mocks y documentar el contrato entregado al frontend.

Las decisiones finales fueron contrastadas con el código real. Las migraciones, pruebas y verificaciones fueron ejecutadas sobre el proyecto antes de considerar incorporadas las propuestas.

---

## 2. Historia de usuario trabajada

- **HU-17 — Consultar y visualizar tasas**
- Responsabilidad de Guillermo: backend completo.
- Dependencia directa: HU-36 — Configurar monedas.
- Integración posterior: HU-21 — Administrar tasas comerciales.
- Consumidor del contrato: frontend e integración asignados a Axel.

---

## 3. Registro de consultas realizadas a la IA

### Consulta 1 — Interpretación del alcance

**Pregunta realizada**

> Necesito crear la rama y trabajar sobre toda la implementación del trabajo que le tiene que tocar a Guillermo sobre HU-17.

**Respuesta / orientación obtenida**

Se analizó la guía entregada y se identificó que Guillermo debía realizar el backend completo: modelo, migración, proveedor externo desacoplado, configuración, validación, persistencia, fallback, endpoint, pruebas y documentación.

También se identificó que la pantalla de tasas corresponde a Axel y que la administración de tasas comerciales pertenece a HU-21.

**Aplicación en el proyecto**

Se creó la rama:

```text
feature/hu-17-consultar-visualizar-tasas
```

Los cambios locales anteriores fueron resguardados antes de cambiar de rama.

---

### Consulta 2 — Dependencia con el catálogo de monedas

**Pregunta realizada**

> ¿Cómo debe relacionarse HU-17 con la configuración de monedas ya implementada?

**Respuesta / orientación obtenida**

Se determinó que las tasas no debían utilizar códigos hardcodeados como entidades funcionales. La moneda base y cada moneda cotizada debían relacionarse mediante claves foráneas con `Moneda`.

Solo las monedas activas de HU-36 deben participar en nuevas consultas.

**Aplicación en el proyecto**

Los modelos `ConsultaProveedorTasas` y `TasaReferencia` se relacionaron con `Moneda`. El servicio utiliza `Moneda.objects.activas()` y controla que la moneda base exista y esté activa.

---

### Consulta 3 — Selección del proveedor externo

**Pregunta realizada**

> ¿Cuál es la API externa utilizada para consultar las tasas?

**Respuesta / orientación obtenida**

Se seleccionó el endpoint abierto de **ExchangeRate-API**:

```text
https://open.er-api.com/v6/latest/USD
```

Se recomendó no acoplar el caso de uso a esa URL, sino declararla mediante variables de entorno y encapsular la comunicación en un adaptador.

**Aplicación en el proyecto**

Se implementó `ProveedorTasasHTTP` y la URL configurable:

```env
TASAS_PROVIDER_URL=https://open.er-api.com/v6/latest/__BASE__
```

---

### Consulta 4 — Diseño de persistencia

**Pregunta realizada**

> ¿Cómo se puede persistir la última respuesta válida y conservar trazabilidad?

**Respuesta / orientación obtenida**

Se propuso separar dos conceptos:

- La respuesta externa válida recibida.
- El último valor normalizado disponible para cada par.

Esta separación permite mantener trazabilidad sin hacer costosa la consulta del dato vigente.

**Aplicación en el proyecto**

Se implementaron:

- `ConsultaProveedorTasas`: conserva la respuesta original válida.
- `TasaReferencia`: mantiene el último valor válido por par.

La persistencia se realiza dentro de una transacción atómica.

---

### Consulta 5 — Comportamiento ante fallos

**Pregunta realizada**

> ¿Qué debe responder el sistema si el proveedor falla?

**Respuesta / orientación obtenida**

Se definieron dos caminos:

1. Si existe un dato anterior válido, devolverlo claramente como desactualizado.
2. Si no existe información previa, devolver indisponibilidad.

No se deben devolver cero, valores fijos ni cotizaciones inventadas.

**Aplicación en el proyecto**

El servicio devuelve:

- `desactualizado` con HTTP 200 cuando existe fallback.
- `indisponible` con HTTP 503 cuando no existe fallback.

---

### Consulta 6 — Validación de la respuesta externa

**Pregunta realizada**

> ¿Qué errores del proveedor deben controlarse antes de guardar una tasa?

**Respuesta / orientación obtenida**

Se identificaron timeout, red, HTTP inválido, JSON inválido, estructura incompleta, moneda base incorrecta, monedas ausentes, fecha inválida y valores no numéricos, infinitos, cero o negativos.

**Aplicación en el proyecto**

El adaptador normaliza la respuesta en `RespuestaTasas`. Solo una respuesta completamente válida se entrega al servicio para persistencia.

---

### Consulta 7 — Contrato para el frontend

**Pregunta realizada**

> ¿Cómo debe exponerse la información sin confundir la referencia externa con la tasa comercial?

**Respuesta / orientación obtenida**

Se recomendó separar ambas colecciones en el contrato y acompañar cada referencia con tipo, par, fuente, fecha, vigencia e indicador de dato desactualizado.

**Aplicación en el proyecto**

Se creó el endpoint autenticado:

```http
GET /tasas/
```

La respuesta contiene `tasas_referencia` y `tasas_comerciales` como colecciones independientes. La segunda queda vacía hasta la integración de HU-21.

---

### Consulta 8 — Estrategia de pruebas

**Pregunta realizada**

> ¿Cómo se prueban los errores de un proveedor sin depender de Internet?

**Respuesta / orientación obtenida**

Se recomendó inyectar o sustituir la sesión HTTP y el adaptador mediante mocks. De esa manera cada escenario es determinístico y no depende de disponibilidad externa.

**Aplicación en el proyecto**

Se implementaron pruebas para:

- Respuesta exitosa.
- Timeout.
- Error HTTP.
- JSON inválido.
- Respuesta incompleta.
- Valores inválidos.
- Fecha inválida.
- Persistencia y actualización.
- Fallback y ausencia de datos.
- Catálogo de monedas incompleto.
- Autenticación y serialización del endpoint.

---

### Consulta 9 — Validación sobre el proyecto real

**Pregunta realizada**

> ¿Cómo se comprueba que la solución no rompe funcionalidades existentes?

**Respuesta / orientación obtenida**

Se propuso ejecutar las pruebas específicas, la regresión completa, la comprobación de Django, la validación de migraciones y una consulta real no persistente al proveedor.

**Aplicación en el proyecto**

Se obtuvieron los siguientes resultados:

| Comprobación | Resultado |
|---|---|
| Pruebas HU-17 | 16 aprobadas |
| Regresión completa | 127 aprobadas |
| Django system check | Sin observaciones |
| Migraciones pendientes | Ninguna |
| Consulta real al proveedor | Exitosa |

---

## 4. Decisiones finales incorporadas

- Utilizar `Decimal` para las tasas.
- Mantener el proveedor detrás de un adaptador.
- Configurar URL, credencial y timeout mediante entorno.
- Persistir únicamente respuestas completamente válidas.
- Conservar el último valor por par y el histórico de respuestas válidas.
- No inventar información cuando el proveedor está indisponible.
- Separar referencias externas de tasas comerciales.
- Mantener los tests independientes de Internet.
- Requerir una sesión OIDC válida para consultar el endpoint.

---

## 5. Archivos principales resultantes

```text
tasas/models.py
tasas/providers.py
tasas/services.py
tasas/views.py
tasas/urls.py
tasas/tests.py
tasas/migrations/0001_initial.py
docs/HU-17_Tasas_Referencia.md
docs/ia/Documentacion_IA_Guillermo_HU17.md
```

---

## 6. Resultado relevante

La IA permitió acelerar el análisis y revisar alternativas, pero las propuestas se validaron contra la guía, el catálogo de monedas existente, la arquitectura del repositorio y la ejecución real de pruebas.

El resultado incorporado es un backend desacoplado, persistente y verificable para HU-17, preparado para que el frontend consuma tasas reales y represente correctamente éxito, dato desactualizado e indisponibilidad.

---

## 7. Consideraciones de seguridad y privacidad

- No se registraron tokens ni credenciales reales en esta documentación.
- La clave opcional del proveedor debe permanecer en `.env`.
- Los mensajes externos se transforman en errores controlados.
- La documentación no contiene datos personales de usuarios.
- El endpoint reutiliza la autenticación OIDC del proyecto.
