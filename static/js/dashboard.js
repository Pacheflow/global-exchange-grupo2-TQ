/* Métricas coordinadas; Chart.js se sirve localmente. Dinero exacto en strings. */
(function (global) {
  'use strict';
  const colors = ['#3d5afe', '#22c55e', '#fbbf24', '#f87171', '#38bdf8', '#a78bfa'];
  const emptyMessage = 'No hay datos disponibles para los filtros seleccionados.';

  function integer(value) {
    const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(value));
    if (!match) return '0';
    let result = BigInt(match[2]);
    if ((match[3] || '0')[0] >= '5') result += 1n;
    return (match[1] && result ? '-' : '') + result.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }
  function pyg(value) { return integer(value) + ' PYG'; }
  function decimal(value) {
    const parts = String(value).split('.');
    const fraction = (parts[1] || '').replace(/0+$/, '');
    return integer(parts[0]) + (fraction ? ',' + fraction : '');
  }
  function queryFor(filters) {
    const query = new URLSearchParams({ periodo: filters.periodo, divisa: filters.divisa });
    if (filters.periodo === 'personalizado') {
      query.set('desde', filters.desde); query.set('hasta', filters.hasta);
    }
    return query;
  }

  function init(root, env = global) {
    if (root.dashboardController) return root.dashboardController;
    const doc = root.ownerDocument;
    const get = selector => root.querySelector(selector);
    const form = get('[data-dashboard-form]');
    const fields = Object.fromEntries(['periodo', 'divisa', 'desde', 'hasta'].map(k => [k, get('[data-filter="' + k + '"]')]));
    const status = get('[data-dashboard-status]'), error = get('[data-dashboard-error]');
    const results = get('[data-dashboard-results]');
    const media = env.matchMedia('(prefers-reduced-motion: reduce)');
    const charts = {};
    const counters = new Map();
    let active = null, controller = null, sequence = 0, destroyed = false;

    function text(tag, value, className) {
      const node = doc.createElement(tag); node.textContent = value;
      if (className) node.className = className;
      return node;
    }
    function rows(body, entries) { body.replaceChildren(...entries); }
    function busy(value) {
      results.setAttribute('aria-busy', String(value));
      status.textContent = value ? 'Actualizando…' : '';
    }
    function syncFields(filters) {
      Object.keys(fields).forEach(k => { fields[k].value = filters[k] || ''; });
      customFields();
    }
    function customFields() {
      const custom = fields.periodo.value === 'personalizado';
      root.querySelectorAll('[data-custom-date]').forEach(node => { node.hidden = !custom; });
      ['desde', 'hasta'].forEach(k => { fields[k].disabled = !custom; fields[k].required = custom; });
    }
    function counter(node, value, money, initial) {
      if (counters.has(node)) env.cancelAnimationFrame(counters.get(node));
      const finalText = money ? pyg(value) : integer(value);
      const target = Number(value);
      const start = initial ? 0 : (node.visualValue || 0);
      const finish = () => { node.textContent = finalText; node.visualValue = target; counters.delete(node); };
      if (media.matches || !Number.isFinite(target)) { finish(); return; }
      const began = env.performance.now();
      function frame(now) {
        const progress = Math.min(1, Math.max(0, (now - began) / 800));
        const current = start + (target - start) * (1 - Math.pow(1 - progress, 3));
        node.visualValue = current;
        node.textContent = (money ? pyg : integer)(BigInt(Math.max(0, Math.round(current))).toString());
        if (progress < 1 && !destroyed) counters.set(node, env.requestAnimationFrame(frame));
        else finish();
      }
      counters.set(node, env.requestAnimationFrame(frame));
    }
    function chart(name, canvas, data, type, tooltip) {
      if (!env.Chart) return false;
      if (!charts[name]) {
        charts[name] = new env.Chart(canvas, {
          type, data,
          options: {
            responsive: true, maintainAspectRatio: false,
            animation: media.matches ? false : { duration: 800, easing: 'easeOutQuart', animateRotate: true, animateScale: false },
            interaction: { intersect: false, mode: 'index' },
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: tooltip }, backgroundColor: '#171b27', titleColor: '#ffffff', bodyColor: '#e3e7ef', padding: 12 } },
            ...(type === 'bar' ? { scales: {
              x: { ticks: { color: '#b9c1d0', maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } },
              y: { beginAtZero: true, ticks: { color: '#b9c1d0', maxTicksLimit: 5, callback: value => pyg(value.toFixed(0)) }, title: { display: true, text: 'PYG', color: '#b9c1d0' }, grid: { color: '#303746' } }
            } } : { cutout: '70%' })
          }
        });
      } else {
        charts[name].data.labels = data.labels;
        Object.assign(charts[name].data.datasets[0], data.datasets[0]);
        charts[name].options.plugins.tooltip.callbacks.label = tooltip;
        charts[name].options.animation = media.matches ? false : { duration: 800, easing: 'easeOutQuart' };
        charts[name].update(media.matches ? 'none' : undefined);
      }
      return true;
    }
    function render(data, initial = false) {
      active = data;
      const filters = data.filtros, summary = data.resumen;
      const currency = filters.divisa || 'Todas las divisas';
      get('[data-dashboard-active]').textContent = filters.etiqueta + ' · ' + currency + ' · ' + filters.desde + ' – ' + filters.hasta;
      get('[data-dashboard-currency]').textContent = filters.divisa || 'Todas';
      get('[data-evolution-title]').textContent = 'Evolución de ganancias · ' + currency;
      get('[data-dashboard-granularity]').textContent = filters.agrupacion === 'mes' ? 'Meses' : 'Días';
      const warning = get('[data-dashboard-warning]');
      warning.hidden = !summary.excluidas;
      warning.textContent = 'Subtotal disponible: ' + summary.excluidas + ' operaciones excluidas de los importes por falta de conversión confiable a PYG. Los conteos sí las incluyen.';
      ['ganancia_pyg', 'volumen_pyg', 'operaciones', 'compras', 'ventas'].forEach(key => counter(get('[data-kpi="' + key + '"]'), summary[key], key.endsWith('_pyg'), initial));
      rows(get('[data-evolution-table]'), data.evolucion.map(point => {
        const row = doc.createElement('tr'), label = text('th', point.etiqueta);
        label.setAttribute('scope', 'row');
        row.append(label, text('td', pyg(point.ganancia_pyg)), text('td', point.excluidas));
        return row;
      }));
      const evolutionContainer = get('[data-evolution-container]'), evolutionEmpty = get('[data-evolution-empty]');
      const hasGain = data.evolucion.some(point => Number(point.ganancia_pyg) > 0);
      evolutionContainer.hidden = !hasGain || !env.Chart;
      const barReady = chart('evolution', get('[data-evolution-chart]'), {
        labels: data.evolucion.map(p => p.etiqueta),
        datasets: [{ label: 'Ganancia (PYG)', data: data.evolucion.map(p => Number(p.ganancia_pyg)), backgroundColor: colors[0], borderRadius: 5, maxBarThickness: 44 }]
      }, 'bar', context => 'Ganancia: ' + pyg(active.evolucion[context.dataIndex].ganancia_pyg));
      evolutionEmpty.hidden = hasGain && barReady;
      evolutionEmpty.textContent = !env.Chart ? 'El gráfico no está disponible. Consultá la tabla Datos de evolución.' : !summary.operaciones ? emptyMessage : 'No hay ganancias convertibles disponibles para los filtros seleccionados.';
      if (!evolutionContainer.hidden) charts.evolution.resize();
      const distribution = data.distribucion, categories = distribution.categorias;
      const monetary = distribution.modo === 'divisa';
      get('[data-distribution-title]').textContent = distribution.titulo;
      get('[data-distribution-note]').textContent = monetary ? 'Comisiones en PYG por la divisa distinta de PYG del par.' : 'Cantidad de compras y ventas de la divisa seleccionada.';
      rows(get('[data-distribution-legend]'), categories.map((item, index) => {
        const entry = doc.createElement('li'), swatch = text('span', '', 'ge-chart-swatch');
        swatch.style.backgroundColor = colors[index % colors.length]; swatch.setAttribute('aria-hidden', 'true');
        const copy = doc.createElement('div');
        copy.append(text('strong', item.categoria), text('span', monetary ? pyg(item.ganancia_pyg) : integer(item.cantidad) + ' operaciones'));
        entry.append(swatch, copy, text('strong', decimal(item.porcentaje) + ' %'));
        return entry;
      }));
      const values = categories.map(item => Number(monetary ? item.ganancia_pyg : item.cantidad));
      const hasDistribution = values.some(v => v > 0);
      const distributionContainer = get('[data-distribution-container]'), distributionEmpty = get('[data-distribution-empty]');
      distributionContainer.hidden = !hasDistribution || !env.Chart;
      const donutReady = chart('distribution', get('[data-distribution-chart]'), {
        labels: categories.map(item => item.categoria),
        datasets: [{ data: values, backgroundColor: categories.map((_, index) => colors[index % colors.length]), borderWidth: 0, hoverOffset: media.matches ? 0 : 5 }]
      }, 'doughnut', context => {
        const item = active.distribucion.categorias[context.dataIndex];
        return decimal(item.porcentaje) + ' % · ' + (active.distribucion.modo === 'divisa' ? 'Ganancia: ' + pyg(item.ganancia_pyg) : integer(item.cantidad) + ' operaciones');
      });
      distributionEmpty.hidden = hasDistribution && donutReady;
      distributionEmpty.textContent = !env.Chart ? 'El gráfico no está disponible. Consultá los valores de la leyenda.' : emptyMessage;
      if (!distributionContainer.hidden) charts.distribution.resize();
      rows(get('[data-dashboard-activity]'), data.actividad_reciente.length ? data.actividad_reciente.map(op => {
        const row = doc.createElement('tr'), detail = doc.createElement('td');
        const link = text('a', 'Ver detalle', 'ge-btn-ghost'); link.href = op.detalle;
        link.setAttribute('aria-label', 'Ver detalle de operación ' + op.id); detail.append(link);
        row.append(text('td', '#' + op.id), text('td', op.fecha), text('td', op.cliente), text('td', op.tipo), text('td', decimal(op.origen) + ' ' + op.divisa_origen), text('td', decimal(op.destino) + ' ' + op.divisa_destino), text('td', op.estado), detail);
        return row;
      }) : [(() => { const row = doc.createElement('tr'), cell = text('td', 'No hay operaciones completadas para los filtros seleccionados.'); cell.colSpan = 8; row.append(cell); return row; })()]);
    }
    function paramsFromForm() {
      return queryFor(Object.fromEntries(Object.keys(fields).map(k => [k, fields[k].value])));
    }
    async function load(params, historyMode = 'push') {
      const ticket = ++sequence;
      if (controller) controller.abort();
      controller = new env.AbortController();
      busy(true); error.hidden = true;
      try {
        const response = await env.fetch(root.dataset.endpoint + '?' + params, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: controller.signal });
        const data = await response.json();
        if (destroyed || ticket !== sequence) return;
        if (!response.ok) {
          const failure = new Error(response.status === 401 ? 'Tu sesión expiró. Iniciá sesión nuevamente.' : response.status === 403 ? 'No tenés permiso para consultar este dashboard.' : data.error || 'No se pudieron cargar los datos. Intentá nuevamente.');
          failure.dashboardMessage = true; throw failure;
        }
        render(data); syncFields(data.filtros);
        const url = new URL(env.location.href); url.search = queryFor(data.filtros).toString();
        if (historyMode === 'push' && url.href !== env.location.href) env.history.pushState(null, '', url);
        else if (historyMode === 'replace') env.history.replaceState(null, '', url);
        status.textContent = 'Datos actualizados.';
      } catch (failure) {
        if (destroyed || ticket !== sequence || failure.name === 'AbortError') return;
        error.textContent = (failure.dashboardMessage ? failure.message : 'No se pudieron cargar los datos. Revisá la conexión e intentá nuevamente.') + (active ? ' Se conservan los datos y filtros de la última consulta exitosa.' : ' Aplicá los filtros para intentar nuevamente.');
        error.hidden = false;
        if (active) {
          syncFields(active.filtros);
          if (historyMode === 'none') {
            const url = new URL(env.location.href); url.search = queryFor(active.filtros).toString();
            env.history.replaceState(null, '', url);
          }
        }
      } finally {
        if (!destroyed && ticket === sequence) {
          results.setAttribute('aria-busy', 'false');
          if (status.textContent === 'Actualizando…') status.textContent = '';
        }
      }
    }
    const submit = event => { event.preventDefault(); if (form.reportValidity()) load(paramsFromForm()); };
    const change = () => { customFields(); };
    const reset = () => { syncFields({ periodo: 'mes', divisa: '' }); load(paramsFromForm()); };
    const popstate = () => load(new URL(env.location.href).searchParams, 'none');
    const motion = () => { if (active) render(active); };
    form.addEventListener('submit', submit);
    Object.values(fields).forEach(field => field.addEventListener('change', change));
    get('[data-dashboard-reset]').addEventListener('click', reset);
    env.addEventListener('popstate', popstate);
    media.addEventListener('change', motion);
    const initial = JSON.parse(get('#dashboard-inicial').textContent);
    customFields();
    if (initial) { syncFields(initial.filtros); render(initial, true); }
    const api = {
      load, charts,
      destroy() {
        destroyed = true; ++sequence; if (controller) controller.abort();
        counters.forEach(frame => env.cancelAnimationFrame(frame));
        Object.values(charts).forEach(instance => instance.destroy());
        env.removeEventListener('popstate', popstate); media.removeEventListener('change', motion);
        form.removeEventListener('submit', submit);
        Object.values(fields).forEach(field => field.removeEventListener('change', change));
        get('[data-dashboard-reset]').removeEventListener('click', reset);
        delete root.dashboardController;
      }
    };
    root.dashboardController = api;
    return api;
  }
  const exported = { init, integer, pyg, decimal, queryFor };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  if (global.document) {
    const boot = () => global.document.querySelectorAll('[data-admin-dashboard]').forEach(root => init(root));
    if (global.document.readyState === 'loading') global.document.addEventListener('DOMContentLoaded', boot);
    else boot();
  }
})(typeof window !== 'undefined' ? window : globalThis);
