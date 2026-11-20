/* Mercado del analista: solo lectura; no importa lógica de métricas administrativas. */
(function (global) {
  'use strict';
  const palette = ['#3d5afe', '#22c55e', '#fbbf24', '#f87171', '#38bdf8', '#a78bfa'];
  function amount(value) {
    if (value === null || value === undefined || value === '') return '—';
    const [whole, fraction] = String(value).split('.');
    const decimals = (fraction || '').replace(/0+$/, '');
    return whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (decimals ? ',' + decimals : '');
  }
  function percent(value) {
    if (value === null || value === undefined) return 'Sin histórico suficiente';
    const n = Number(value);
    return (n > 0 ? '+' : '') + n.toLocaleString('es-PY', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' %';
  }
  function queryFor(values) {
    const query = new URLSearchParams({ periodo: values.periodo || 'mes', divisa: values.divisa || '' });
    if (values.periodo === 'personalizado') {
      query.set('desde', values.desde || ''); query.set('hasta', values.hasta || '');
    }
    return query;
  }
  function init(root, env = global) {
    if (root._analyst) return root._analyst;
    const doc = root.ownerDocument, get = selector => root.querySelector(selector);
    const fields = Object.fromEntries(['periodo', 'divisa', 'desde', 'hasta'].map(k => [k, get('[data-filter="' + k + '"]')]));
    const form = get('[data-analyst-form]'), results = get('[data-analyst-results]');
    const error = get('[data-analyst-error]'), status = get('[data-analyst-status]');
    const media = env.matchMedia('(prefers-reduced-motion: reduce)');
    const charts = {};
    let active = null, sequence = 0, controller = null, destroyed = false;
    function node(tag, value, className) {
      const element = doc.createElement(tag); element.textContent = value;
      if (className) element.className = className;
      return element;
    }
    function date(value) {
      return value ? new Date(value).toLocaleString('es-PY', { timeZone: active?.filtros.zona_horaria || 'America/Asuncion', dateStyle: 'short', timeStyle: 'short' }) : 'Sin actualización';
    }
    function variationClass(value) { return Number(value) > 0 ? 'is-positive' : Number(value) < 0 ? 'is-negative' : 'is-neutral'; }
    function customFields() {
      const custom = fields.periodo.value === 'personalizado';
      root.querySelectorAll('[data-custom-date]').forEach(el => { el.hidden = !custom; });
      ['desde', 'hasta'].forEach(k => { fields[k].disabled = !custom; fields[k].required = custom; });
    }
    function sync(filters) {
      Object.keys(fields).forEach(k => { fields[k].value = filters[k] || ''; }); customFields();
    }
    function params() { return queryFor(Object.fromEntries(Object.entries(fields).map(([k, el]) => [k, el.value]))); }
    function rows(target, entries, empty, columns) {
      target.replaceChildren(...(entries.length ? entries.map(values => {
        const row = doc.createElement('tr'); values.forEach(value => row.append(node('td', value))); return row;
      }) : [(() => { const row = doc.createElement('tr'), cell = node('td', empty); cell.colSpan = columns; row.append(cell); return row; })()]));
    }
    function chart(key, canvas, type, data, options) {
      if (!env.Chart) return;
      if (charts[key]) {
        charts[key].data = data;
        charts[key].options = { responsive: true, maintainAspectRatio: false, ...options, animation: media.matches ? false : { duration: 600 } };
        charts[key].update(media.matches ? 'none' : undefined);
      } else {
        charts[key] = new env.Chart(canvas, { type, data, options: { responsive: true, maintainAspectRatio: false,
          animation: media.matches ? false : { duration: 650, easing: 'easeOutQuart' }, ...options } });
      }
    }
    function render(data, initial = false) {
      active = data;
      const summary = data.resumen, change = summary.mayor_variacion, operated = summary.divisa_mas_operada;
      const values = { usd: amount(data.referencias.USD?.valor), eur: amount(data.referencias.EUR?.valor),
        variation: change ? percent(change.porcentaje) : '—', operated: operated?.divisa || '—',
        rates: String(summary.tasas_vigentes), updated: date(summary.ultima_actualizacion) };
      Object.entries(values).forEach(([key, value]) => { get('[data-analyst-kpi="' + key + '"]').textContent = value; });
      get('[data-analyst-kpi-note="variation"]').textContent = change ? change.par + ' · compra comercial' : 'Sin histórico suficiente';
      get('[data-analyst-kpi="variation"]').className = change ? variationClass(change.porcentaje) : 'is-neutral';
      get('[data-analyst-kpi-note="operated"]').textContent = operated ? operated.operaciones + ' operaciones completadas' : 'Sin operaciones completadas';
      ['USD', 'EUR'].forEach(code => { get('[data-analyst-kpi-note="' + code.toLowerCase() + '"]').textContent = data.referencias[code] ? 'Referencia vigente · global · ' + date(data.referencias[code].fecha) : 'Sin referencia vigente'; });
      get('[data-analyst-context]').textContent = data.filtros.etiqueta + ' · ' + (data.filtros.divisa || 'Todas las divisas') + ' · ' + data.filtros.desde + ' — ' + data.filtros.hasta;
      get('[data-analyst-pair]').textContent = data.evolucion.par + ' · ' + data.filtros.etiqueta;
      const points = data.evolucion.puntos;
      rows(get('[data-evolution-rows]'), points.map(p => [date(p.fecha), amount(p.compra), amount(p.venta)]), 'No hay histórico disponible para los filtros seleccionados.', 3);
      const showLine = points.length > 0 && !!env.Chart;
      get('[data-evolution-container]').hidden = !showLine; get('[data-evolution-empty]').hidden = showLine;
      get('[data-evolution-empty]').textContent = !points.length ? 'No hay histórico disponible para los filtros seleccionados.' : 'El gráfico no está disponible. Consultá los valores en la tabla.';
      if (showLine) {
        const data = { datasets: ['compra', 'venta'].map((key, i) => ({ label: i ? 'Venta' : 'Compra',
          data: points.map(p => ({ x: Date.parse(p.fecha), y: Number(p[key]) })), borderColor: palette[i],
          backgroundColor: palette[i], borderWidth: 2, pointRadius: points.length === 1 ? 4 : 2,
          pointHoverRadius: 5, tension: 0, fill: false })) };
        chart('line', get('[data-analyst-line]'), 'line', data, {
          interaction: { mode: 'index', intersect: false },
          plugins: { legend: { labels: { color: '#c7daf5', usePointStyle: true } }, tooltip: { callbacks: {
            title: items => points[items[0]?.dataIndex] ? date(points[items[0].dataIndex].fecha) : '',
            label: context => context.dataset.label + ': ' + amount(points[context.dataIndex][context.datasetIndex ? 'venta' : 'compra']) + ' PYG'
          } } },
          scales: { x: { type: 'linear', grid: { display: false }, ticks: { color: '#9bb5da', maxTicksLimit: 5, callback: value => new Date(value).toLocaleDateString('es-PY', { timeZone: active.filtros.zona_horaria, day: '2-digit', month: 'short' }) } },
            y: { ticks: { color: '#9bb5da', callback: value => amount(value) }, grid: { color: '#1c2f50' } } }
        });
      } else if (charts.line) { charts.line.destroy(); delete charts.line; }
      const distribution = data.distribucion, categories = distribution.categorias;
      get('[data-distribution-title]').textContent = distribution.modo === 'tipo' ? 'Compras vs Ventas' : 'Operaciones por divisa';
      get('[data-distribution-note]').textContent = distribution.modo === 'tipo' ? 'Cantidad de compras y ventas completadas de la divisa seleccionada.' : 'Participaciones por divisa. Cada cruce cuenta una vez para cada divisa activa; porcentajes sobre esas participaciones.';
      get('[data-operation-counts]').textContent = summary.operaciones + ' operaciones · ' + summary.compras + ' compras · ' + summary.ventas + ' ventas · fecha de creación';
      get('[data-distribution-legend]').replaceChildren(...categories.map((category, i) => {
        const li = doc.createElement('li'), swatch = doc.createElement('i'); swatch.style.backgroundColor = palette[i % palette.length]; swatch.setAttribute('aria-hidden', 'true');
        li.append(swatch, node('span', category.nombre + ' · ' + category.cantidad + ' operaciones'), node('strong', percent(category.porcentaje).replace(/^\+/, ''))); return li;
      }));
      const showDonut = distribution.total > 0 && !!env.Chart;
      get('[data-distribution-container]').hidden = !showDonut; get('[data-distribution-empty]').hidden = showDonut;
      get('[data-distribution-empty]').textContent = distribution.total ? 'El gráfico no está disponible. Consultá los valores de la leyenda.' : 'No hay operaciones completadas para los filtros seleccionados.';
      if (showDonut) {
        chart('donut', get('[data-analyst-donut]'), 'doughnut', { labels: categories.map(c => c.nombre), datasets: [{ data: categories.map(c => c.cantidad), backgroundColor: categories.map((_, i) => palette[i % palette.length]), borderWidth: 0, hoverOffset: 5 }] },
          { cutout: '70%', plugins: { legend: { display: false }, tooltip: { callbacks: { label: context => categories[context.dataIndex].cantidad + ' operaciones · ' + percent(categories[context.dataIndex].porcentaje).replace(/^\+/, '') } } } });
      } else if (charts.donut) { charts.donut.destroy(); delete charts.donut; }
      get('[data-variation-list]').replaceChildren(...(data.variaciones.length ? data.variaciones.map(item => {
        const el = doc.createElement('div'); el.append(node('strong', item.par), node('span', percent(item.variacion?.porcentaje), item.variacion ? variationClass(item.variacion.porcentaje) : 'is-neutral'));
        if (item.variacion) el.append(node('small', date(item.variacion.desde) + ' → ' + date(item.variacion.hasta), 'is-neutral'));
        return el;
      }) : [node('p', 'No hay divisas activas disponibles.', 'ge-analyst-note')]));
      rows(get('[data-market-rows]'), data.mercado.map(row => [row.par, amount(row.compra), amount(row.venta), amount(row.spread), percent(row.variacion?.porcentaje), date(row.fecha)]), 'No hay tasas comerciales vigentes para esta selección.', 6);
      if (initial && !media.matches) get('.ge-analyst-kpis').classList.add('is-entering');
    }
    async function load(query, historyMode = 'push') {
      const ticket = ++sequence; controller?.abort(); controller = new env.AbortController();
      results.setAttribute('aria-busy', 'true'); error.hidden = true; status.textContent = 'Actualizando…';
      try {
        const response = await env.fetch(root.dataset.endpoint + '?' + query, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: controller.signal });
        const data = await response.json();
        if (destroyed || ticket !== sequence) return;
        if (!response.ok) {
          const failure = new Error(response.status === 401 ? 'Tu sesión expiró. Iniciá sesión nuevamente.' : response.status === 403 ? 'No tenés permiso para consultar este dashboard.' : data.error || 'No se pudieron cargar los datos. Intentá nuevamente.'); failure.controlled = true; throw failure;
        }
        render(data); sync(data.filtros);
        const url = new URL(env.location.href); url.search = queryFor(data.filtros).toString();
        if (historyMode === 'push' && url.href !== env.location.href) env.history.pushState(null, '', url);
        status.textContent = 'Datos actualizados.';
      } catch (failure) {
        if (destroyed || ticket !== sequence || failure.name === 'AbortError') return;
        error.textContent = (failure.controlled ? failure.message : 'No se pudieron cargar los datos. Revisá la conexión e intentá nuevamente.') + (active ? ' Se conserva la última consulta exitosa.' : ' Aplicá los filtros para reintentar.'); error.hidden = false;
        if (active) {
          sync(active.filtros);
          if (historyMode === 'none') { const url = new URL(env.location.href); url.search = queryFor(active.filtros).toString(); env.history.replaceState(null, '', url); }
        }
      } finally {
        if (!destroyed && ticket === sequence) { results.setAttribute('aria-busy', 'false'); if (status.textContent === 'Actualizando…') status.textContent = ''; }
      }
    }
    function change() {
      customFields();
    }
    const submit = event => { event.preventDefault(); if (form.reportValidity()) load(params()); };
    const reset = () => { sync({ periodo: 'mes', divisa: '' }); load(params()); };
    const popstate = () => load(new URL(env.location.href).searchParams, 'none');
    const motion = () => { if (active) render(active); };
    form.addEventListener('submit', submit);
    Object.values(fields).forEach(field => field.addEventListener('change', change));
    get('[data-analyst-reset]').addEventListener('click', reset);
    env.addEventListener('popstate', popstate); media.addEventListener('change', motion);
    const initial = JSON.parse(get('#analista-inicial').textContent);
    if (initial) { sync(initial.filtros); render(initial, true); } else customFields();
    const api = { load, charts, destroy() {
      destroyed = true; ++sequence; controller?.abort(); Object.values(charts).forEach(chart => chart.destroy());
      form.removeEventListener('submit', submit); Object.values(fields).forEach(field => field.removeEventListener('change', change));
      get('[data-analyst-reset]').removeEventListener('click', reset); env.removeEventListener('popstate', popstate); media.removeEventListener('change', motion);
      delete root._analyst;
    } };
    root._analyst = api; return api;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { amount, percent, queryFor, init };
  if (global.document) {
    const boot = () => global.document.querySelectorAll('[data-analyst-dashboard]').forEach(root => init(root));
    if (global.up) global.up.compiler('[data-analyst-dashboard]', root => { const api = init(root); return () => api.destroy(); });
    else if (global.document.readyState === 'loading') global.document.addEventListener('DOMContentLoaded', boot, { once: true });
    else boot();
  }
})(typeof window !== 'undefined' ? window : globalThis);
