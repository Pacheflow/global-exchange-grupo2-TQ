const test = require('node:test');
const assert = require('node:assert/strict');
const dashboard = require('../dashboard.js');

function payload({ divisa = '', amount = '51660.500000', operations = 3 } = {}) {
  return {
    filtros: { periodo: 'mes', etiqueta: 'Este mes', divisa, desde: '2026-11-01', hasta: '2026-11-19', agrupacion: 'dia' },
    resumen: { ganancia_pyg: amount, volumen_pyg: '738000.000000', operaciones: operations, compras: operations ? 2 : 0, ventas: operations ? 1 : 0, excluidas: 0 },
    evolucion: [{ periodo: '2026-11-01', etiqueta: '01/11/2026', ganancia_pyg: amount, excluidas: 0 }],
    distribucion: { modo: divisa ? 'tipo' : 'divisa', titulo: divisa ? 'Compras vs Ventas' : 'Ganancia por divisa (%)', categorias: divisa ? [{ categoria: 'Compra', cantidad: 2, porcentaje: '66.67' }, { categoria: 'Venta', cantidad: 1, porcentaje: '33.33' }] : [{ categoria: 'USD', ganancia_pyg: amount, porcentaje: '100.00' }] },
    actividad_reciente: operations ? [{ id: 12, fecha: '19/11/2026 12:00', cliente: '<script>cliente</script>', tipo: 'Compra', estado: 'Completada', origen: '100.500000', divisa_origen: 'USD', destino: '700000', divisa_destino: 'PYG', detalle: '/operaciones/reportes/transacciones/12/' }] : []
  };
}

function runtime({ reduced = false, data = payload(), withChart = true } = {}) {
  class Element {
    constructor() { this.children = []; this.style = {}; this.attrs = {}; this.listeners = {}; this.textContent = ''; this.value = ''; this.hidden = false; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(name, value) { this.attrs[name] = value; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    removeEventListener(name) { delete this.listeners[name]; }
    reportValidity() { return true; }
  }
  const elements = new Map(), get = selector => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const root = new Element(); root.querySelector = get;
  root.ownerDocument = { createElement: () => new Element() };
  root.querySelectorAll = () => [get('custom-from'), get('custom-to')];
  root.dataset = { endpoint: '/api/operaciones/dashboard/metricas/' };
  get('#dashboard-inicial').textContent = JSON.stringify(data);
  const requests = [], listeners = {}, frames = new Map(), instances = [], history = [];
  let frameId = 0;
  const media = { matches: reduced, addEventListener(_, cb) { this.change = cb; }, removeEventListener() { this.change = null; } };
  const env = {
    matchMedia: () => media, performance: { now: () => 0 },
    requestAnimationFrame(cb) { frames.set(++frameId, cb); return frameId; },
    cancelAnimationFrame(id) { frames.delete(id); },
    AbortController,
    location: { href: 'http://localhost/panel/' },
    history: {
      pushState(_, __, url) { env.location.href = String(url); history.push(['push', String(url)]); },
      replaceState(_, __, url) { env.location.href = String(url); history.push(['replace', String(url)]); }
    },
    addEventListener(name, cb) { listeners[name] = cb; }, removeEventListener(name) { delete listeners[name]; },
    fetch(url, options) { return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })); }
  };
  class Chart {
    constructor(canvas, config) { Object.assign(this, config); this.canvas = canvas; this.updates = []; instances.push(this); }
    update(mode) { this.updates.push(mode); }
    resize() { this.resized = true; }
    destroy() { this.destroyed = true; }
  }
  if (withChart) env.Chart = Chart;
  const api = dashboard.init(root, env);
  return { root, get, api, env, requests, listeners, media, frames, instances, history,
    flushFrames(now = 1000) { const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(cb => cb(now)); },
    reply(index, value, status = 200) { requests[index].resolve({ ok: status === 200, status, json: async () => value }); }
  };
}

