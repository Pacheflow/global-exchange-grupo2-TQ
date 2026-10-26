// DOM mínimo sin dependencias: ejecuta el script real y simula únicamente HTTP.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.dataset = {};
    this.children = [];
    this.listeners = {};
    this.hidden = false;
    this.disabled = false;
    this.textContent = '';
    this.value = '';
    this.classList = { contains: () => true };
  }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  appendChild(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
  set innerHTML(value) {
    this.html = value;
    if (value.startsWith('<option')) { this.children = [new Element()]; this.value = ''; }
  }
  get innerHTML() { return this.html || ''; }
  get options() { return this.children; }
}

const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(setImmediate); };
const transaction = id => ({
  id, tipo: 'VENTA', estado: 'PENDIENTE', cliente: { nombre_razon_social: 'QA' },
  moneda_origen: { codigo: 'USD' }, moneda_destino: { codigo: 'PYG' },
  metodo_pago: { id: 1, nombre: 'QA', activo: true, naturaleza: 'ELECTRONICO' }, creado_por: { username: 'QA' }
});

function runtime(canPay = false, canLiquidate = true) {
  const elements = new Map();
  const get = selector => {
    if (selector === '[data-payment-actions] [data-payment-action]' &&
        elements.get('[data-payment-actions]')?.children[0]) return elements.get('[data-payment-actions]').children[0];
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const page = get('[data-operaciones-page]');
  page.dataset = {
    canPay: String(canPay), canLiquidate: String(canLiquidate), canViewPayment: 'true',
    historyUrl: '/historial/', detailUrl: '/detalle/0/', liquidationUrl: '/liquidar/0/',
    liquidationPeriodsUrl: '/periodos/0/', paymentUrl: '/pago/0/',
    paymentStartUrl: '/pago-iniciar/0/', paymentRetryUrl: '/pago-reintentar/0/', createUrl: '/crear/'
  };
  page.querySelector = selector => ['[data-operation-form]', '[data-preview-card]'].includes(selector) ? null : get(selector);
  const calls = [];
  const closed = [];
  const opened = [];
  const context = {
    document: { querySelector: get, getElementById: get, createElement: () => new Element() },
    window: { GEApp: { authenticationError: () => null, openModal(id) { opened.push(id); },
      closeModal(id) { closed.push(id); }, toast() {} } },
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      const id = Number(url.split('/')[2]);
      let status = 200;
      let data;
      if (url.startsWith('/liquidar/')) {
        status = 400;
        data = { error: 'Saldo insuficiente para liquidar la operación.', codigo: 'SALDO_INSUFICIENTE' };
      } else if (url.startsWith('/detalle/')) data = { transaccion: transaction(id) };
      else if (url.startsWith('/periodos/')) data = {
        transaccion_id: id, periodos: [{ periodo_id: 12, estado: 'ABIERTO', caja: { codigo: 'QA', nombre: 'Principal' } }]
      };
      else data = { transacciones: [] };
      return { ok: status === 200, status, json: async () => data };
    }
  };
  // Exponer funciones solo en la copia en memoria, sin hooks en código productivo.
  const source = fs.readFileSync(path.join(__dirname, '../operaciones.js'), 'utf8').replace(
    /\s*loadHistory\(\);\s*\}\)\(\);\s*$/,
    '\n globalThis.ui = { state, showDetail, renderPayment, renderHistory, confirmOperation, submitPayment, loadPaymentMethods, openConfirmation };\n})();'
  );
  vm.runInNewContext(source, context);
  return { ...context, get, calls, closed, opened, setFetch(fn) { context.fetch = fn; } };
}

