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
  metodo_pago: { nombre: 'QA' }, creado_por: { username: 'QA' }
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
  const context = {
    document: { querySelector: get, getElementById: get, createElement: () => new Element() },
    window: { GEApp: { authenticationError: () => null, openModal() {},
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
    '\n globalThis.ui = { state, showDetail, renderPayment, renderHistory, confirmOperation, submitPayment };\n})();'
  );
  vm.runInNewContext(source, context);
  return { ...context, get, calls, closed, setFetch(fn) { context.fetch = fn; } };
}

test('confirmación sin disponibilidad muestra aviso y conserva preview y clave sin repetir POST', async () => {
  const app = runtime(true, false);
  const mensaje = 'No hay disponibilidad suficiente para atender esta operación. Intenta más tarde.';
  const preview = { tasa_comercial: { version: 1 }, tasa: '7000', categoria_preview_id: 1, porcentaje_comision: '0' };
  app.ui.state.preview = preview;
  app.ui.state.payload = { tipo: 'COMPRA' };
  app.ui.state.idempotencyKey = 'misma-clave';
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
  for (const datos of [{ estado: null, codigo: 'PAGO_NO_INICIADO', pago_id: null },
    { estado: 'ERROR', codigo: 'ERROR_SIN_EJECUCION' }]) {
    const app = runtime(true, false);
    const compra = { ...transaction(1), tipo: 'COMPRA' };
    app.ui.state.detailId = 1;
    app.ui.state.detailVersion = 1;
    app.ui.state.detailTransaction = compra;
    app.ui.renderPayment(datos, compra);
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

test('SALDO_INSUFICIENTE permanece visible tras refrescar detalle y catálogo, sin repetir POST', async () => {
  const app = runtime();
  app.ui.showDetail(transaction(10));
  await settle();
  const select = app.get('[data-liquidation-period]');
  assert.equal(select.value, '', 'no autoseleccionar período');
  select.value = '12';
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

test('bandeja distingue Compra aprobada y Venta pendiente del historial no liquidable', () => {
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