test('formato PYG exacto HALF_UP con enteros grandes, sin float financiero', () => {
  assert.equal(dashboard.pyg('51660.500000'), '51.661 PYG');
  assert.equal(dashboard.pyg('0.000000'), '0 PYG');
  assert.equal(dashboard.pyg('123456789012345678901234567890.5'), '123.456.789.012.345.678.901.234.567.891 PYG');
  assert.equal(dashboard.decimal('1234.560000'), '1.234,56');
});

test('Chart.js local tiene versión fijada y exporta un solo motor', () => {
  assert.equal(require('../../vendor/chartjs/chart.umd.min.js').version, '4.5.1');
});

test('entrada anima barras, dona y KPI; termina exactamente en PYG', () => {
  const ui = runtime();
  assert.equal(ui.instances.length, 2);
  assert.equal(ui.instances[0].type, 'bar');
  assert.equal(ui.instances[1].type, 'doughnut');
  assert.equal(ui.instances[0].options.animation.duration, 800);
  assert.equal(ui.instances[1].options.animation.animateRotate, true);
  assert.equal(ui.frames.size, 5);
  ui.flushFrames(400);
  assert.notEqual(ui.get('[data-kpi="ganancia_pyg"]').textContent, '51.661 PYG');
  ui.flushFrames();
  assert.equal(ui.get('[data-kpi="ganancia_pyg"]').textContent, '51.661 PYG');
  assert.equal(ui.get('[data-kpi="volumen_pyg"]').textContent, '738.000 PYG');
});

test('tooltips usan valor exacto del backend y valores accesibles fuera del canvas', () => {
  const ui = runtime({ reduced: true });
  assert.equal(ui.instances[0].options.plugins.tooltip.callbacks.label({ dataIndex: 0 }), 'Ganancia: 51.661 PYG');
  assert.equal(ui.instances[1].options.plugins.tooltip.callbacks.label({ dataIndex: 0 }), '100 % · Ganancia: 51.661 PYG');
  assert.equal(ui.get('[data-evolution-table]').children[0].children[1].textContent, '51.661 PYG');
  assert.equal(ui.get('[data-dashboard-activity]').children[0].children[2].textContent, '<script>cliente</script>');
});

test('prefers-reduced-motion evita animaciones iniciales y actualizaciones', async () => {
  const ui = runtime({ reduced: true });
  assert.equal(ui.frames.size, 0);
  assert.equal(ui.instances[0].options.animation, false);
  const request = ui.api.load(new URLSearchParams('periodo=mes&divisa=USD'));
  ui.reply(0, payload({ divisa: 'USD' })); await request;
  assert.equal(ui.instances[0].updates.at(-1), 'none');
  assert.equal(ui.frames.size, 0);
});

test('actualiza todo sin recarga y conserva instancias para transición de valores', async () => {
  const ui = runtime();
  const request = ui.api.load(new URLSearchParams('periodo=mes&divisa=USD'));
  assert.equal(ui.get('[data-dashboard-results]').attrs['aria-busy'], 'true');
  assert.equal(ui.requests[0].options.credentials, 'same-origin');
  ui.reply(0, payload({ divisa: 'USD', amount: '750000' })); await request;
  ui.flushFrames();
  assert.equal(ui.instances.length, 2);
  assert.equal(ui.instances[0].data.datasets[0].data[0], 750000);
  assert.equal(ui.instances[0].updates.length, 1);
  assert.equal(ui.get('[data-distribution-title]').textContent, 'Compras vs Ventas');
  assert.equal(ui.get('[data-kpi="ganancia_pyg"]').textContent, '750.000 PYG');
  assert.equal(ui.get('[data-dashboard-results]').attrs['aria-busy'], 'false');
  assert.match(ui.env.location.href, /divisa=USD/);
});