test('confirmación sin disponibilidad muestra aviso y conserva preview y clave sin repetir POST', async () => {
  /** Confirmar sin fondos informa el rechazo y conserva la solicitud para un reintento explícito. */
  const app = runtime(true, false);
  const mensaje = 'No hay disponibilidad suficiente para atender esta operación. Intenta más tarde.';
  const preview = { tasa_comercial: { version: 1 }, tasa: '7000', categoria_preview_id: 1, porcentaje_comision: '0' };
  app.ui.state.preview = preview;
  app.ui.state.payload = { tipo: 'COMPRA' };
  app.ui.state.idempotencyKey = 'misma-clave';
  app.get('[data-confirm-method]').value = '1';
  let solicitudes = 0;
  app.setFetch(async () => {
    solicitudes++;
    return { ok: false, status: 400, json: async () => ({ codigo: 'DISPONIBILIDAD_INSUFICIENTE', error: mensaje }) };
  });
  const boton = app.get('[data-confirm-operation]');
  app.ui.confirmOperation({ currentTarget: boton });
  await settle();
  assert.equal(app.get('[data-operation-feedback]').hidden, false);
  assert.equal(app.get('[data-operation-feedback]').textContent, mensaje);
  assert.deepEqual(app.closed, ['confirmar-operacion']);
  assert.equal(app.ui.state.preview, preview);
  assert.equal(app.ui.state.idempotencyKey, 'misma-clave');
  assert.equal(boton.disabled, false);
  assert.equal(solicitudes, 1);
});

test('inicio y reintento sin disponibilidad muestran aviso sin ocultar la acción ni reintentar automáticamente', async () => {
  /** Sin Pago se muestra una sola etiqueta legible; un rechazo libera iniciar/reintentar sin nuevos envíos. */
  for (const datos of [{ estado: null, codigo: 'PAGO_NO_INICIADO', pago_id: null },
    { estado: 'ERROR', codigo: 'ERROR_SIN_EJECUCION' }]) {
    const app = runtime(true, false);
    const compra = { ...transaction(1), tipo: 'COMPRA' };
    app.ui.state.detailId = 1;
    app.ui.state.detailVersion = 1;
    app.ui.state.detailTransaction = compra;
    app.ui.renderPayment(datos, compra);
    if (datos.codigo === 'PAGO_NO_INICIADO') {
      assert.equal(app.get('[data-payment-state]').textContent, 'Pago no iniciado');
      assert.equal(app.get('[data-payment-message]').textContent, '');
    }
    const boton = app.get('[data-payment-actions]').children[0];
    const etiqueta = datos.estado === 'ERROR' ? 'Reintentar pago' : 'Iniciar pago';
    const mensaje = 'No hay disponibilidad suficiente para procesar esta operación. No se realizó ningún cobro en este intento. Intenta más tarde.';
    let solicitudes = 0;
    app.setFetch(async () => {
      solicitudes++;
      return { ok: false, status: 400, json: async () => ({ codigo: 'DISPONIBILIDAD_INSUFICIENTE', error: mensaje }) };
    });
    app.ui.submitPayment({ target: { closest: () => boton } });
    app.ui.submitPayment({ target: { closest: () => boton } });
    assert.equal(boton.disabled, true);
    assert.equal(boton.textContent, 'Procesando…');
    await settle();
    assert.equal(app.get('[data-payment-message]').textContent, mensaje);
    assert.equal(app.get('[data-payment-actions]').hidden, false);
    assert.equal(app.get('[data-payment-actions]').children[0], boton);
    assert.equal(boton.disabled, false);
    assert.equal(boton.textContent, etiqueta);
    assert.equal(app.ui.state.paymentPending[1], undefined);
    assert.equal(solicitudes, 1);
  }
});

test('QA #21: rechazo 400 visible y un segundo clic explícito aprueba después de reponer fondos', async () => {
  const app = runtime(true, false);
  const compra = { ...transaction(21), tipo: 'COMPRA' };
  Object.assign(app.ui.state, { detailId: 21, detailVersion: 1, detailTransaction: compra });
  app.ui.renderPayment({ estado: null, codigo: 'PAGO_NO_INICIADO', pago_id: null }, compra);
  const boton = app.get('[data-payment-actions]').children[0];
  const mensaje = 'No hay disponibilidad suficiente para procesar esta operación. No se realizó ningún cobro en este intento. Intenta más tarde.';
  let solicitudes = 0;
  const aprobado = { transaccion_id: 21, pago_id: 'pago-test', estado: 'APROBADO', codigo: 'APROBADO', reutilizado: false };
  app.setFetch(async (url, opciones = {}) => {
    if (opciones.method === 'POST' && ++solicitudes === 1) {
      return { ok: false, status: 400, json: async () => ({ codigo: 'DISPONIBILIDAD_INSUFICIENTE', error: mensaje }) };
    }
    return { ok: true, status: 200, json: async () => aprobado };
  });
  const pulsar = () => app.ui.submitPayment({ target: { closest: () => boton } });
  pulsar();
  await settle();
  assert.equal(app.get('[data-payment-message]').textContent, mensaje);
  assert.equal(boton.disabled, false);
  assert.equal(solicitudes, 1);
  // El segundo POST solo ocurre al volver a pulsar, con fondos repuestos en el backend simulado.
  pulsar();
  await settle();
  assert.equal(solicitudes, 2);
  assert.equal(app.get('[data-payment-state]').textContent, 'APROBADO');
  assert.match(app.get('[data-payment-message]').textContent, /pendiente de liquidación/);
  assert.equal(app.get('[data-payment-actions]').children.length, 0);
});

