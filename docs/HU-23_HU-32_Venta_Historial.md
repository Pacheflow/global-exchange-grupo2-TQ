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
Luego bloquea las filas relevantes, vuelve a leer la configuración vigente,
recalcula y crea una `Transaccion` `COMPLETADA`. La confirmación incluye como
huella la versión de tasa, la categoría y el porcentaje vistos en el preview;
si alguno cambió, se rechaza sin crear una transacción y se exige previsualizar
de nuevo. No se agregó un snapshot histórico de categoría.

La idempotencia sí incorpora una migración mínima para una huella SHA-256
nullable del payload canónico. Esa huella incluye la categoría observada, pero
no funciona como snapshot histórico ni participa en el cálculo económico.

La clave de idempotencia solo devuelve una operación existente cuando coinciden
el usuario autorizado, cliente y la huella persistida del payload: tipo, par de
monedas, monto, método, versión de tasa, categoría y comisión. La misma
comparación se aplica después de una carrera de unicidad; una fila histórica sin
huella se rechaza. Ningún rechazo revela los datos de la operación original.

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

`GET /api/operaciones/historial/` requiere `selected_client` para CAJERO y
USUARIO. Esa selección no se considera autorización: el servicio vuelve a
comprobar la asociación activa y filtra estrictamente por el cliente. El
ADMINISTRADOR usa el mismo endpoint como supervisor global.

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
| Venta usa `TasaComercial.venta` y crea `COMPLETADA` | `test_venta_previsualiza_y_confirma_con_tasa_de_venta` |
| Solo se ofrecen métodos activos y se preselecciona el preferido válido | `test_metodos_expone_solo_activos_y_preselecciona_preferido` |
| Un preferido inactivo no se ofrece | `test_metodo_preferido_inactivo_no_se_preselecciona` |
| El historial se limita al cliente seleccionado | `test_historial_muestra_solo_el_cliente_seleccionado` |
| El detalle de otro cliente no se expone | `test_detalle_de_otro_cliente_no_es_accesible` |
| El detalle conserva snapshots | `test_detalle_incluye_snapshots_y_cancelacion_sin_recalcular` |
| Historial y detalle son de solo lectura | `test_historial_y_detalle_rechazan_escrituras` |
| Cambio de categoría o comisión invalida el preview | `test_cambio_de_categoria_desde_preview_rechaza_confirmacion`, `test_cambio_de_porcentaje_desde_preview_rechaza_confirmacion` |
| Reutilización de clave con otro usuario, cliente o payload se rechaza | `IdempotenciaTests` |
| Categorías distintas con igual porcentaje no comparten payload | `test_misma_clave_categoria_distinta_con_igual_porcentaje_es_rechazada` |

## Ejecución

```powershell
docker compose exec -T web python manage.py test operaciones.test_guillermo
docker compose exec -T web python manage.py test operaciones
```

Antes de integrar también deben ejecutarse `check`, la verificación de
migraciones pendientes y la suite completa del proyecto.