test('respuestas antiguas y sus errores no pisan selección ni estado de carga nuevo', async () => {
  const ui = runtime({ reduced: true });
  const first = ui.api.load(new URLSearchParams('divisa=USD'));
  const second = ui.api.load(new URLSearchParams('divisa=EUR'));
  assert.equal(ui.requests[0].options.signal.aborted, true);
  ui.reply(0, payload({ divisa: 'USD' })); await first;
  assert.equal(ui.get('[data-dashboard-results]').attrs['aria-busy'], 'true');
  ui.reply(1, payload({ divisa: 'EUR' })); await second;
  assert.equal(ui.get('[data-dashboard-currency]').textContent, 'EUR');
  assert.equal(ui.history.length, 1);
});

test('errores 400/401/403/503 mantienen datos y filtros exitosos con aviso controlado', async () => {
  for (const code of [400, 401, 403, 503]) {
    const ui = runtime({ reduced: true });
    const request = ui.api.load(new URLSearchParams('divisa=EUR'));
    ui.reply(0, { error: 'Filtro o servicio no disponible' }, code); await request;
    assert.equal(ui.get('[data-dashboard-error]').hidden, false);
    assert.match(ui.get('[data-dashboard-error]').textContent, /última consulta exitosa/);
    assert.equal(ui.get('[data-kpi="ganancia_pyg"]').textContent, '51.661 PYG');
    assert.equal(ui.get('[data-filter="divisa"]').value, '');
    assert.equal(ui.history.length, 0);
  }
});

test('red fallida no expone detalles internos y permite reintentar', async () => {
  const ui = runtime({ reduced: true });
  const request = ui.api.load(new URLSearchParams('divisa=USD'));
  ui.requests[0].reject(new TypeError('internal detail')); await request;
  assert.doesNotMatch(ui.get('[data-dashboard-error]').textContent, /internal detail/);
  assert.match(ui.get('[data-dashboard-error]').textContent, /Revisá la conexión/);
  const retry = ui.api.load(new URLSearchParams('divisa=USD'));
  ui.reply(1, payload({ divisa: 'USD' })); await retry;
  assert.equal(ui.get('[data-dashboard-error]').hidden, true);
});

test('filtros vacíos ocultan gráficos pero conservan ceros y contenedores', () => {
  const data = payload({ amount: '0', operations: 0 }); data.distribucion.categorias = [];
  const ui = runtime({ reduced: true, data });
  assert.equal(ui.get('[data-evolution-container]').hidden, true);
  assert.equal(ui.get('[data-distribution-container]').hidden, true);
  assert.equal(ui.get('[data-evolution-empty]').textContent, 'No hay datos disponibles para los filtros seleccionados.');
  assert.equal(ui.get('[data-kpi="operaciones"]').textContent, '0');
  assert.equal(ui.get('[data-kpi="ganancia_pyg"]').textContent, '0 PYG');
});

test('sin librería quedan tabla y leyenda disponibles sin romper los KPI', () => {
  const ui = runtime({ reduced: true, withChart: false });
  assert.equal(ui.instances.length, 0);
  assert.equal(ui.get('[data-kpi="ganancia_pyg"]').textContent, '51.661 PYG');
  assert.match(ui.get('[data-evolution-empty]').textContent, /Consultá la tabla/);
});

test('editar filtros no consulta; Aplicar envía período, divisa y fechas preparados', async () => {
  const ui = runtime({ reduced: true });
  const query = dashboard.queryFor({ periodo: 'personalizado', divisa: 'EUR', desde: '2026-01-01', hasta: '2026-02-01' });
  assert.equal(query.get('desde'), '2026-01-01'); assert.equal(query.get('hasta'), '2026-02-01');
  ui.get('[data-filter="periodo"]').value = 'personalizado';
  ui.get('[data-filter="periodo"]').listeners.change();
  assert.equal(ui.get('[data-filter="desde"]').disabled, false);
  ui.get('[data-filter="divisa"]').value = 'EUR';
  ui.get('[data-filter="divisa"]').listeners.change();
  ui.get('[data-filter="desde"]').value = '2026-01-01';
  ui.get('[data-filter="desde"]').listeners.change();
  ui.get('[data-filter="hasta"]').value = '2026-02-01';
  ui.get('[data-filter="hasta"]').listeners.change();
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.get('[data-dashboard-currency]').textContent, 'Todas');
  assert.equal(ui.history.length, 0);
  ui.get('[data-dashboard-form]').listeners.submit({ preventDefault() {} });
  assert.equal(ui.requests.length, 1);
  assert.match(ui.requests[0].url, /periodo=personalizado&divisa=EUR&desde=2026-01-01&hasta=2026-02-01/);
  ui.reply(0, payload({ divisa: 'EUR' })); await new Promise(setImmediate);
});