test('timeout y respuestas no controladas conservan el aviso de resultado incierto', async () => {
  for (const timeout of [true, false]) {
    const app = runtime(true, false);
    const compra = { ...transaction(1), tipo: 'COMPRA' };
    Object.assign(app.ui.state, { detailId: 1, detailVersion: 1, detailTransaction: compra });
    app.ui.renderPayment({ estado: null, codigo: 'PAGO_NO_INICIADO', pago_id: null }, compra);
    const boton = app.get('[data-payment-actions]').children[0];
    app.setFetch(async () => {
      if (timeout) throw new Error('Timeout simulado');
      return { ok: false, status: 503, json: async () => ({ codigo: 'DISPONIBILIDAD_INSUFICIENTE' }) };
    });
    app.ui.submitPayment({ target: { closest: () => boton } });
    await settle();
    assert.match(app.get('[data-payment-message]').textContent, /No se pudo confirmar el resultado/);
    assert.equal(app.get('[data-payment-actions]').hidden, true);
  }
});

test('HU-27: confirma la selección una sola vez y abre detalle de Compra o Venta únicamente tras éxito', async () => {
  /** Conserva selección y firma; un fallo mantiene revisión y solo el éxito abre el detalle, sin cobrar. */
  for (const tipo of ['COMPRA', 'VENTA']) {
    const app = runtime(true, false);
    app.get('[data-operaciones-page]').dataset.methodsUrl = '/metodos/';
    const preview = { tipo, monto_origen: '1', monto_destino: '2', moneda_origen: { codigo: 'USD' },
      moneda_destino: { codigo: 'PYG' }, tasa_comercial: { version: 3 }, tasa: '2',
      categoria_preview_id: 1, porcentaje_comision: '0', firma_preview: 'firma-original' };
    Object.assign(app.ui.state, { preview, payload: { tipo }, idempotencyKey: 'clave' });
    let completar;
    const posts = [];
    app.setFetch(async (url, options = {}) => {
      if (options.method === 'POST') {
        posts.push(JSON.parse(options.body));
        return new Promise(resolve => { completar = resolve; });
      }
      return { ok: true, status: 200, json: async () => ({ metodo_pago_preferido: { id: 1 },
        metodos_pago: [{ id: 1, nombre: 'Preferido' }, { id: 2, nombre: 'Alternativa' }] }) };
    });
    app.ui.loadPaymentMethods();
    await settle();
    const select = app.get('[data-confirm-method]');
    assert.match(select.innerHTML, /value="1" selected/);
    assert.equal(app.get('[data-new-method]').value, '1');
    app.ui.openConfirmation();
    assert.equal(app.get('[data-confirm-method-label]').textContent, tipo === 'VENTA' ? 'Medio de recepción' : 'Método de pago');
    select.value = '2';
    select.listeners.change.call(select);
    assert.equal(app.get('[data-new-method]').value, '2', 'volver a editar conserva la selección del resumen');
    app.ui.loadPaymentMethods();
    await settle();
    assert.equal(select.value, '2', 'recargar opciones no restaura silenciosamente el preferido');
    app.ui.openConfirmation();
    assert.equal(select.value, '2');
    assert.equal(app.ui.state.preview, preview);
    const button = app.get('[data-confirm-operation]');
    app.ui.confirmOperation({ currentTarget: button });
    app.ui.confirmOperation({ currentTarget: button });
    assert.equal(button.disabled, true);
    assert.equal(select.disabled, true);
    await settle();
    assert.equal(posts.length, 1);
    assert.equal(posts[0].metodo_pago_id, 2);
    assert.equal(posts[0].firma_preview, 'firma-original');
    assert.equal(posts[0].version_preview, 3);
    completar({ ok: false, status: 503, json: async () => ({ error: 'Resultado incierto' }) });
    await settle();
    assert.equal(app.ui.state.confirmationPayload.metodo_pago_id, 2, 'una repetición incierta conserva la solicitud');
    assert.equal(select.disabled, true);
    assert.equal(app.ui.state.preview, preview, 'el error conserva la revisión');
    assert.equal(app.get('[data-operation-feedback]').textContent, 'Resultado incierto');
    assert.equal(app.opened.includes('detalle-operacion'), false);
    const solicitudes = [];
    const creada = { ...transaction(51), tipo };
    app.setFetch(async (url, options = {}) => {
      solicitudes.push({ url, options });
      const data = options.method === 'POST' ? { transaccion: creada, repetida: false }
        : url.startsWith('/detalle/') ? { transaccion: creada }
        : url.startsWith('/pago/') ? { transaccion_id: 51, estado: null, codigo: 'PAGO_NO_INICIADO', pago_id: null }
        : { transacciones: [] };
      return { ok: true, status: 200, json: async () => data };
    });
    app.ui.confirmOperation({ currentTarget: button });
    await settle();
    assert.equal(app.opened.filter(id => id === 'detalle-operacion').length, 1);
    assert.equal(app.ui.state.detailId, 51);
    assert.equal(app.ui.state.detailTransaction.tipo, tipo);
    assert.match(app.get('[data-transaction-detail]').innerHTML, tipo === 'VENTA' ? /Medio de recepción/ : /Método de pago/);
    assert.equal(solicitudes.filter(s => s.options.method === 'POST').length, 1, 'abrir detalle no crea otra operación');
    assert.deepEqual(JSON.parse(solicitudes[0].options.body), posts[0], 'el reintento explícito conserva la solicitud');
    assert.equal(solicitudes.some(s => /pago-iniciar|pago-reintentar/.test(s.url)), false);
    if (tipo === 'VENTA') {
      assert.equal(solicitudes.some(s => s.url.startsWith('/pago/')), false);
      assert.equal(app.get('[data-payment-section]').hidden, true);
      assert.equal(app.get('[data-payment-actions]').children.length, 0);
    }
  }
});

