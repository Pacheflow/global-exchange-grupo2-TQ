const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(setImmediate); };

test('conversor público separa validaciones locales de errores generales sin alertas duplicadas', async () => {
  const elements = new Map();
  const get = selector => {
    if (!elements.has(selector)) elements.set(selector, { value: '', textContent: '', hidden: false, listeners: {},
      querySelector: get, addEventListener(name, fn) { this.listeners[name] = fn; } });
    return elements.get(selector);
  };
  const toasts = []; let requests = 0;
  const context = { document: { readyState: 'loading', addEventListener() {}, querySelector: get,
      createElement() { return { textContent: '', get innerHTML() { return this.textContent; } }; } },
    window: { GEApp: { toast(message, type) { toasts.push({ message, type }); } } },
    fetch: async () => { requests++; return { ok: false, status: 503, json: async () => ({ error: 'El servicio no está disponible.' }) }; } };
  const source = fs.readFileSync(path.join(__dirname, '../landing.js'), 'utf8').replace(
    "  if (document.readyState === 'loading')", "  globalThis.ui = { initConverter };\n  if (document.readyState === 'loading')");
  vm.runInNewContext(source, context);
  const landing = { querySelector: get, dataset: { simulateUrl: '/simulate' } };
  context.ui.initConverter(landing, [{ id: 1, codigo: 'USD' }, { id: 2, codigo: 'EUR' }]);
  const amount = get('#ge-converter-amount'); const from = get('[data-converter-from]'); const to = get('[data-converter-to]');
  amount.value = '-1'; from.value = '1'; to.value = '2';
  from.listeners.change();
  assert.equal(get('[data-converter-error]').textContent, 'El monto debe ser mayor que cero.');
  assert.equal(get('[data-converter-error]').hidden, false);
  assert.equal(toasts.length, 0);
  assert.equal(requests, 0);
  amount.value = '10'; from.listeners.change();
  await settle();
  assert.equal(requests, 1);
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].message, 'El servicio no está disponible.');
  assert.equal(toasts[0].type, 'error');
  assert.equal(get('[data-converter-error]').hidden, true);
  assert.equal(get('[data-converter-error]').textContent, '');
  assert.equal(get('[data-converter-output]').textContent, '—');
});
