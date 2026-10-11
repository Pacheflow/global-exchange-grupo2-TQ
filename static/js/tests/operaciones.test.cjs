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
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const page = get('[data-operaciones-page]');
  page.dataset = {
    canPay: String(canPay), canLiquidate: String(canLiquidate), canViewPayment: 'true',
    historyUrl: '/historial/', detailUrl: '/detalle/0/', liquidationUrl: '/liquidar/0/',
    liquidationPeriodsUrl: '/periodos/0/', paymentUrl: '/pago/0/'
  };
  page.querySelector = selector => ['[data-operation-form]', '[data-preview-card]'].includes(selector) ? null : get(selector);
  const calls = [];
  const context = {
    document: { querySelector: get, getElementById: get, createElement: () => new Element() },
    window: { GEApp: { authenticationError: () => null, openModal() {} } },
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
    '\n globalThis.ui = { state, showDetail, renderPayment };\n})();'
  );
  vm.runInNewContext(source, context);
  return { ...context, get, calls };
}

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