test('HU-27: método deshabilitado recarga opciones con aviso y catálogo vacío bloquea sin otro POST', async () => {
  /** Un método deshabilitado recarga con aviso, conserva la cotización y exige nueva confirmación. */
  const app = runtime(true, false);
  app.get('[data-operaciones-page]').dataset.methodsUrl = '/metodos/';
  const preview = { tasa_comercial: { version: 1 }, tasa: '2', categoria_preview_id: 1, porcentaje_comision: '0', firma_preview: 'original' };
  Object.assign(app.ui.state, { preview, payload: { tipo: 'VENTA' }, idempotencyKey: 'clave' });
  const select = app.get('[data-confirm-method]');
  select.value = '1';
  const mensaje = 'El método está inactivo. Revisá las opciones y confirmá nuevamente.';
  let posts = 0;
  let metodos = [{ id: 2, nombre: 'Alternativa' }];
  app.setFetch(async (url, options = {}) => {
    if (options.method === 'POST') {
      posts++;
      return { ok: false, status: 400, json: async () => ({ codigo: 'METODO_NO_DISPONIBLE', error: mensaje }) };
    }
    return { ok: true, status: 200, json: async () => ({ metodos_pago: metodos, metodo_pago_preferido: { id: 2 } }) };
  });
  const button = app.get('[data-confirm-operation]');
  app.ui.confirmOperation({ currentTarget: button });
  await settle();
  assert.equal(posts, 1);
  assert.equal(app.get('[data-confirm-message]').textContent, mensaje);
  assert.equal(app.ui.state.preview, preview);
  assert.equal(app.ui.state.confirmationPayload, null);
  assert.equal(select.value, '');
  assert.equal(button.disabled, true);
  assert.match(select.innerHTML, /Alternativa/);
  select.value = '2';
  select.listeners.change.call(select);
  assert.equal(button.disabled, false);
  metodos = [];
  app.ui.loadPaymentMethods(mensaje);
  await settle();
  assert.equal(select.disabled, true);
  assert.equal(button.disabled, true);
  assert.match(app.get('[data-confirm-message]').textContent, /No hay métodos/);
  assert.equal(posts, 1);
});
test('SALDO_INSUFICIENTE permanece visible tras refrescar detalle y catálogo, sin repetir POST', async () => {
  /** Un rechazo de liquidación conserva el aviso tras refrescar, sin repetir automáticamente el POST. */
  const app = runtime();
  app.ui.showDetail(transaction(10));
  await settle();
  const select = app.get('[data-liquidation-period]');
  assert.equal(select.value, '', 'no autoseleccionar período');
  select.value = '12';
  select.listeners.change();
  app.get('[data-liquidation-submit]').listeners.click();
  await settle();
  const error = app.get('[data-liquidation-error]');
  assert.equal(error.hidden, false);
  assert.equal(error.textContent, 'Saldo insuficiente para liquidar la operación.');
  app.get('[data-liquidation-refresh]').listeners.click();
  await settle();
  assert.equal(error.hidden, false);
  assert.match(error.textContent, /Saldo insuficiente/);
  app.ui.showDetail(transaction(10));
  await settle();
  assert.equal(error.hidden, false);
  assert.match(error.textContent, /Saldo insuficiente/);
  const posts = app.calls.filter(call => call.options.method === 'POST');
  assert.equal(posts.length, 1);
  assert.deepEqual(JSON.parse(posts[0].options.body), { periodo_id: 12 });
  app.ui.showDetail(transaction(11));
  await settle();
  assert.equal(error.hidden, true, 'no trasladar el error a otra operación');
  const template = fs.readFileSync(path.join(__dirname, '../../../templates/frontend/operaciones.html'), 'utf8');
  assert.match(template, /class="ge-operation-feedback is-error" data-liquidation-error role="alert" hidden/);
});

