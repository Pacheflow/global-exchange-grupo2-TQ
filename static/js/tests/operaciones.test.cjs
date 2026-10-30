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
    this.classList = { contains: () => true, toggle() {} };
    this.attributes = {};
    this.notes = [];
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  setCustomValidity(value) { this.validityMessage = value; }
  insertAdjacentElement(_position, node) { this.notes.push(node); }
  remove() { this.removed = true; }
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
  id, canal: 'ONLINE', version_flujo: 1, tipo: 'VENTA', estado: 'PENDIENTE', cliente: { nombre_razon_social: 'QA' },
  moneda_origen: { codigo: 'USD' }, moneda_destino: { codigo: 'PYG' },
  metodo_pago: { id: 1, nombre: 'QA', activo: true, naturaleza: 'ELECTRONICO' }, creado_por: { username: 'QA' }
});

function runtime(canPay = false, canLiquidate = true, formFields = null, settings = {}) {
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
    paymentRecoverUrl: '/pago-recuperar/0/', paymentStartUrl: '/pago-iniciar/0/', paymentRetryUrl: '/pago-reintentar/0/', createUrl: '/crear/'
  };
  page.dataset.presencial = String(Boolean(settings.presencial));
  if (settings.cashRecent) {
    page.dataset.cashRecentUrl = '/cajas/recientes/';
    page.dataset.cashPeriodId = settings.periodId || '';
  }
  get('operacion-limites-monto').textContent = JSON.stringify(settings.amountLimits || null);
  const typeButtons = ['COMPRA', 'VENTA'].map(tipo => {
    const button = new Element(); button.dataset.operationType = tipo; return button;
  });
  const previewCard = settings.preview ? get('[data-preview-card]') : null;
  if (previewCard) { previewCard.querySelector = get; previewCard.scrollIntoView = () => {}; }
  const operationForm = formFields ? new Element() : null;
  if (operationForm) {
    operationForm.elements = Object.values(formFields);
    Object.assign(operationForm.elements, formFields);
    operationForm.querySelectorAll = selector => selector === '[data-operation-field-error]'
      ? Object.values(formFields).flatMap(input => input.notes) : selector === '[data-operation-type]' ? typeButtons : [];
    operationForm.querySelector = get;
    operationForm.reportValidity = () => false;
  }
  page.querySelector = selector => selector === '[data-operation-form]' ? operationForm : selector === '[data-preview-card]' ? previewCard : get(selector);
  const calls = [];
  const closed = [];
  const opened = [];
  const toasts = [];
  const context = {
    document: { querySelector: get, getElementById: get, createElement: () => new Element() },
    window: { GEApp: { authenticationError: () => null, openModal(id) { opened.push(id); },
      closeModal(id) { closed.push(id); }, toast(message, type) { toasts.push({ message, type }); },
      userMessage(message) { return message; },
      insufficientFundsMessage(currency) { return 'No hay fondos suficientes' + (currency ? ' en ' + currency : '') + ' para completar esta operación. Probá con otro monto o intentá nuevamente más tarde.'; } } },
    FormData: class {
      constructor(form) { this.form = form; }
      get(name) { const input = this.form.elements[name]; return input && !input.disabled ? input.value : null; }
    },
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      const id = Number(url.split('/')[2]);
      let status = 200;
      let data;
      if (url.startsWith('/liquidar/')) {
        status = 400;
        data = { error: 'Saldo insuficiente para liquidar la operación.', codigo: 'SALDO_INSUFICIENTE' };
      } else if (url.startsWith('/detalle/')) data = { transaccion: canLiquidate && !canPay ? { ...transaction(id), canal: 'PRESENCIAL', metodo_pago: { id: 1, naturaleza: 'EFECTIVO', activo: true } } : transaction(id) };
      else if (url.startsWith('/periodos/')) data = {
        transaccion_id: id, periodos: [{ periodo_id: 12, estado: 'ABIERTO', disponible: true, caja: { codigo: 'QA', nombre: 'Principal' } }]
      };
      else data = { transacciones: [] };
      return { ok: status === 200, status, json: async () => data };
    }
  };
  // Exponer funciones solo en la copia en memoria, sin hooks en código productivo.
  const source = fs.readFileSync(path.join(__dirname, '../operaciones.js'), 'utf8').replace(
    /\s*loadHistory\(\);\s*\}\)\(\);\s*$/,
    '\n globalThis.ui = { state, showDetail, renderPayment, renderHistory, loadHistory, confirmOperation, submitPayment, loadPaymentMethods, openConfirmation, fieldErrors, renderMethodChange, submitMethodChange };\n})();'
  );
  vm.runInNewContext(source, context);
  return { ...context, get, calls, closed, opened, toasts, operationForm, typeButtons, setFetch(fn) { context.fetch = fn; } };
}

