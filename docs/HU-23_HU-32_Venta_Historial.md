# HU-23 Venta y HU-32/HU-24 Historial y detalle

## Alcance

Esta implementación cubre el trabajo asignado a Guillermo Benítez en el Sprint
3: venta de divisas, selección de métodos de pago y consulta segura del
historial y detalle. Reutiliza el núcleo transaccional compartido y no incorpora
procesamiento de pagos, caja, reportes ni exportaciones.

## Venta de divisas

En una operación `VENTA`, el cliente compra la moneda de origen a Global
Exchange. El servicio común selecciona `TasaComercial.venta`, calcula con
`Decimal`, descuenta la comisión correspondiente a la categoría del cliente y
devuelve una previsualización sin persistir.

Al confirmar, el backend vuelve a validar identidad Keycloak, cliente,
asociación `UsuarioCliente`, monedas, tasa vigente, método activo y comisión.
Luego recalcula y crea una `Transaccion` `PENDIENTE`. La clave de idempotencia
impide duplicados y un cambio de versión de la cotización conserva el intento
como `CANCELADA`, según el comportamiento del núcleo integrado.

## Métodos de pago

`GET /api/operaciones/metodos-pago/` trabaja sobre el cliente seleccionado:

- revalida que el cliente esté activo y autorizado;
- ofrece únicamente `MetodoPago.objects.activos()`;
- informa el método preferido solo cuando continúa activo;
- permite que el consumidor elija cualquier otro método activo;
- no procesa pagos ni integra proveedores externos.

Al confirmar se persisten la FK `metodo_pago` y el snapshot
`metodo_pago_nombre`. Por ello el histórico conserva el nombre utilizado aun
cuando el catálogo cambie posteriormente.

## Historial y detalle

`GET /api/operaciones/historial/` requiere `selected_client` en sesión. Esa
selección no se considera autorización: el servicio vuelve a comprobar la
asociación activa del usuario y filtra estrictamente por el cliente.

`GET /api/operaciones/<id>/detalle/` exige además que la transacción pertenezca
al cliente seleccionado. Una transacción de otro cliente responde como recurso
no disponible y no expone sus datos.

Los datos mínimos incluidos son identificador, tipo, cliente, monedas, montos,
tasa aplicada y versión, comisión, método, creador, fecha, estado y auditoría de
cancelación. Todos provienen de snapshots; nunca se recalculan con la tasa
actual. No existen endpoints de edición, eliminación o exportación para el
historial.

## Matriz de criterios y pruebas

| Criterio | Prueba |
|---|---|
| Venta usa `TasaComercial.venta` y crea `PENDIENTE` | `test_venta_previsualiza_y_confirma_con_tasa_de_venta` |
| Solo se ofrecen métodos activos y se preselecciona el preferido válido | `test_metodos_expone_solo_activos_y_preselecciona_preferido` |
| Un preferido inactivo no se ofrece | `test_metodo_preferido_inactivo_no_se_preselecciona` |
| El historial se limita al cliente seleccionado | `test_historial_muestra_solo_el_cliente_seleccionado` |
| El detalle de otro cliente no se expone | `test_detalle_de_otro_cliente_no_es_accesible` |
| El detalle conserva snapshots | `test_detalle_incluye_snapshots_y_cancelacion_sin_recalcular` |
| Historial y detalle son de solo lectura | `test_historial_y_detalle_rechazan_escrituras` |

## Ejecución

```powershell
docker compose exec -T web python manage.py test operaciones.test_guillermo
docker compose exec -T web python manage.py test operaciones
```

Antes de integrar también deben ejecutarse `check`, la verificación de
migraciones pendientes y la suite completa del proyecto.