test('efectivo: detalle exige disponibilidad por Caja y confirma una sola simulación sin Stripe', async () => {
  /** En COMPRA/VENTA, sin fondos no se confirma; con fondos se envía un POST y el rechazo conserva la operación. */
  for (const tipo of ['COMPRA', 'VENTA']) {
    const app = runtime(false, true);
    const tx = { ...transaction(1), tipo, monto_origen: '100', monto_destino: '70',
      metodo_pago: { nombre: 'Físico', naturaleza: 'EFECTIVO', activo: true } };
    let disponible = false;
    let posts = 0;
    let resolver;
    const urls = [];
    app.setFetch(async (url, options = {}) => {
      urls.push(url);
      if (options.method === 'POST') {
        posts++;
        assert.equal(url, '/liquidar/1/');
        assert.deepEqual(JSON.parse(options.body), { periodo_id: 12 });
        return new Promise(resolve => { resolver = resolve; });
      }
      const data = url.startsWith('/detalle/') ? { transaccion: tx }
        : url.startsWith('/periodos/') ? { transaccion_id: 1, periodos: [{ periodo_id: 12,
          estado: 'ABIERTO', disponible, caja: { codigo: 'QA', nombre: 'Principal' } }] } : { transacciones: [] };
      return { ok: true, status: 200, json: async () => data };
    });
    app.ui.showDetail(tx);
    await settle();
    assert.equal(app.get('[data-liquidation-section]').hidden, false);
    assert.match(app.get('[data-cash-summary]').textContent, /recibe.*100.*entrega.*70/);
    const select = app.get('[data-liquidation-period]');
    const button = app.get('[data-liquidation-submit]');
    select.value = '12';
    select.listeners.change();
    assert.equal(button.disabled, true);
    button.listeners.click();
    await settle();
    assert.equal(posts, 0);
    disponible = true;
    app.get('[data-liquidation-refresh]').listeners.click();
    await settle();
    select.value = '12';
    select.listeners.change();
    assert.equal(button.disabled, false);
    assert.equal(button.textContent, 'Confirmar intercambio en efectivo');
    button.listeners.click();
    button.listeners.click();
    await settle();
    assert.equal(button.disabled, true);
    assert.equal(posts, 1);
    resolver({ ok: false, status: 400, json: async () => ({ codigo: 'SALDO_INSUFICIENTE' }) });
    await settle();
    assert.match(app.get('[data-liquidation-error]').textContent, /Saldo insuficiente/);
    assert.equal(app.ui.state.detailTransaction.estado, 'PENDIENTE');
    assert.equal(app.get('[data-payment-actions]').children.length, 0);
    assert.equal(urls.some(url => url.includes('/pago')), false);
    assert.equal(posts, 1);
  }
});