test('confirmación sin disponibilidad muestra aviso y conserva preview y clave sin repetir POST', async () => {
  /** Confirmar sin fondos informa el rechazo y conserva la solicitud para un reintento explícito. */
  const app = runtime(true, false);
  const mensaje = 'No hay disponibilidad suficiente para atender esta operación. Intenta más tarde.';
  const preview = { moneda_destino: { codigo: 'EUR' }, tasa_comercial: { version: 1 }, tasa: '7000', categoria_preview_id: 1, porcentaje_comision: '0' };
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
  assert.equal(app.get('[data-operation-feedback]').hidden, true);
  assert.equal(app.get('[data-operation-feedback]').textContent, '');
  assert.deepEqual(app.toasts, [{ message: 'No hay fondos suficientes en EUR para completar esta operación. Probá con otro monto o intentá nuevamente más tarde.', type: 'error' }]);
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
    assert.equal(app.get('[data-payment-message]').textContent, '');
    assert.equal(app.toasts.at(-1).message, 'No hay fondos suficientes en PYG para completar esta operación. Probá con otro monto o intentá nuevamente más tarde.');
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
    return { ok: true, status: 200, json: async () => url.startsWith('/detalle/') ? { transaccion: { ...compra, estado: 'COMPLETADA' } } : url.startsWith('/historial/') ? { transacciones: [] } : aprobado };
  });
  const pulsar = () => app.ui.submitPayment({ target: { closest: () => boton } });
  pulsar();
  await settle();
  assert.equal(app.get('[data-payment-message]').textContent, '');
    assert.equal(app.toasts.at(-1).message, 'No hay fondos suficientes en PYG para completar esta operación. Probá con otro monto o intentá nuevamente más tarde.');
  assert.equal(boton.disabled, false);
  assert.equal(solicitudes, 1);
  // El segundo POST solo ocurre al volver a pulsar, con fondos repuestos en el backend simulado.
  pulsar();
  await settle();
  assert.equal(solicitudes, 2);
  assert.equal(app.get('[data-payment-state]').textContent, 'APROBADO');
  assert.equal(app.get('[data-payment-message]').textContent, '');
  assert.equal(app.ui.state.detailTransaction.estado, 'COMPLETADA');
  assert.equal(app.calls.some(call => /\/periodos\//.test(call.url)), false);
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
    assert.equal(app.get('[data-payment-message]').textContent, '');
    assert.match(app.toasts.at(-1).message, /No se pudo confirmar el resultado/);
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
    assert.equal(app.get('[data-operation-feedback]').textContent, '');
    assert.equal(app.toasts.at(-1).message, 'Resultado incierto');
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
  assert.equal(app.get('[data-confirm-message]').textContent, '');
  assert.equal(app.toasts.at(-1).message, mensaje);
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
  assert.equal(app.get('[data-confirm-message]').textContent, '');
  assert.match(app.toasts.at(-1).message, /No hay métodos/);
  assert.equal(posts, 1);
});
test('SALDO_INSUFICIENTE muestra un toast y refrescar detalle o catálogo no lo duplica', async () => {
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
  assert.equal(error.hidden, true);
  assert.equal(error.textContent, '');
  assert.equal(app.toasts.length, 1);
  assert.match(app.toasts[0].message, /fondos suficientes en PYG/);
  app.get('[data-liquidation-refresh]').listeners.click();
  await settle();
  assert.equal(error.hidden, true);
  assert.equal(app.toasts.length, 1);
  app.ui.showDetail(transaction(10));
  await settle();
  assert.equal(error.hidden, true);
  assert.equal(app.toasts.length, 1);
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
    const tx = { ...transaction(1), canal: 'PRESENCIAL', tipo, monto_origen: '100', monto_destino: '70',
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
    assert.equal(app.get('[data-liquidation-error]').hidden, true);
    assert.equal(app.toasts.length, 1);
    assert.match(app.toasts[0].message, /fondos suficientes en PYG/);
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
    ['COMPRA', 'PENDIENTE', 'APROBADO', false],
    ['COMPRA', 'PENDIENTE', 'ERROR', false],
    ['COMPRA', 'PENDIENTE', null, false],
    ['VENTA', 'PENDIENTE', null, false],
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
        canal: 'PRESENCIAL', metodo_pago: { naturaleza: 'EFECTIVO', nombre: 'Físico', activo: true }, pago_estado: null };
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
  // Un histórico conserva su información, sin habilitar cobros por inferencia del catálogo.
  usuario.ui.renderPayment({ codigo: 'PAGO_NO_INICIADO', pago_id: null, estado: null }, { ...compra, version_flujo: 0 });
  assert.equal(usuario.get('[data-payment-actions]').children.length, 0);
  assert.match(usuario.get('[data-payment-message]').textContent, /histórica pendiente de revisión/);
});


