const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(setImmediate); };

function runtime() {
  const elements = new Map();
  const get = selector => {
    if (!elements.has(selector)) elements.set(selector, { dataset: {}, textContent: '', hidden: false, value: '',
      listeners: {}, attributes: {}, querySelector: get,
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, fn) { this.listeners[name] = fn; } });
    return elements.get(selector);
  };
  const page = get('[data-ge-api]'); page.dataset = { geApi: 'test', historyUrl: '/history', currenciesUrl: '/currencies', simulateUrl: '/simulate' };
  const toasts = [];
  const context = { document: { querySelector: get },
    window: { GEApp: { toast(message, type) { toasts.push({ message, type }); }, authenticationError() { return null; } } },
    fetch: async () => ({ ok: false, json: async () => ({ error: 'El servicio no está disponible.' }) }) };
  const source = fs.readFileSync(path.join(__dirname, '../frontend-api.js'), 'utf8').replace(/  if \(page.dataset.geApi === 'currencies'\)[\s\S]*$/, '  globalThis.ui = { fail, loadRates, renderReferenceRates, initSimulator, renderPayments, paymentForm };\n}());');
  vm.runInNewContext(source, context);
  return { ...context, get, toasts, setFetch(fn) { context.fetch = fn; } };
}

test('catálogos y métodos muestran un toast de error y un estado neutral sin repetir el mensaje', async () => {
  const ui = runtime();
  ui.ui.fail(new Error('No se pudo cargar el catálogo.'));
  assert.equal(ui.toasts.length, 1);
  assert.equal(ui.toasts[0].message, 'No se pudo cargar el catálogo.');
  assert.match(ui.get('[data-api-body]').innerHTML, /Datos no disponibles/);
  assert.doesNotMatch(ui.get('[data-api-body]').innerHTML, /No se pudo cargar el catálogo/);
  ui.toasts.length = 0;
  await ui.ui.loadRates();
  assert.equal(ui.toasts.length, 1);
  for (const selector of ['[data-rates-body]', '[data-history-body]']) {
    assert.doesNotMatch(ui.get(selector).innerHTML, /El servicio no está disponible/);
  }
});

test('advertencia de tasas se presenta flotante y conserva solamente el estado del dato', () => {
  const ui = runtime();
  ui.ui.renderReferenceRates({ estado: 'desactualizado', mensaje: 'Se muestran tasas de respaldo.', tasas_referencia: [], tasas_comerciales: [] });
  assert.equal(ui.toasts.length, 1);
  assert.equal(ui.toasts[0].type, 'warning');
  assert.equal(ui.get('[data-reference-message]').hidden, true);
  assert.equal(ui.get('[data-reference-message]').textContent, '');
  assert.equal(ui.get('[data-reference-status]').textContent, 'Respaldo disponible');
});

test('simulador conserva validación de monto inline y errores del backend solo en toast', async () => {
  const ui = runtime();
  ui.fetch = undefined;
  ui.ui.initSimulator();
  await settle();
  ui.toasts.length = 0; // Ignorar fallo de catálogo inicial de la fixture.
  const amount = ui.get('[data-sim-amount]');
  const from = ui.get('[data-sim-from]'); const to = ui.get('[data-sim-to]');
  amount.value = '-1'; from.value = '1'; to.value = '2';
  from.listeners.change();
  assert.equal(ui.get('[data-sim-error]').hidden, false);
  assert.equal(ui.get('[data-sim-error]').textContent, 'El monto debe ser mayor que cero.');
  assert.equal(ui.toasts.length, 0);
  amount.value = '10'; from.listeners.change();
  await settle();
  assert.equal(ui.toasts.length, 1);
  assert.equal(ui.toasts[0].message, 'El servicio no está disponible.');
  assert.equal(ui.get('[data-sim-error]').hidden, true);
  assert.equal(ui.get('[data-sim-error]').textContent, '');
  assert.equal(ui.get('[data-sim-result]').textContent, '—');
});


test('listado de métodos muestra ambos tipos y conserva registros sin clasificar', () => {
  const ui = runtime();
  ui.ui.renderPayments([
    { id: 1, nombre: 'Tarjeta', naturaleza: 'ELECTRONICO', naturaleza_display: 'Electrónico', activo: true },
    { id: 2, nombre: 'Caja', naturaleza: 'EFECTIVO', naturaleza_display: 'Efectivo', activo: true },
    { id: 3, nombre: 'Legado', naturaleza: 'SIN_CLASIFICAR', naturaleza_display: 'Sin clasificar', activo: false }
  ]);
  const html = ui.get('[data-api-body]').innerHTML;
  assert.match(html, /Tarjeta<\/strong><\/td><td>Electrónico<\/td>/);
  assert.match(html, /Caja<\/strong><\/td><td>Efectivo<\/td>/);
  assert.match(html, /Legado<\/strong><\/td><td>Sin clasificar<\/td>/);
});

function paymentDialog(item) {
  const ui = runtime();
  const controls = {
    nombre: { value: item ? item.nombre : 'Nuevo método' },
    descripcion: { value: '' }, naturaleza: { value: 'EFECTIVO' }, activo: { checked: true }
  };
  const form = { elements: controls, reportValidity: () => true };
  const box = ui.get('dialog');
  const get = box.querySelector;
  box.querySelector = selector => selector === 'form' ? form : get(selector);
  box.remove = () => {};
  ui.document.getElementById = () => null;
  ui.document.createElement = () => box;
  ui.document.body = { appendChild() {} };
  ui.get('input,select,button').focus = () => {};
  const calls = [];
  ui.setFetch(async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ message: 'Guardado', metodos: [] }) };
  });
  ui.get('[data-ge-api]').dataset = { geApi: 'payments', createUrl: '/create', editUrl: '/edit/0/', listUrl: '/list' };
  ui.ui.paymentForm(item);
  return { ui, box, form, calls };
}

test('crear método exige selección visible y envía la naturaleza elegida', async () => {
  const { ui, box, calls } = paymentDialog(null);
  assert.match(box.innerHTML, /TIPO/);
  assert.match(box.innerHTML, /name="naturaleza" required/);
  assert.match(box.innerHTML, /value="ELECTRONICO"/);
  assert.match(box.innerHTML, /value="EFECTIVO"/);
  assert.doesNotMatch(box.innerHTML, /value="SIN_CLASIFICAR"/);
  ui.get('[data-confirm]').listeners.click();
  await settle();
  assert.equal(calls[0].url, '/create');
  assert.equal(JSON.parse(calls[0].options.body).naturaleza, 'EFECTIVO');
});

test('editar preserva tipo actual y legacy exige escoger una clasificación', async () => {
  const current = paymentDialog({ id: 4, nombre: 'Tarjeta', naturaleza: 'ELECTRONICO', activo: true });
  assert.match(current.box.innerHTML, /value="ELECTRONICO" selected/);
  current.ui.get('[data-confirm]').listeners.click();
  await settle();
  assert.equal(current.calls[0].url, '/edit/4/');
  const legacy = paymentDialog({ id: 5, nombre: 'Legado', naturaleza: 'SIN_CLASIFICAR', activo: true });
  assert.match(legacy.box.innerHTML, /value="" selected/);
  assert.doesNotMatch(legacy.box.innerHTML, /value="SIN_CLASIFICAR"/);
  legacy.form.reportValidity = () => false;
  legacy.ui.get('[data-confirm]').listeners.click();
  await settle();
  assert.equal(legacy.calls.length, 0);
});
