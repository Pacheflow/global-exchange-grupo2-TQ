const test = require('node:test');
const assert = require('node:assert/strict');
const dashboard = require('../dashboard-analista.js');
function payload(currency = '') {
  return { filtros: { periodo: 'mes', etiqueta: 'Este mes', divisa: currency, desde: '2026-11-01', hasta: '2026-11-19', zona_horaria: 'America/Asuncion' },
    referencias: { USD: { valor: '6000', fecha: '2026-11-19T12:00:00Z' }, EUR: null },
    resumen: { mayor_variacion: { par: 'USD/PYG', porcentaje: '2' }, divisa_mas_operada: { divisa: currency || 'USD', operaciones: 3 }, tasas_vigentes: 2, ultima_actualizacion: '2026-11-19T12:00:00Z', operaciones: 3, compras: 2, ventas: 1 },
    evolucion: { par: (currency || 'USD') + '/PYG', puntos: [{ fecha: '2026-11-01T12:00:00Z', compra: '6000', venta: '6100' }, { fecha: '2026-11-19T12:00:00Z', compra: '6120', venta: '6200' }] },
    distribucion: { modo: currency ? 'tipo' : 'divisa', total: 3, categorias: [{ nombre: currency ? 'Compra' : 'USD', cantidad: 2, porcentaje: '66.66666667' }, { nombre: currency ? 'Venta' : 'EUR', cantidad: 1, porcentaje: '33.33333333' }] },
    variaciones: [{ par: 'USD/PYG', variacion: { porcentaje: '2', desde: '2026-11-01T12:00:00Z', hasta: '2026-11-19T12:00:00Z' } }],
    mercado: [{ par: 'USD/PYG', compra: '6120', venta: '6200', spread: '80', variacion: { porcentaje: '2' }, fecha: '2026-11-19T12:00:00Z' }] };
}
function runtime({ reduced = false, withChart = true, data = payload() } = {}) {
  class Element {
    constructor() { this.value = ''; this.textContent = ''; this.hidden = false; this.disabled = false; this.children = []; this.listeners = {}; this.attrs = {}; this.style = {}; this.classList = { add() {} }; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(k, v) { this.attrs[k] = v; }
    addEventListener(k, fn) { this.listeners[k] = fn; }
    removeEventListener(k) { delete this.listeners[k]; }
    checkValidity() { return true; }
    reportValidity() { return true; }
  }
  const elements = new Map(), get = selector => { if (!elements.has(selector)) elements.set(selector, new Element()); return elements.get(selector); };
  const root = new Element(); root.querySelector = get;
  root.ownerDocument = { createElement: () => new Element() };
  root.querySelectorAll = () => [get('custom-from'), get('custom-to')];
  root.dataset = { endpoint: '/api/tasas/dashboard-analista/' };
  get('#analista-inicial').textContent = JSON.stringify(data);
  const requests = [], listeners = {}, instances = [], history = [];
  const media = { matches: reduced, addEventListener(_, fn) { this.change = fn; }, removeEventListener() { delete this.change; } };
  const env = { matchMedia: () => media, AbortController,
    location: { href: 'http://localhost/panel/' },
    history: { pushState(_, __, url) { env.location.href = String(url); history.push(['push', String(url)]); }, replaceState(_, __, url) { env.location.href = String(url); history.push(['replace', String(url)]); } },
    addEventListener(k, fn) { listeners[k] = fn; }, removeEventListener(k) { delete listeners[k]; },
    fetch(url, options) { return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })); }
  };
  if (withChart) env.Chart = class {
    constructor(canvas, config) { Object.assign(this, config); this.updates = []; instances.push(this); }
    update(mode) { this.updates.push(mode); }
    destroy() { this.destroyed = true; }
  };
  const api = dashboard.init(root, env);
  return { root, api, env, get, requests, listeners, instances, history, media,
    reply(i, value, status = 200) { requests[i].resolve({ ok: status === 200, status, json: async () => value }); } };
}
const settled = () => new Promise(setImmediate);
test('formato exacto de tasas y spread sin perder decimales ni enteros grandes', () => {
  assert.equal(dashboard.amount('12345678901234.1234567890'), '12.345.678.901.234,123456789');
  assert.equal(dashboard.amount('0'), '0'); assert.equal(dashboard.amount('-0.01'), '-0,01');
  assert.match(dashboard.percent('2'), /^\+2[,.]00 %$/);
  assert.match(dashboard.percent('-2'), /^-2[,.]00 %$/);
  assert.equal(dashboard.percent(null), 'Sin histórico suficiente');
});
test('dos líneas, dona animada, tooltip preciso y tablas alternativas', () => {
  const ui = runtime(); assert.equal(ui.instances.length, 2);
  const line = ui.api.charts.line;
  assert.deepEqual(line.data.datasets.map(d => d.label), ['Compra', 'Venta']);
  assert.ok(line.options.animation.duration > 0);
  assert.equal(line.options.plugins.tooltip.callbacks.label({ dataset: { label: 'Compra' }, dataIndex: 1, datasetIndex: 0 }), 'Compra: 6.120 PYG');
  assert.equal(ui.get('[data-market-rows]').children.length, 1);
  assert.equal(ui.get('[data-analyst-kpi="rates"]').textContent, '2');
});
test('editar filtros solo prepara la selección; Aplicar actualiza sin reload', async () => {
  const ui = runtime(), original = ui.api.charts.line;
  ui.get('[data-filter="divisa"]').value = 'EUR'; ui.get('[data-filter="divisa"]').listeners.change();
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.get('[data-analyst-kpi="operated"]').textContent, 'USD');
  assert.equal(ui.history.length, 0);
  assert.equal(original.updates.length, 0);
  ui.get('[data-analyst-form]').listeners.submit({ preventDefault() {} });
  assert.match(ui.requests[0].url, /periodo=mes&divisa=EUR/);
  assert.equal(ui.get('[data-analyst-results]').attrs['aria-busy'], 'true');
  ui.reply(0, payload('EUR')); await settled();
  assert.equal(ui.api.charts.line, original); assert.equal(original.updates.length, 1);
  assert.equal(ui.get('[data-distribution-title]').textContent, 'Compras vs Ventas');
  assert.equal(ui.get('[data-analyst-kpi="operated"]').textContent, 'EUR');
  assert.equal(ui.get('[data-analyst-results]').attrs['aria-busy'], 'false');
  assert.match(ui.env.location.href, /divisa=EUR/);
});
test('tooltip se actualiza con los nuevos valores y no retiene el dataset anterior', async () => {
  const ui = runtime(), changed = payload('EUR'); changed.evolucion.puntos[1].compra = '7999.123';
  const loading = ui.api.load(new URLSearchParams('divisa=EUR'));
  ui.reply(0, changed); await loading;
  assert.equal(ui.api.charts.line.options.plugins.tooltip.callbacks.label({ dataset: { label: 'Compra' }, dataIndex: 1, datasetIndex: 0 }), 'Compra: 7.999,123 PYG');
});
test('período y fechas personalizadas no consultan hasta pulsar Aplicar', () => {
  const ui = runtime(); ui.get('[data-filter="periodo"]').value = 'personalizado';
  ui.get('[data-filter="desde"]').value = ''; ui.get('[data-filter="hasta"]').value = '';
  ui.get('[data-filter="periodo"]').listeners.change(); assert.equal(ui.requests.length, 0);
  ui.get('[data-filter="desde"]').value = '2026-11-01'; ui.get('[data-filter="desde"]').listeners.change(); assert.equal(ui.requests.length, 0);
  ui.get('[data-filter="hasta"]').value = '2026-11-19'; ui.get('[data-filter="hasta"]').listeners.change();
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.history.length, 0);
  ui.get('[data-analyst-form]').listeners.submit({ preventDefault() {} });
  assert.equal(ui.requests.length, 1); assert.match(ui.requests[0].url, /desde=2026-11-01&hasta=2026-11-19/);
  assert.equal(ui.get('[data-filter="desde"]').disabled, false);
});
test('limpiar carga mes y todas inmediatamente', async () => {
  const ui = runtime({ data: payload('EUR') }); ui.get('[data-analyst-reset]').listeners.click();
  assert.match(ui.requests[0].url, /periodo=mes&divisa=$/);
  ui.reply(0, payload()); await settled();
  assert.equal(ui.get('[data-distribution-title]').textContent, 'Operaciones por divisa');
});
test('solicitud vieja o abortada no pisa datos de la última selección', async () => {
  const ui = runtime(); const old = ui.api.load(new URLSearchParams('divisa=USD'));
  const current = ui.api.load(new URLSearchParams('divisa=EUR'));
  assert.equal(ui.requests[0].options.signal.aborted, true);
  ui.reply(1, payload('EUR')); await current; ui.reply(0, payload('USD')); await old;
  assert.equal(ui.get('[data-analyst-kpi="operated"]').textContent, 'EUR');
});
test('errores controlados mantienen datos, selección y URL exitosa', async () => {
  for (const status of [400, 401, 403, 503]) {
    const ui = runtime(); const load = ui.api.load(new URLSearchParams('divisa=EUR'));
    ui.reply(0, { error: 'Error controlado' }, status); await load;
    assert.equal(ui.get('[data-analyst-error]').hidden, false);
    assert.equal(ui.get('[data-analyst-kpi="operated"]').textContent, 'USD');
    assert.equal(ui.get('[data-filter="divisa"]').value, '');
    assert.equal(ui.history.length, 0);
  }
});
test('error de red o respuesta no JSON no expone contenido interno', async () => {
  const ui = runtime(); const load = ui.api.load(new URLSearchParams()); ui.requests[0].reject(new Error('secreto')); await load;
  assert.doesNotMatch(ui.get('[data-analyst-error]').textContent, /secreto/);
  assert.match(ui.get('[data-analyst-error]').textContent, /conexión/);
});
test('vacíos destruyen gráficos y muestran mensajes sin porcentajes ficticios', async () => {
  const ui = runtime(), charts = [...ui.instances], empty = payload();
  empty.evolucion.puntos = []; empty.distribucion = { modo: 'divisa', total: 0, categorias: [] }; empty.mercado = [];
  empty.variaciones = []; empty.resumen.mayor_variacion = null; empty.resumen.divisa_mas_operada = null;
  const load = ui.api.load(new URLSearchParams()); ui.reply(0, empty); await load;
  assert.ok(charts.every(c => c.destroyed)); assert.equal(ui.get('[data-evolution-empty]').hidden, false);
  assert.equal(ui.get('[data-distribution-empty]').hidden, false);
  assert.equal(ui.get('[data-analyst-kpi="variation"]').textContent, '—');
});
test('sin Chart se conservan tabla, leyenda y KPI', () => {
  const ui = runtime({ withChart: false }); assert.equal(ui.instances.length, 0);
  assert.equal(ui.get('[data-distribution-legend]').children.length, 2);
  assert.equal(ui.get('[data-market-rows]').children.length, 1);
  assert.equal(ui.get('[data-evolution-container]').hidden, true);
});
test('movimiento reducido desactiva entrada y transiciones de gráficos', async () => {
  const ui = runtime({ reduced: true }); assert.ok(ui.instances.every(c => c.options.animation === false));
  const load = ui.api.load(new URLSearchParams()); ui.reply(0, payload()); await load;
  assert.ok(ui.instances.every(c => c.updates.includes('none')));
});
test('popstate no agrega historial, falla restaura URL y destroy libera recursos', async () => {
  const ui = runtime(); ui.env.location.href = 'http://localhost/panel/?divisa=EUR';
  let load = ui.listeners.popstate(); ui.reply(0, payload('EUR')); await load; assert.equal(ui.history.length, 0);
  ui.env.location.href = 'http://localhost/panel/?divisa=USD';
  load = ui.listeners.popstate(); ui.reply(1, { error: 'Error' }, 400); await load;
  assert.match(ui.env.location.href, /divisa=EUR/); assert.equal(ui.history[0][0], 'replace');
  assert.equal(dashboard.init(ui.root, ui.env), ui.api);
  ui.api.destroy(); assert.equal(ui.listeners.popstate, undefined); assert.ok(ui.instances.every(c => c.destroyed));
});