test('limpiar carga inmediatamente este mes y todas las divisas', async () => {
  const ui = runtime({ reduced: true, data: payload({ divisa: 'USD' }) });
  ui.get('[data-dashboard-reset]').listeners.click();
  assert.equal(ui.get('[data-filter="periodo"]').value, 'mes');
  assert.equal(ui.get('[data-filter="divisa"]').value, '');
  assert.equal(ui.requests.length, 1);
  assert.equal(ui.get('[data-dashboard-currency]').textContent, 'USD');
  assert.match(ui.requests[0].url, /periodo=mes&divisa=$/);
  ui.reply(0, payload()); await new Promise(setImmediate);
  assert.equal(ui.get('[data-dashboard-currency]').textContent, 'Todas');
  assert.equal(new URL(ui.env.location.href).search, '?periodo=mes&divisa=');
});

test('atrás/adelante recarga datos sin agregar historial y cleanup libera gráficos', async () => {
  const ui = runtime({ reduced: true });
  ui.env.location.href = 'http://localhost/panel/?periodo=mes&divisa=EUR';
  const request = ui.listeners.popstate();
  ui.reply(0, payload({ divisa: 'EUR' })); await request;
  assert.equal(ui.history.length, 0);
  assert.equal(ui.get('[data-dashboard-currency]').textContent, 'EUR');
  assert.equal(dashboard.init(ui.root, ui.env), ui.api);
  ui.api.destroy();
  assert.equal(ui.listeners.popstate, undefined);
  assert.ok(ui.instances.every(chart => chart.destroyed));
});

test('error de una solicitud antigua no apaga la carga de otra en curso', async () => {
  const ui = runtime({ reduced: true });
  const old = ui.api.load(new URLSearchParams('divisa=USD'));
  const current = ui.api.load(new URLSearchParams('divisa=EUR'));
  ui.requests[0].reject(new Error('old request')); await old;
  assert.equal(ui.get('[data-dashboard-error]').hidden, true);
  assert.equal(ui.get('[data-dashboard-results]').attrs['aria-busy'], 'true');
  ui.reply(1, payload({ divisa: 'EUR' })); await current;
  assert.equal(ui.get('[data-dashboard-currency]').textContent, 'EUR');
});

test('cambio de preferencia de movimiento cancela contadores y termina valores exactos', () => {
  const ui = runtime();
  assert.equal(ui.frames.size, 5);
  ui.media.matches = true; ui.media.change();
  assert.equal(ui.frames.size, 0);
  assert.equal(ui.get('[data-kpi="ganancia_pyg"]').textContent, '51.661 PYG');
  assert.equal(ui.instances[0].updates.at(-1), 'none');
});

test('popstate fallido restaura URL y selección correspondientes a los datos visibles', async () => {
  const ui = runtime({ reduced: true });
  ui.env.location.href = 'http://localhost/panel/?periodo=otro';
  const request = ui.listeners.popstate();
  ui.reply(0, { error: 'Período inválido.' }, 400); await request;
  assert.equal(ui.get('[data-filter="periodo"]').value, 'mes');
  assert.match(ui.env.location.href, /periodo=mes/);
  assert.equal(ui.history[0][0], 'replace');
});