test('aprobado pendiente recupera la misma operación una vez por doble clic y oculta acciones al completar', async () => {
  for (const canPay of [false, true]) {
    const app = runtime(canPay, true);
    const compra = { ...transaction(31), tipo: 'COMPRA' };
    const aprobado = { transaccion_id: 31, pago_id: 'mismo-pago', estado: 'APROBADO', codigo: 'APROBADO' };
    Object.assign(app.ui.state, { detailId: 31, detailVersion: 1, detailTransaction: compra });
    app.ui.renderPayment(aprobado, compra);
    const actions = app.get('[data-payment-actions]');
    assert.equal(actions.children.length, 1);
    const boton = actions.children[0];
    assert.equal(boton.dataset.paymentAction, 'recover');
    assert.equal(boton.textContent, 'Recuperar finalización');
    assert.match(app.get('[data-payment-message]').textContent, /sin volver a cobrar/);
    const solicitudes = [];
    let responder;
    app.setFetch(async (url, options = {}) => {
      solicitudes.push({ url, method: options.method || 'GET' });
      if (options.method === 'POST') return new Promise(resolve => { responder = resolve; });
      const data = url.startsWith('/detalle/') ? { transaccion: { ...compra, estado: 'COMPLETADA' } }
        : url.startsWith('/pago/') ? aprobado : { transacciones: [] };
      return { ok: true, status: 200, json: async () => data };
    });
    const pulsar = () => app.ui.submitPayment({ target: { closest: () => boton } });
    pulsar();
    pulsar();
    assert.equal(boton.disabled, true);
    assert.deepEqual(solicitudes, [{ url: '/pago-recuperar/31/', method: 'POST' }]);
    responder({ ok: true, status: 200, json: async () => aprobado });
    await settle();
    assert.equal(app.ui.state.detailTransaction.estado, 'COMPLETADA');
    assert.equal(actions.children.length, 0);
    assert.equal(actions.hidden, true);
    assert.equal(app.get('[data-liquidation-section]').hidden, true);
    assert.equal(app.get('[data-payment-message]').textContent, '');
    assert.equal(solicitudes.filter(call => call.method === 'POST').length, 1);
    assert.equal(solicitudes.some(call => /\/(pago-iniciar|pago-reintentar|periodos|liquidar)\//.test(call.url)), false);
    // Volver a abrir consulta la evidencia aprobada sin iniciar otra acción.
    app.ui.showDetail(app.ui.state.detailTransaction);
    await settle();
    assert.equal(actions.children.length, 0);
    assert.equal(solicitudes.filter(call => call.method === 'POST').length, 1);
  }
});

test('recuperación de finalización aprobada respeta flujo, estado y permiso de consulta', () => {
  const aprobado = { estado: 'APROBADO', codigo: 'APROBADO' };
  const compra = { ...transaction(32), tipo: 'COMPRA' };
  for (const cambios of [
    { version_flujo: 0 }, { version_flujo: 2 }, { estado: 'COMPLETADA' }, { estado: 'CANCELADA' },
    { canal: 'PRESENCIAL' }, { canal: '' }, { tipo: 'VENTA' },
    { metodo_pago: { naturaleza: 'EFECTIVO' } }, { metodo_pago: { naturaleza: 'SIN_CLASIFICAR' } },
    { metodo_pago: null }
  ]) {
    const app = runtime(true, true);
    app.ui.renderPayment(aprobado, { ...compra, ...cambios });
    assert.equal(app.get('[data-payment-actions]').children.length, 0, JSON.stringify(cambios));
    assert.equal(app.calls.length, 0);
  }
  const app = runtime(true, true);
  app.get('[data-operaciones-page]').dataset.canViewPayment = 'false';
  app.ui.renderPayment(aprobado, compra);
  assert.equal(app.get('[data-payment-actions]').children.length, 0);
});


test('validaciones de campo permanecen junto al input sin toast y se limpian al corregir', () => {
  const input = new Element();
  input.value = '1';
  const app = runtime(true, false, { monto_origen: input });
  assert.equal(app.ui.fieldErrors({ fields: { monto: ['Ingresá un monto válido.'] } }), true);
  assert.equal(input.validityMessage, 'Ingresá un monto válido.');
  assert.equal(input.notes[0].textContent, 'Ingresá un monto válido.');
  assert.equal(input.attributes['aria-invalid'], 'true');
  assert.equal(app.toasts.length, 0);
  app.operationForm.listeners.input({ target: input });
  assert.equal(input.validityMessage, '');
  assert.equal(input.attributes['aria-invalid'], undefined);
  assert.equal(input.notes[0].removed, true);
  app.operationForm.listeners.submit({ preventDefault() {} });
  assert.equal(app.calls.length, 0, 'la validación nativa impide enviar un campo inválido');
  assert.equal(app.toasts.length, 0);
});

test('éxito de creación genera solo un toast y conserva vacío el aviso inline', async () => {
  const app = runtime(true, false);
  Object.assign(app.ui.state, { preview: { tasa_comercial: { version: 1 } }, payload: { tipo: 'VENTA' } });
  app.get('[data-confirm-method]').value = '1';
  const creada = { ...transaction(91), estado: 'COMPLETADA' };
  app.setFetch(async (url, options = {}) => ({ ok: true, status: 200, json: async () =>
    options.method === 'POST' ? { transaccion: creada } : url.startsWith('/detalle/') ? { transaccion: creada } : { transacciones: [] } }));
  app.ui.confirmOperation({ currentTarget: app.get('[data-confirm-operation]') });
  await settle();
  assert.equal(app.toasts.length, 1);
  assert.equal(app.toasts[0].type, 'success');
  assert.equal(app.get('[data-operation-feedback]').hidden, true);
  assert.equal(app.get('[data-operation-feedback]').textContent, '');
});


function cashForm() {
  const fields = {};
  for (const [name, value] of Object.entries({ cliente_id: '9', tipo: 'COMPRA', moneda_origen_id: '1',
    moneda_destino_id: '2', monto_origen: '10', metodo_pago_id: '4' })) {
    fields[name] = new Element();
    fields[name].value = value;
  }
  const app = runtime(false, true, fields);
  const page = app.get('[data-operaciones-page]');
  page.dataset.presencial = 'true';
  page.dataset.methodsUrl = '/efectivo/metodos/';
  page.dataset.previewUrl = '/efectivo/preview/';
  app.operationForm.reportValidity = () => true;
  return { app, fields };
}

test('cajero autoselecciona un único método efectivo y varios permiten elegir', async () => {
  for (const methods of [[{ id: 4, nombre: 'Efectivo' }], [{ id: 4, nombre: 'Efectivo' }, { id: 5, nombre: 'Ventanilla' }]]) {
    const { app } = cashForm();
    app.setFetch(async () => ({ ok: true, status: 200, json: async () => ({ metodos_pago: methods }) }));
    await app.ui.loadPaymentMethods();
    const initial = app.get('[data-new-method]');
    assert.equal(initial.disabled, false);
    assert.equal(app.get('[data-confirm-method]').disabled, false);
    assert.equal(initial.value, methods.length === 1 ? '4' : '');
    assert.equal(app.get('[data-preview-button]').disabled, false);
  }
});

test('cajero sin efectivo usa toast y mantiene editables los otros campos', async () => {
  const { app, fields } = cashForm();
  app.setFetch(async () => ({ ok: true, status: 200, json: async () => ({ metodos_pago: [] }) }));
  await app.ui.loadPaymentMethods();
  assert.equal(app.toasts.length, 1);
  assert.match(app.toasts[0].message, /No hay métodos de efectivo activos/);
  assert.equal(app.get('[data-preview-button]').disabled, true);
  assert.equal(app.get('[data-new-method-message]').textContent, '');
  for (const name of ['cliente_id', 'tipo', 'moneda_origen_id', 'moneda_destino_id', 'monto_origen']) {
    assert.equal(fields[name].disabled, false);
  }
});

test('error al consultar métodos libera selectores y permite volver a previsualizar con efectivo', async () => {
  const { app, fields } = cashForm();
  const initial = app.get('[data-new-method]');
  const confirm = app.get('[data-confirm-method]');
  initial.value = confirm.value = '4';
  app.setFetch(async () => { throw new Error('No se pudo consultar el catálogo.'); });
  await app.ui.loadPaymentMethods();
  assert.equal(initial.disabled, false);
  assert.equal(confirm.disabled, false);
  assert.equal(app.get('[data-preview-button]').disabled, false);
  let sent;
  app.setFetch(async (_url, options) => {
    sent = JSON.parse(options.body);
    return { ok: false, status: 400, json: async () => ({ error: 'La tasa cambió.' }) };
  });
  app.operationForm.listeners.submit({ preventDefault() {} });
  await settle();
  assert.equal(sent.metodo_pago_id, '4');
  for (const input of Object.values(fields)) assert.equal(input.disabled, false);
  assert.equal(app.get('[data-preview-button]').disabled, false);
});

test('submit durante carga o sin métodos no envía FormData con método omitido', () => {
  const { app, fields } = cashForm();
  app.ui.state.methodsLoading = true;
  fields.metodo_pago_id.disabled = true;
  app.operationForm.listeners.submit({ preventDefault() {} });
  assert.equal(app.calls.length, 0);
  app.ui.state.methodsLoading = false;
  app.operationForm.listeners.submit({ preventDefault() {} });
  assert.equal(app.calls.length, 0);
});

test('operaciones limita las filas a cinco y el historial completo mantiene método y detalle', () => {
  const app = runtime(true, false);
  app.ui.state.transactions = Array.from({ length: 8 }, (_, index) => transaction(index + 1));
  app.get('[data-operaciones-page]').dataset.historyLimit = '5';
  app.ui.renderHistory();
  assert.equal((app.get('[data-history-body]').innerHTML.match(/data-detail-index=/g) || []).length, 5);
  assert.match(app.get('[data-history-body]').innerHTML, /<td>QA<\/td>/);
  app.get('[data-operaciones-page]').dataset.historyLimit = '';
  app.ui.renderHistory();
  assert.equal((app.get('[data-history-body]').innerHTML.match(/data-detail-index=/g) || []).length, 8);
});


function methodChangeApp(status = 'RECHAZADO', capability = true) {
  const app = runtime(true, false);
  Object.assign(app.get('[data-operaciones-page]').dataset, {
    paymentChangeMethodUrl: '/cambio/0/', paymentAttemptsUrl: '/intentos/0/', methodsUrl: '/metodos/'
  });
  const tx = { ...transaction(11), tipo: 'COMPRA' };
  const data = { transaccion_id: 11, estado: status, codigo: status === 'ERROR' ? 'ERROR_SIN_EJECUCION' : status,
    pago_id: '00000000-0000-4000-8000-000000000001', metodo_pago_id: 1, puede_cambiar_metodo: capability };
  if (status === 'PAGO_NO_INICIADO') { data.estado = null; data.pago_id = null; }
  Object.assign(app.ui.state, { detailId: 11, detailVersion: 1, detailTransaction: tx });
  return { app, tx, data };
}

const paymentCatalog = { metodos_pago: [{ id: 1, nombre: 'Tarjeta' }, { id: 2, nombre: 'Transferencia' }] };
const http = data => ({ ok: true, status: 200, json: async () => data });

test('pago no iniciado, rechazado y error seguro ofrecen otro método si backend lo autoriza', async () => {
  for (const status of ['PAGO_NO_INICIADO', 'RECHAZADO', 'ERROR']) {
    const { app, tx, data } = methodChangeApp(status);
    app.setFetch(async () => http(paymentCatalog));
    app.ui.renderPayment(data, tx);
    await settle();
    assert.equal(app.get('[data-payment-method-change]').hidden, false);
    const select = app.get('[data-payment-method-options]');
    assert.equal(select.disabled, false);
    assert.match(select.innerHTML, /Transferencia/);
    assert.doesNotMatch(select.innerHTML, />Tarjeta</);
    select.value = '2';
    select.listeners.change.call(select);
    assert.equal(app.get('[data-payment-method-submit]').disabled, false);
  }
});

test('pago aprobado, en proceso, indeterminado o sin permiso nunca ofrecen cambiar método', async () => {
  for (const [status, capability] of [['APROBADO', true], ['EN_PROCESO', true], ['INDETERMINADO', true], ['RECHAZADO', false]]) {
    const { app, tx, data } = methodChangeApp(status, capability);
    app.ui.renderPayment(data, tx);
    await settle();
    assert.equal(app.get('[data-payment-method-change]').hidden, true);
    assert.equal(app.calls.length, 0);
  }
  const { app, tx, data } = methodChangeApp();
  app.get('[data-operaciones-page]').dataset.canPay = 'false';
  app.ui.renderPayment(data, tx);
  assert.equal(app.get('[data-payment-method-change]').hidden, true);
});

test('cambio de método solo cambia y refresca estado e intentos, sin iniciar cobro y sin doble clic', async () => {
  const { app, tx, data } = methodChangeApp();
  let current = 1;
  let release;
  const posts = [];
  app.setFetch(async (url, options = {}) => {
    if (options.method === 'POST') {
      posts.push({ url, payload: JSON.parse(options.body) });
      await new Promise(resolve => { release = resolve; });
      current = 2;
      return http({ transaccion_id: 11, metodo_pago_id: 2, codigo: 'METODO_CAMBIADO' });
    }
    if (url === '/metodos/') return http(paymentCatalog);
    if (url === '/detalle/11/') return http({ transaccion: { ...tx, metodo_pago: { id: current, nombre: 'Transferencia', activo: true, naturaleza: 'ELECTRONICO' } } });
    if (url === '/pago/11/') return http({ ...data, metodo_pago_id: current, estado: null, codigo: 'PAGO_NO_INICIADO', pago_id: null });
    if (url === '/intentos/11/') return http({ transaccion_id: 11, intentos: [{ pago_id: data.pago_id, metodo_pago_nombre: 'Tarjeta', estado: 'RECHAZADO', codigo: 'RECHAZADO', vigente: false, fecha_creacion: '2026-10-29T10:00:00Z' }] });
    return http({ transacciones: [] });
  });
  app.ui.renderPayment(data, tx);
  await settle();
  const select = app.get('[data-payment-method-options]');
  const button = app.get('[data-payment-method-submit]');
  select.value = '2'; select.listeners.change.call(select);
  app.ui.submitMethodChange({ currentTarget: button });
  app.ui.submitMethodChange({ currentTarget: button });
  assert.equal(posts.length, 1);
  assert.equal(select.disabled, true);
  const request = posts[0].payload;
  assert.equal(posts[0].url, '/cambio/11/');
  assert.equal(request.metodo_pago_id, 2);
  assert.equal(request.metodo_anterior_id, 1);
  assert.equal(request.pago_esperado_id, data.pago_id);
  assert.match(request.clave_idempotencia, /^[0-9a-f-]{36}$/);
  release();
  await settle();
  assert.equal(posts.length, 1);
  assert.equal(app.ui.state.detailTransaction.metodo_pago.id, 2);
  assert.equal(app.get('[data-payment-state]').textContent, 'Pago no iniciado');
  assert.equal(app.get('[data-payment-actions]').children[0].textContent, 'Iniciar pago');
  assert.match(app.get('[data-payment-attempts-body]').innerHTML, /Tarjeta/);
  assert.match(app.get('[data-payment-attempts-body]').innerHTML, /RECHAZADO/);
  assert.equal(app.toasts.length, 1);
  assert.equal(app.toasts[0].type, 'success');
});

test('cambio incierto conserva UUID y payload, bloquea otro cobro y repite la misma solicitud explícita', async () => {
  const { app, tx, data } = methodChangeApp('ERROR');
  const posts = [];
  let current = 1;
  app.setFetch(async (url, options = {}) => {
    if (options.method === 'POST') {
      posts.push({ url, body: options.body });
      if (posts.length === 1) throw new Error('Sin conexión para confirmar el cambio.');
      current = 2;
      return http({ transaccion_id: 11, metodo_pago_id: 2, codigo: 'METODO_CAMBIADO' });
    }
    if (url === '/metodos/') return http(paymentCatalog);
    if (url === '/detalle/11/') return http({ transaccion: { ...tx, metodo_pago: { ...tx.metodo_pago, id: current } } });
    if (url === '/pago/11/') return http({ ...data, metodo_pago_id: current });
    if (url === '/intentos/11/') return http({ transaccion_id: 11, intentos: [] });
    return http({ transacciones: [] });
  });
  app.ui.renderPayment(data, tx);
  await settle();
  const select = app.get('[data-payment-method-options]');
  select.value = '2'; select.listeners.change.call(select);
  const button = app.get('[data-payment-method-submit]');
  app.ui.submitMethodChange({ currentTarget: button });
  const payButton = app.get('[data-payment-actions]').children[0];
  app.ui.submitPayment({ target: { closest: () => payButton } });
  await settle();
  assert.equal(posts.length, 1);
  assert.equal(select.disabled, true);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, 'Reintentar cambio');
  const retryPay = app.get('[data-payment-actions]').children[0];
  app.ui.submitPayment({ target: { closest: () => retryPay } });
  await settle();
  assert.equal(posts.length, 1, 'resolver el cambio incierto antes de otro cobro');
  app.ui.submitMethodChange({ currentTarget: button });
  await settle();
  assert.equal(posts.length, 2);
  assert.equal(posts[0].body, posts[1].body);
  assert.equal(posts[0].url, posts[1].url);
});


test('rechazo o error del POST actualizan capacidades e intentos y ofrecen otro método sin reabrir detalle', async () => {
  for (const status of ['RECHAZADO', 'ERROR']) {
    const { app, tx, data } = methodChangeApp('PAGO_NO_INICIADO');
    let posted = false;
    const requests = [];
    const result = { transaccion_id: tx.id, pago_id: '00000000-0000-4000-8000-000000000004',
      estado: status, codigo: status === 'ERROR' ? 'ERROR_SIN_EJECUCION' : 'RECHAZADO' };
    app.setFetch(async (url, options = {}) => {
      requests.push({ url, method: options.method || 'GET' });
      if (options.method === 'POST') { posted = true; return http(result); }
      if (url === '/pago/11/') return http({ ...result, metodo_pago_id: 1, puede_cambiar_metodo: true });
      if (url === '/metodos/') return http(paymentCatalog);
      if (url === '/intentos/11/') return http({ transaccion_id: tx.id, intentos: [{ pago_id: result.pago_id,
        metodo_pago_nombre: 'Tarjeta', estado: status, codigo: result.codigo, vigente: true,
        fecha_creacion: '2026-10-29T10:00:00Z' }] });
      throw new Error('Consulta inesperada: ' + url);
    });
    app.ui.renderPayment(data, tx);
    await settle();
    assert.equal(app.get('[data-payment-actions]').children[0].textContent, 'Iniciar pago');
    const button = app.get('[data-payment-actions]').children[0];
    app.ui.submitPayment({ target: { closest: () => button } });
    await settle();
    assert.equal(posted, true);
    assert.equal(requests.filter(request => request.method === 'POST').length, 1);
    assert.equal(requests.filter(request => request.url === '/pago/11/').length, 1);
    assert.equal(requests.filter(request => request.url === '/intentos/11/').length, 1);
    assert.equal(app.get('[data-payment-method-change]').hidden, false);
    assert.equal(app.get('[data-payment-method-options]').disabled, false);
    assert.match(app.get('[data-payment-method-options]').innerHTML, /Transferencia/);
    assert.match(app.get('[data-payment-attempts-body]').innerHTML, new RegExp(status));
    assert.equal(app.ui.state.detailTransaction, tx);
    assert.equal(app.ui.state.detailVersion, 1);
    assert.equal(app.ui.state.paymentData.pago_id, result.pago_id);
    assert.equal(app.ui.state.paymentPending[tx.id], undefined);
    assert.equal(app.opened.length, 0, 'no requiere volver a abrir el detalle');
    assert.equal(app.toasts.length, 1, 'solo el resultado del POST genera aviso');
  }
});


// El JSON reproduce el contexto Django, no hay máximos dentro del script productivo.
const amountLimits = {
  general: { maximo: '999999999999.999999', decimales: 6, minimo: '0.000001' },
  compra_online: Object.fromEntries(['USD', 'EUR', 'BRL', 'ARS'].map(currency =>
    [currency, { maximo: '999999.99', decimales: 2, minimo: '0.01' }]).concat(
    [['PYG', { maximo: '99999999', decimales: 0, minimo: '1' }]]))
};
const excessiveAmountMessage = 'El monto ingresado supera el límite permitido para una operación.';
function amountForm({ amount = '1', currency = 'USD', tipo = 'COMPRA', presencial = false, limits = amountLimits } = {}) {
  const fields = {};
  for (const [name, value] of Object.entries({ cliente_id: '9', tipo, moneda_origen_id: '1',
    moneda_destino_id: '2', monto_origen: amount, metodo_pago_id: '4' })) {
    fields[name] = new Element(); fields[name].value = value;
  }
  const option = new Element(); option.value = '1'; option.dataset.codigo = currency;
  fields.moneda_origen_id.children = [option]; fields.moneda_origen_id.selectedIndex = 0;
  const app = runtime(false, false, fields, { amountLimits: limits, presencial, preview: true });
  app.get('[data-operaciones-page]').dataset.previewUrl = '/preview/';
  app.operationForm.reportValidity = () => true;
  app.setFetch(async (_url, options) => {
    app.calls.push({ url: _url, options });
    return { ok: true, status: 200, json: async () => ({
      tipo, cliente: { nombre_razon_social: 'QA' }, moneda_origen: { codigo: currency },
      moneda_destino: { codigo: 'PYG' }, monto_origen: amount, monto_destino: '2',
      monto_convertido: '2', importe_comision: '0', porcentaje_comision: '0', tasa: '2'
    }) };
  });
  const submit = () => app.operationForm.listeners.submit({ preventDefault() {} });
  const edit = value => { fields.monto_origen.value = value; app.operationForm.listeners.input({ target: fields.monto_origen }); };
  return { app, fields, submit, edit, option };
}

test('monto inválido, vacío o no finito evita el POST y muestra un solo toast antes de la validación nativa', () => {
  for (const amount of ['', '0', '-1', 'NaN', 'Infinity', '-Infinity', 'texto', '1.2.3']) {
    const { app, fields, submit } = amountForm({ amount });
    app.operationForm.reportValidity = () => { throw Error('No debe ocultar el toast con validación nativa'); };
    submit();
    assert.equal(app.calls.length, 0, amount);
    assert.deepEqual(app.toasts, [{ message: 'Ingresá un monto válido mayor a cero.', type: 'error' }]);
    assert.equal(fields.monto_origen.notes.length, 0);
    assert.equal(fields.monto_origen.validityMessage, undefined);
    assert.equal(app.get('[data-operation-feedback]').textContent, '');
  }
});

test('monto excesivo local evita toda solicitud y produce únicamente el toast solicitado', () => {
  for (const amount of ['1000000', '9999999999999999999999999999', '1e40']) {
    const { app, fields, submit } = amountForm({ amount });
    app.operationForm.reportValidity = () => { throw Error('El límite se valida primero'); };
    submit();
    assert.equal(app.calls.length, 0);
    assert.deepEqual(app.toasts, [{ message: excessiveAmountMessage, type: 'error' }]);
    assert.equal(fields.monto_origen.notes.length, 0);
    assert.equal(app.get('[data-preview-button]').disabled, false);
  }
});

test('MONTO_EXCESIVO del backend usa un solo toast aunque haya detalles de campo', async () => {
  const { app, fields, submit } = amountForm();
  let posts = 0;
  app.setFetch(async () => { posts++; return { ok: false, status: 400, json: async () => ({
    codigo: 'MONTO_EXCESIVO', error: excessiveAmountMessage, detalles: { monto: ['detalle técnico'] }
  }) }; });
  submit(); await settle();
  assert.equal(posts, 1);
  assert.deepEqual(app.toasts, [{ message: excessiveAmountMessage, type: 'error' }]);
  assert.equal(fields.monto_origen.notes.length, 0);
  assert.equal(fields.monto_origen.validityMessage, undefined);
  assert.equal(app.get('[data-operation-feedback]').hidden, true);
  assert.equal(app.get('[data-preview-button]').disabled, false);
});

test('el máximo de compra online por moneda se puede previsualizar sin redondear', async () => {
  for (const currency of ['USD', 'EUR', 'BRL', 'ARS', 'PYG']) {
    const amount = amountLimits.compra_online[currency].maximo;
    const { app, submit } = amountForm({ amount, currency });
    submit(); await settle();
    assert.equal(app.calls.length, 1, currency);
    assert.equal(JSON.parse(app.calls[0].options.body).monto, amount);
    assert.equal(app.toasts.length, 0, currency);
    assert.equal(app.get('[data-preview-card]').hidden, false);
  }
});

test('la comparación conserva las seis posiciones cerca del máximo del modelo', async () => {
  for (const amount of ['999999999999.999998', '999999999999.999999', '9.99999999999999999e11']) {
    const { app, submit } = amountForm({ amount, tipo: 'VENTA' });
    submit(); await settle();
    assert.equal(app.calls.length, 1, amount);
    assert.equal(app.toasts.length, 0);
  }
  const { app, submit } = amountForm({ amount: '999999999999.9999991', tipo: 'VENTA' });
  submit();
  assert.equal(app.calls.length, 0);
  assert.equal(app.toasts[0].message, excessiveAmountMessage);
});

test('precisión no representable se avisa sin redondear y permite ceros decimales sobrantes', async () => {
  for (const [currency, amount, message] of [
    ['USD', '1.001', 'Ingresá un monto con hasta 2 decimales.'],
    ['PYG', '1.1', 'Ingresá un monto sin decimales para esta moneda.']
  ]) {
    const { app, submit, edit } = amountForm({ currency, amount });
    submit();
    assert.equal(app.calls.length, 0);
    assert.deepEqual(app.toasts, [{ message, type: 'error' }]);
    edit('1.00000000'); submit(); await settle();
    assert.equal(app.calls.length, 1);
    assert.equal(app.toasts.length, 1);
  }
});

test('cambiar Compra y Venta actualiza min, max y step desde el JSON del servidor', () => {
  const { app, fields } = amountForm();
  assert.equal(fields.monto_origen.min, '0.01');
  assert.equal(fields.monto_origen.step, '0.01');
  assert.equal(fields.monto_origen.max, amountLimits.compra_online.USD.maximo);
  app.typeButtons[1].listeners.click();
  assert.equal(fields.tipo.value, 'VENTA');
  assert.equal(fields.monto_origen.min, amountLimits.general.minimo);
  assert.equal(fields.monto_origen.step, amountLimits.general.minimo);
  assert.equal(fields.monto_origen.max, amountLimits.general.maximo);
  app.typeButtons[0].listeners.click();
  assert.equal(fields.monto_origen.max, amountLimits.compra_online.USD.maximo);
});

test('cambiar origen a PYG actualiza su límite entero y rechaza una unidad de más', () => {
  const { app, fields, option, submit, edit } = amountForm();
  option.dataset.codigo = 'PYG';
  app.operationForm.listeners.change({ target: fields.moneda_origen_id });
  assert.equal(fields.monto_origen.step, '1');
  assert.equal(fields.monto_origen.min, '1');
  assert.equal(fields.monto_origen.max, '99999999');
  edit('100000000'); submit();
  assert.equal(app.calls.length, 0);
  assert.equal(app.toasts[0].message, excessiveAmountMessage);
});

test('Venta y Presencial conservan el límite general y precisión del modelo', async () => {
  for (const config of [{ tipo: 'VENTA' }, { presencial: true }, { tipo: 'VENTA', presencial: true }]) {
    const { app, fields, submit } = amountForm({ ...config, amount: '999999999999.123456' });
    assert.equal(fields.monto_origen.max, amountLimits.general.maximo);
    assert.equal(fields.monto_origen.step, amountLimits.general.minimo);
    submit(); await settle();
    assert.equal(app.calls.length, 1);
    assert.equal(app.toasts.length, 0);
  }
});

test('MONTO_INVALIDO y MONTO_PRECISION del backend liberan la previsualización sin errores inline', async () => {
  for (const [codigo, error] of [['MONTO_INVALIDO', 'Ingresá un monto válido mayor a cero.'],
    ['MONTO_PRECISION', 'Ingresá un monto con hasta 2 decimales.']]) {
    const { app, fields, submit } = amountForm();
    app.setFetch(async () => ({ ok: false, status: 400, json: async () => ({ codigo, error, detalles: { monto: [error] } }) }));
    submit(); await settle();
    assert.deepEqual(app.toasts, [{ message: error, type: 'error' }]);
    assert.equal(fields.monto_origen.notes.length, 0);
    assert.equal(app.get('[data-preview-button]').disabled, false);
  }
});

test('corregir un monto excesivo permite otra previsualización sin recargar la página', async () => {
  const { app, submit, edit } = amountForm({ amount: '1000000' });
  submit();
  edit('123.45'); submit(); await settle();
  assert.equal(app.toasts.length, 1);
  assert.equal(app.calls.length, 1);
  assert.equal(app.ui.state.payload.monto, '123.45');
  assert.equal(app.get('[data-preview-card]').hidden, false);
});

test('el cliente respeta límites nuevos del contexto y delega monedas sin tope online al general', async () => {
  const limits = { general: { maximo: '50.123', decimales: 3, minimo: '0.001' },
    compra_online: { USD: { maximo: '12.34', decimales: 2, minimo: '0.01' } } };
  const { app, fields, submit, edit, option } = amountForm({ amount: '12.35', limits });
  assert.equal(fields.monto_origen.max, '12.34');
  submit(); assert.equal(app.calls.length, 0);
  option.dataset.codigo = 'OTRA';
  app.operationForm.listeners.change({ target: fields.moneda_origen_id });
  assert.equal(fields.monto_origen.max, '50.123');
  edit('50.123'); submit(); await settle();
  assert.equal(app.calls.length, 1);
  assert.equal(app.toasts.length, 1);
});


test('rechazo de monto al confirmar libera el formulario para corregir sin repetir la creación', async () => {
  const { app, fields } = amountForm();
  Object.assign(app.ui.state, { preview: { tasa_comercial: { version: 1 } }, payload: { tipo: 'COMPRA' }, idempotencyKey: 'clave-monto' });
  app.get('[data-confirm-method]').value = '4';
  let posts = 0;
  app.setFetch(async () => { posts++; return { ok: false, status: 400, json: async () => ({
    codigo: 'MONTO_EXCESIVO', error: excessiveAmountMessage
  }) }; });
  const button = app.get('[data-confirm-operation]');
  app.ui.confirmOperation({ currentTarget: button });
  await settle();
  assert.equal(posts, 1);
  assert.deepEqual(app.toasts, [{ message: excessiveAmountMessage, type: 'error' }]);
  assert.deepEqual(app.closed, ['confirmar-operacion']);
  assert.equal(app.ui.state.preview, null);
  assert.equal(app.ui.state.confirmationPayload, null);
  assert.equal(app.ui.state.confirmationPending, false);
  assert.equal(app.get('[data-new-method]').disabled, false);
  assert.equal(app.get('[data-confirm-method]').disabled, false);
  assert.equal(fields.monto_origen.disabled, false);
  assert.equal(button.disabled, false);
});


function cashRecentRuntime(formFields = null, periodId = '') {
  return runtime(false, true, formFields, { presencial: true, cashRecent: true, periodId });
}
const cashPeriod = (id, name = 'Principal') => ({ id, caja_codigo: 'CAJA-' + id, caja_nombre: name });
const cashMovement = id => ({ id, fecha_registro: '2026-10-29T12:00:00Z', tipo: 'Ingreso',
  moneda: 'USD', importe: '123.456789', metodo: 'Efectivo', origen: 'Manual', estado: 'Registrado' });
const cashResponse = (periods, selected, movements = []) => ({ periodos: periods,
  periodo_id: selected, movimientos: movements, history_url: selected ? '/cajas/' + selected + '/historial/' : '/cajas/historial/' });
const jsonResponse = (data, status = 200) => ({ ok: status === 200, status, json: async () => data });

test('recientes Caja: cinco registros informativos, sin acciones ni consulta comercial', async () => {
  const app = cashRecentRuntime();
  const calls = [];
  app.setFetch(async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(cashResponse([cashPeriod(12)], 12, [9, 8, 7, 6, 5, 4].map(cashMovement)));
  });
  await app.ui.loadHistory();
  const html = app.get('[data-history-body]').innerHTML;
  assert.equal((html.match(/<tr>/g) || []).length, 5);
  assert.match(html, /#9.*#8.*#7.*#6.*#5/);
  assert.match(html, /Efectivo.*Manual.*Registrado/);
  assert.doesNotMatch(html, /button|data-detail|data-cancel|Liquidar|Stripe/);
  assert.deepEqual(calls.map(call => call.url), ['/cajas/recientes/']);
  assert.ok(calls.every(call => !call.options.method || call.options.method === 'GET'));
  app.get('[data-history-body]').listeners.click({ target: { closest() { throw new Error('No admite acciones'); } } });
  assert.equal(calls.length, 1);
  assert.equal(app.get('[data-cash-period]').value, '12');
  assert.equal(app.get('[data-cash-history-link]').attributes.href, '/cajas/12/historial/');
});

test('recientes Caja: varias cajas requieren selección y Actualizar conserva formulario', async () => {
  const amount = new Element(); amount.value = '123';
  const app = cashRecentRuntime({ monto_origen: amount });
  const calls = [];
  app.setFetch(async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(cashResponse([cashPeriod(12), cashPeriod(15)], url.includes('15') ? 15 : null,
      url.includes('15') ? [cashMovement(30)] : []));
  });
  await app.ui.loadHistory();
  assert.match(app.get('[data-history-body]').innerHTML, /Seleccioná una caja/);
  assert.equal(app.get('[data-cash-history-link]').attributes.href, '/cajas/historial/');
  const select = app.get('[data-cash-period]');
  select.value = '15'; select.listeners.change.call(select);
  await settle();
  app.get('[data-reload-history]').listeners.click();
  await settle();
  assert.equal(app.operationForm.elements.monto_origen.value, '123');
  assert.match(app.get('[data-history-body]').innerHTML, /#30/);
  assert.deepEqual(calls.map(call => call.url), ['/cajas/recientes/', '/cajas/recientes/?periodo_id=15', '/cajas/recientes/?periodo_id=15']);
  assert.ok(calls.every(call => !call.options.method));
});

test('recientes Caja: período cerrado borra filas y permite elegir otra Caja sin fallback', async () => {
  const app = cashRecentRuntime(null, '12');
  let closed = false;
  const calls = [];
  app.setFetch(async url => {
    calls.push(url);
    if (!closed) return jsonResponse(cashResponse([cashPeriod(12), cashPeriod(15)], 12, [cashMovement(9)]));
    if (url.includes('periodo_id=12')) return jsonResponse({ ...cashResponse([cashPeriod(15)], null), error: 'El período seleccionado ya no está disponible.' }, 400);
    return jsonResponse(cashResponse([cashPeriod(15)], 15, [cashMovement(40)]));
  });
  await app.ui.loadHistory(); closed = true;
  await app.ui.loadHistory();
  assert.doesNotMatch(app.get('[data-history-body]').innerHTML, /#9/);
  assert.equal(app.get('[data-cash-period]').value, '');
  assert.equal(app.get('[data-cash-history-link]').attributes.href, '/cajas/historial/');
  assert.match(app.toasts.at(-1).message, /ya no está disponible/);
  assert.doesNotMatch(app.get('[data-cash-recent-message]').textContent, /ya no está disponible/);
  assert.equal(calls.length, 2);
  const select = app.get('[data-cash-period]'); select.value = '15'; select.listeners.change.call(select);
  await settle();
  assert.match(app.get('[data-history-body]').innerHTML, /#40/);
});

test('recientes Caja: respuesta anterior no pisa Caja elegida después', async () => {
  const app = cashRecentRuntime(null, '12');
  let resolveFirst;
  app.setFetch(async url => url.includes('12') ? new Promise(resolve => { resolveFirst = resolve; })
    : jsonResponse(cashResponse([cashPeriod(12), cashPeriod(15)], 15, [cashMovement(40)])));
  const first = app.ui.loadHistory();
  const select = app.get('[data-cash-period]'); select.value = '15'; select.listeners.change.call(select);
  await settle();
  resolveFirst(jsonResponse(cashResponse([cashPeriod(12)], 12, [cashMovement(9)])));
  await first;
  assert.equal(select.value, '15');
  assert.match(app.get('[data-history-body]').innerHTML, /#40/);
  assert.doesNotMatch(app.get('[data-history-body]').innerHTML, /#9/);
  assert.equal(app.get('[data-reload-history]').disabled, false);
});

test('recientes Caja: vacíos y error conservan filas informativas sin duplicar mensaje', async () => {
  const app = cashRecentRuntime();
  for (const [response, expected] of [
    [cashResponse([], null), /No hay períodos abiertos/],
    [cashResponse([cashPeriod(12)], 12), /Todavía no hay movimientos/]
  ]) {
    app.setFetch(async () => jsonResponse(response)); await app.ui.loadHistory();
    assert.match(app.get('[data-history-body]').innerHTML, expected);
  }
  app.setFetch(async () => { throw new Error('Sin conexión'); }); await app.ui.loadHistory();
  assert.doesNotMatch(app.get('[data-cash-recent-message]').textContent, /Sin conexión/);
  assert.equal(app.toasts.length, 1);
  assert.equal(app.get('[data-reload-history]').disabled, false);
});

test('recientes Caja: otras pantallas conservan historial comercial aunque exista endpoint', async () => {
  for (const app of [runtime(), runtime(false, false, null, { cashRecent: true })]) {
    await app.ui.loadHistory();
    assert.deepEqual(app.calls.map(call => call.url), ['/historial/']);
  }
});


test('recientes Caja: crear efectivo abre detalle y refresca solo movimientos de Caja', async () => {
  const app = cashRecentRuntime(null, '12');
  Object.assign(app.ui.state, { preview: { tasa_comercial: { version: 1 } }, payload: { tipo: 'VENTA' }, idempotencyKey: 'misma-clave' });
  app.get('[data-confirm-method]').value = '1';
  const creada = { ...transaction(91), canal: 'PRESENCIAL', monto_origen: '10', monto_destino: '70',
    metodo_pago: { id: 1, naturaleza: 'EFECTIVO', activo: true } };
  const calls = [];
  app.setFetch(async (url, options = {}) => {
    calls.push({ url, options });
    const data = options.method === 'POST' ? { transaccion: creada }
      : url.startsWith('/cajas/recientes/') ? cashResponse([cashPeriod(12)], 12, [cashMovement(20)])
      : url.startsWith('/detalle/') ? { transaccion: creada }
      : { transaccion_id: 91, periodos: [] };
    return { ok: true, status: 200, json: async () => data };
  });
  app.ui.confirmOperation({ currentTarget: app.get('[data-confirm-operation]') });
  await settle();
  assert.equal(calls.filter(call => call.options.method === 'POST').length, 1);
  assert.ok(calls.some(call => call.url === '/cajas/recientes/?periodo_id=12'));
  assert.ok(calls.some(call => call.url === '/detalle/91/'));
  assert.equal(calls.some(call => /historial|pago|Stripe/.test(call.url)), false);
  assert.match(app.get('[data-history-body]').innerHTML, /#20/);
  assert.equal(app.opened.includes('detalle-operacion'), true);
  assert.equal(app.toasts.filter(toast => toast.type === 'success').length, 1);
});


test('recientes Caja: importe decimal grande conserva las seis posiciones sin redondear', async () => {
  const app = cashRecentRuntime();
  app.setFetch(async () => jsonResponse(cashResponse([cashPeriod(12)], 12,
    [{ ...cashMovement(50), importe: '999999999999.999999' }])));
  await app.ui.loadHistory();
  assert.match(app.get('[data-history-body]').innerHTML, /999\.999\.999\.999,999999/);
});