test('bandeja y detalle distinguen efectivo aprobado por evidencia, pendiente y pagos electrónicos', async () => {
  /** COMPRA/VENTA muestran Aprobado solo con liquidación efectiva; sin evidencia quedan Pendiente y electrónicos conservan etiquetas. */
  const app = runtime();
  app.get('[data-operaciones-page]').dataset.operativeInbox = 'true';
  for (const [tipo, estado, pago_estado, liquidable] of [
    ['COMPRA', 'PENDIENTE', 'APROBADO', true],
    ['COMPRA', 'PENDIENTE', 'ERROR', false],
    ['COMPRA', 'PENDIENTE', null, false],
    ['VENTA', 'PENDIENTE', null, true],
    ['COMPRA', 'COMPLETADA', 'APROBADO', false],
    ['VENTA', 'CANCELADA', null, false]
  ]) {
    app.ui.state.transactions = [{ ...transaction(1), tipo, estado, pago_estado }];
    app.ui.renderHistory();
    const html = app.get('[data-history-body]').innerHTML;
    assert.equal(html.includes('Ver / Liquidar'), liquidable);
    assert.equal(html.includes('Ver detalle'), !liquidable);
    assert.equal(html.includes('data-cancel-index'), false);
    assert.equal(html.includes('Iniciar pago'), false);
    assert.ok(html.includes(tipo === 'VENTA' ? 'No aplica' : (pago_estado || 'Pago no iniciado')));
  }
  for (const tipo of ['COMPRA', 'VENTA']) {
    for (const [estado, evidencia, etiqueta] of [
      ['PENDIENTE', null, 'Pendiente'],
      ['COMPLETADA', null, 'Pendiente'],
      ['COMPLETADA', { periodo_id: 12, caja: 'QA', confirmado_por: 'Cajero', ingreso_id: 1, egreso_id: 2 }, 'Aprobado']
    ]) {
      const tx = { ...transaction(1), tipo, estado, liquidacion_efectivo: evidencia,
        metodo_pago: { naturaleza: 'EFECTIVO', nombre: 'Físico', activo: true }, pago_estado: null };
      app.ui.state.transactions = [tx];
      app.ui.renderHistory();
      assert.ok(app.get('[data-history-body]').innerHTML.includes('<td>' + etiqueta + '</td>'));
      app.setFetch(async url => ({ ok: true, status: 200, json: async () => url.startsWith('/detalle/')
        ? { transaccion: tx } : { transaccion_id: 1, periodos: [] } }));
      app.ui.showDetail(tx);
      await settle();
      assert.equal(app.get('[data-payment-state]').textContent, etiqueta);
      assert.equal(app.get('[data-payment-actions]').children.length, 0);
      assert.equal(app.ui.state.detailTransaction.estado, estado, 'la etiqueta no cambia el estado financiero');
      assert.equal(app.ui.state.detailTransaction.pago_estado, null, 'no se fabrica estado de Pago');
    }
  }
});

test('capacidades UI: Cajero consulta sin iniciar/reintentar; Usuario no consulta catálogo ni liquida', async () => {
  const cajero = runtime();
  const compra = { ...transaction(1), tipo: 'COMPRA' };
  for (const data of [{ codigo: 'PAGO_NO_INICIADO', pago_id: null, estado: null },
    { codigo: 'ERROR_SIN_EJECUCION', estado: 'ERROR' }]) {
    cajero.ui.renderPayment(data, compra);
    assert.equal(cajero.get('[data-payment-actions]').children.length, 0);
  }
  const usuario = runtime(true, false);
  usuario.ui.showDetail(transaction(1));
  await settle();
  assert.equal(usuario.get('[data-liquidation-section]').hidden, true);
  usuario.get('[data-liquidation-period]').value = '12';
  usuario.get('[data-liquidation-submit]').listeners.click();
  assert.equal(usuario.calls.some(call => /\/(periodos|liquidar)\//.test(call.url)), false);
  usuario.ui.renderPayment({ codigo: 'PAGO_NO_INICIADO', pago_id: null, estado: null }, compra);
  assert.equal(usuario.get('[data-payment-actions]').children[0].textContent, 'Iniciar pago');
});
