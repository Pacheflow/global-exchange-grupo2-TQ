# HU-40 y HU-41 — Saldos y movimientos de caja

## Alcance implementado

Esta entrega implementa el trabajo de Guillermo Benítez para el Sprint 4 sobre
la base de caja y apertura integrada previamente en `develop`:

- consulta del saldo actual de un período abierto, separado por moneda;
- ingreso y egreso manual por un cajero;
- validación de fondos antes de un egreso;
- trazabilidad de actor, fecha, motivo y origen;
- contrato interno para movimientos automáticos idempotentes;
- pantallas operativas y de supervisión;
- pruebas unitarias y documentación automática.

No implementa cierre, arqueo ni historial de períodos cerrados (HU-42/HU-43),
ni procesa pagos (HU-28). El servicio automático es el punto seguro de
integración que esos flujos podrán invocar cuando corresponda.

## Flujo funcional

### Consultar saldo (HU-40)

1. Un CAJERO abre una caja con el saldo inicial de cada moneda.
2. Desde **Cajas** selecciona **Consultar saldo**.
3. La pantalla muestra, por moneda, saldo inicial, ingresos, egresos y saldo
   actual, además del historial auditable de movimientos del período.
4. Un ADMINISTRADOR puede acceder a la misma consulta desde la gestión de
   cajas, pero no ve la acción para registrar movimientos.

La fórmula es independiente para cada moneda:

```text
saldo_actual(moneda) = saldo_inicial(moneda)
                     + suma(ingresos de esa moneda y período)
                     - suma(egresos de esa moneda y período)
```

No hay conversión entre USD, PYG u otras monedas, y nunca se incorporan datos
de otro período.

### Registrar movimiento manual (HU-41)

1. El CAJERO entra en una caja con período abierto.
2. Selecciona **Nuevo movimiento**.
3. Indica ingreso/egreso, una moneda de la apertura, monto positivo y motivo.
4. El backend vuelve a comprobar todos los datos y toma el actor de la sesión
   Keycloak, no del formulario.
5. Para un egreso recalcula el saldo bajo bloqueo. Si no alcanza, revierte y
   muestra un error; si alcanza, registra el movimiento y muestra el saldo.

Los registros no tienen acciones de editar o eliminar. El modelo también
rechaza `save()` sobre una instancia persistida y `delete()` directo.

## Diseño técnico

### Modelo

`MovimientoCaja` referencia mediante `PROTECT` a `PeriodoCaja` y `Moneda`. Usa
`DecimalField(max_digits=18, decimal_places=6)` y constraints de base de datos
para tipo, origen, monto, motivo y relación entre origen e idempotencia.

Los saldos derivados no se persisten. Esto evita dos fuentes de verdad: siempre
se calculan desde `SaldoInicialCaja` y el libro de `MovimientoCaja`.

### Servicios y atomicidad

`consultar_saldos_caja()` autoriza ADMINISTRADOR/CAJERO y calcula por período.

`registrar_movimiento_manual()` ejecuta `transaction.atomic()` y bloquea el
`PeriodoCaja` con `select_for_update()`. Todos los movimientos de un período se
serializan durante la validación/escritura, por lo que dos egresos concurrentes
no pueden aprobarse contra el mismo saldo anterior.

`registrar_movimiento_automatico()` aplica el mismo bloqueo y exige una
`clave_idempotencia` única. Repetir exactamente el mismo evento devuelve
`ResultadoMovimientoCaja(repetido=True)` sin duplicar el efecto. Reutilizar la
clave con período, moneda, tipo, monto o referencia distintos es un error.

### Seguridad

- El decorador web valida autenticación y rol efectivo.
- El servicio vuelve a validar rol e identidad (defensa en profundidad).
- ADMINISTRADOR consulta; CAJERO consulta y registra manualmente.
- Los campos de auditoría se obtienen de la sesión verificada.
- No existe endpoint de edición o eliminación de movimientos.
- CSRF protege el formulario POST.

## Rutas y archivos principales

| Elemento | Ubicación |
|---|---|
| Modelo y constraints | `cajas/models.py` |
| Migración | `cajas/migrations/0003_movimientocaja.py` |
| Cálculo y escrituras | `cajas/services.py` |
| Formulario | `cajas/forms.py` |
| Vistas y permisos | `cajas/views.py` |
| URLs | `cajas/urls.py` |
| UI | `templates/frontend/caja_saldo.html`, `caja_movimiento_form.html` |
| Pruebas | `cajas/test_saldos_movimientos.py` |

## Cómo probar manualmente

1. Iniciar el entorno: `docker compose up --build -d`.
2. Entrar a `http://localhost:8000` con un usuario cuyo rol efectivo sea
   `CAJERO`.
3. Abrir **Cajas** en el sidebar y registrar una apertura si no existe una.
4. Entrar a **Nuevo movimiento**, registrar un ingreso y comprobar que suma.
5. Registrar un egreso menor o igual al saldo y comprobar que resta.
6. Intentar un egreso mayor al saldo: debe informar fondos insuficientes y no
   crear el registro.
7. Cambiar a ADMINISTRADOR: debe poder consultar el saldo, pero la ruta de alta
   de movimiento responde 403.

## Cómo ejecutar las pruebas

Suite específica:

```bash
docker compose exec web python manage.py test cajas.test_saldos_movimientos
```

Todo el módulo:

```bash
docker compose exec web python manage.py test cajas
```

Suite completa y chequeo de migraciones:

```bash
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test
```

La documentación HTML se regenera con:

```bash
docker compose exec web python scripts/generate_docs.py
```

## Casos automatizados relevantes

- saldo inicial sin movimientos;
- separación estricta por moneda;
- suma de ingreso y resta de egreso;
- rechazo de saldo insuficiente;
- rechazo de período cerrado;
- permisos diferenciados de ADMINISTRADOR y CAJERO;
- actor de Keycloak e inmutabilidad;
- reintento automático idempotente;
- rechazo de una clave reutilizada con otro payload;
- formulario web y redirección al saldo actualizado.
