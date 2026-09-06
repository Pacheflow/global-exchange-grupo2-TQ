/*
 * frontend-figma.js — Interacción JS mínima para la capa de presentación
 * 1:1 con la referencia `front_actualizado`. Solo comportamientos de UI;
 * la lógica de negocio (conversión) se delega en GEServices/GEData.
 */
window.GEFigma = (function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';

  function $(selector, root) { return (root || document).querySelectorAll(selector); }

  function svg(tag, attrs) {
    var el = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtNum(n, digits) {
    var v = Number(n);
    if (Number.isFinite(digits)) return v.toLocaleString('es-PY', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return v.toLocaleString('es-PY');
  }

  /* ── Sparkline (reusa GEApp.sparkline, con animación de dibujo) ── */
  function sparkline(el, data, trend, width, height) {
    if (!window.GEApp || !window.GEApp.sparkline) return;
    var svgString = window.GEApp.sparkline(data, trend, width || 60, height || 28);
    if (!svgString) return;
    var wrap = document.createElement('div');
    wrap.innerHTML = svgString;
    var node = wrap.firstChild;
    node.classList.add('ge-figma-spark');
    var grad = node.querySelector('linearGradient[id]');
    if (grad) {
      var uid = 'ge-spark-' + Math.random().toString(36).slice(2, 8);
      var oldId = grad.getAttribute('id');
      grad.setAttribute('id', uid);
      Array.prototype.forEach.call(node.querySelectorAll('[fill="url(#' + oldId + ')"]'), function (ref) {
        ref.setAttribute('fill', 'url(#' + uid + ')');
      });
    }
    el.appendChild(node);
    var line = node.querySelector('path[stroke]');
    if (line) {
      try {
        var len = line.getTotalLength();
        line.style.strokeDasharray = String(len);
        line.style.strokeDashoffset = String(len);
        line.getBoundingClientRect();
        line.style.strokeDashoffset = '0';
        line.style.transition = 'stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1)';
      } catch (err) { /* coast */ }
    }
  }

  function initSparklines(root) {
    var nodes = $('[data-spark]', root);
    Array.prototype.forEach.call(nodes, function (el) {
      var raw = el.getAttribute('data-spark');
      if (!raw) return;
      var data = raw.split(',').map(parseFloat).filter(function (n) { return Number.isFinite(n); });
      sparkline(el, data, el.getAttribute('data-trend') || 'neutral',
        parseInt(el.getAttribute('data-w') || '60', 10),
        parseInt(el.getAttribute('data-h') || '28', 10));
    });
  }

  /* ── Gráfico de líneas (svg) ── */
  function lineChart(el, labels, series) {
    var width = el.clientWidth || 560;
    var height = parseInt(el.getAttribute('data-height') || '200', 10);
    var padL = 44, padR = 12, padT = 10, padB = 24;
    var plotW = width - padL - padR;
    var plotH = height - padT - padB;

    var min = Infinity, max = -Infinity;
    series.forEach(function (s) {
      s.data.forEach(function (v) {
        if (v < min) min = v;
        if (v > max) max = v;
      });
    });
    if (!isFinite(min) || !isFinite(max)) return;
    var span = (max - min) || 1;
    min = min - span * 0.05;
    max = max + span * 0.05;
    span = max - min;

    var svgEl = svg('svg', { width: '100%', height: String(height), viewBox: '0 0 ' + width + ' ' + height, preserveAspectRatio: 'none', role: 'img', 'aria-hidden': 'true' });

    var ticks = 4;
    var i;
    var g;
    for (i = 0; i <= ticks; i++) {
      var y = padT + (plotH / ticks) * i;
      g = svg('line', { x1: padL, x2: width - padR, y1: y, y2: y, stroke: 'var(--border)', 'stroke-dasharray': '3 3', 'stroke-width': '1' });
      svgEl.appendChild(g);
      var yv = max - (span / ticks) * i;
      var label = yv >= 1000000 ? (yv / 1000000).toFixed(1) + 'M' : yv >= 10000 ? yv.toLocaleString('es-PY') : yv.toFixed(yv < 10 ? 2 : 0);
      var tl = svg('text', { x: String(padL - 8), y: String(y + 3), 'text-anchor': 'end', fill: 'var(--text-3)', 'font-family': 'DM Sans, sans-serif', 'font-size': '10' });
      tl.textContent = label;
      svgEl.appendChild(tl);
    }

    labels.forEach(function (lb, i) {
      var x = padL + (plotW / Math.max(1, labels.length - 1)) * i;
      var tl = svg('text', { x: String(x), y: String(height - 6), 'text-anchor': 'middle', fill: 'var(--text-3)', 'font-family': 'DM Sans, sans-serif', 'font-size': '10' });
      tl.textContent = lb;
      svgEl.appendChild(tl);
    });

    series.forEach(function (s, si) {
      var pts = s.data.map(function (v, i) {
        return {
          x: padL + (plotW / Math.max(1, s.data.length - 1)) * i,
          y: padT + plotH - ((v - min) / span) * plotH
        };
      });
      var line = pts.map(function (p, i) { return (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1); }).join(' ');
      var area = 'M' + pts[0].x.toFixed(1) + ',' + (padT + plotH) + ' ' + line + ' L' + pts[pts.length - 1].x.toFixed(1) + ',' + (padT + plotH) + ' Z';

      var gradId = 'ge-fig-grad-' + si;
      var defs = svg('defs', {});
      var grad = svg('linearGradient', { id: gradId, x1: '0', y1: '0', x2: '0', y2: '1' });
      grad.appendChild(svg('stop', { offset: '0%', 'stop-color': s.color, 'stop-opacity': '0.25' }));
      grad.appendChild(svg('stop', { offset: '100%', 'stop-color': s.color, 'stop-opacity': '0' }));
      defs.appendChild(grad);
      svgEl.appendChild(defs);

      svgEl.appendChild(svg('path', { d: area, fill: 'url(#' + gradId + ')' }));
      svgEl.appendChild(svg('path', { d: line, fill: 'none', stroke: s.color, 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
    });

    el.innerHTML = '';
    el.appendChild(svgEl);
  }

  /* ── Gráfico de barras (svg) ── */
  function barChart(el, labels, values, color) {
    var width = el.clientWidth || 560;
    var height = parseInt(el.getAttribute('data-height') || '200', 10);
    var padL = 44, padR = 12, padT = 10, padB = 24;
    var plotW = width - padL - padR;
    var plotH = height - padT - padB;

    var max = Math.max.apply(null, values);
    var ticks = 4;
    var svgEl = svg('svg', { width: '100%', height: String(height), viewBox: '0 0 ' + width + ' ' + height, preserveAspectRatio: 'none', role: 'img', 'aria-hidden': 'true' });
    var i;

    for (i = 0; i <= ticks; i++) {
      var y = padT + (plotH / ticks) * i;
      svgEl.appendChild(svg('line', { x1: padL, x2: width - padR, y1: y, y2: y, stroke: 'var(--border)', 'stroke-dasharray': '3 3', 'stroke-width': '1' }));
      var yv = (max / ticks) * (ticks - i);
      var label = yv >= 1000000 ? (yv / 1000000).toFixed(1) + 'M' : yv.toLocaleString('es-PY');
      var tl = svg('text', { x: String(padL - 8), y: String(y + 3), 'text-anchor': 'end', fill: 'var(--text-3)', 'font-family': 'DM Sans, sans-serif', 'font-size': '10' });
      tl.textContent = label;
      svgEl.appendChild(tl);
    }

    var slot = plotW / values.length;
    var barW = Math.min(34, slot * 0.55);
    values.forEach(function (v, i) {
      var x = padL + slot * i + (slot - barW) / 2;
      var h = (v / max) * plotH;
      var y = padT + plotH - h;
      var rect = svg('rect', { x: String(x), y: String(y), width: String(barW), height: String(h), rx: '4', fill: color || 'var(--primary)' });
      svgEl.appendChild(rect);
      var ll = svg('text', { x: String(x + barW / 2), y: String(height - 6), 'text-anchor': 'middle', fill: 'var(--text-3)', 'font-family': 'DM Sans, sans-serif', 'font-size': '10' });
      ll.textContent = labels[i];
      svgEl.appendChild(ll);
    });

    el.innerHTML = '';
    el.appendChild(svgEl);
  }

  /* ── Donut (svg) ── */
  function donutChart(el, segments) {
    var size = 160, radius = 62, stroke = 26;
    var center = size / 2;
    var circ = 2 * Math.PI * radius;
    var svgEl = svg('svg', { width: String(size), height: String(size), viewBox: '0 0 ' + size + ' ' + size, role: 'img', 'aria-hidden': 'true' });
    var total = segments.reduce(function (a, s) { return a + s.value; }, 0) || 1;
    var offset = 0;

    segments.forEach(function (s) {
      var frac = s.value / total;
      var len = frac * circ;
      var g = svg('g', { transform: 'rotate(-90 ' + center + ' ' + center + ')' });
      g.appendChild(svg('circle', {
        cx: String(center), cy: String(center), r: String(radius),
        fill: 'none', stroke: s.color, 'stroke-width': String(stroke),
        'stroke-dasharray': len.toFixed(1) + ' ' + (circ - len).toFixed(1),
        'stroke-dashoffset': String(-offset)
      }));
      offset += len;
      svgEl.appendChild(g);
    });

    el.innerHTML = '';
    el.appendChild(svgEl);
  }

  function initCharts(root) {
    var i;
    var nodes = $('[data-chart]', root);
    Array.prototype.forEach.call(nodes, function (el) {
      var kind = el.getAttribute('data-chart');
      if (kind === 'line') {
        var labels = JSON.parse(el.getAttribute('data-labels') || '[]');
        var series = JSON.parse(el.getAttribute('data-series') || '[]');
        lineChart(el, labels, series);
      } else if (kind === 'bar') {
        var bvalues = JSON.parse(el.getAttribute('data-values') || '[]');
        barChart(el, JSON.parse(el.getAttribute('data-labels') || '[]'), bvalues, el.getAttribute('data-color'));
      } else if (kind === 'donut') {
        var segs = JSON.parse(el.getAttribute('data-segments') || '[]');
        donutChart(el, segs);
      }
    });
  }

  function redrawAll() {
    initSparklines(document);
    initCharts(document);
  }

  /* ── Tabs con subrayado ── */
  function initTabLine(container) {
    var buttons = container.querySelectorAll('button[data-panel]');
    var panelScope = container.parentElement || document;
    var panels = panelScope.querySelectorAll('[data-panel-id]');
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener('click', function () {
        Array.prototype.forEach.call(buttons, function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        var target = btn.getAttribute('data-panel');
        Array.prototype.forEach.call(panels, function (p) {
          p.hidden = p.getAttribute('data-panel-id') !== target;
        });
      });
    });
  }

  function initTabs(root) {
    Array.prototype.forEach.call($('.ge-tabs-line', root), initTabLine);
    Array.prototype.forEach.call($('.ge-switch', root), function (sw) {
      Array.prototype.forEach.call(sw.querySelectorAll('button[data-caja-view]'), function (btn) {
        btn.addEventListener('click', function () {
          Array.prototype.forEach.call(sw.querySelectorAll('button'), function (b) { b.classList.remove('is-active'); });
          btn.classList.add('is-active');
          var target = btn.getAttribute('data-caja-view');
          Array.prototype.forEach.call($('[data-caja-panel]', root), function (p) {
            p.hidden = p.getAttribute('data-caja-panel') !== target;
          });
        });
      });
    });

    /* Selectores segmentados de la referencia que solo cambian estado visual. */
    Array.prototype.forEach.call($('.ge-switch', root), function (sw) {
      Array.prototype.forEach.call(sw.querySelectorAll('button:not([data-caja-view])'), function (btn) {
        btn.addEventListener('click', function () {
          Array.prototype.forEach.call(sw.querySelectorAll('button'), function (b) { b.classList.remove('is-active'); });
          btn.classList.add('is-active');
        });
      });
    });
  }

  /* ── Controles de tablas y formularios demo de Sprint 2 ── */
  function initTableSearch(root) {
    Array.prototype.forEach.call($('.ge-search-box input', root), function (input) {
      var scope = input.closest('.ge-figma-main-pad') || root;
      var rows = scope.querySelectorAll('tbody tr');
      input.addEventListener('input', function () {
        var query = input.value.trim().toLocaleLowerCase('es');
        Array.prototype.forEach.call(rows, function (row) {
          row.hidden = query !== '' && row.textContent.toLocaleLowerCase('es').indexOf(query) === -1;
        });
      });
    });
  }

  function createDialog(id, title, body, confirmLabel, onConfirm, danger) {
    var previous = document.getElementById(id);
    if (previous) previous.remove();
    var backdrop = document.createElement('div');
    backdrop.className = 'ge-modal-backdrop is-open';
    backdrop.id = id;
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.setAttribute('aria-labelledby', id + '-title');
    backdrop.innerHTML = '<div class="ge-modal"><h3 id="' + id + '-title">' + esc(title) + '</h3>' + body +
      '<div class="ge-modal-actions"><button type="button" class="ge-btn-outline" data-dialog-cancel>Cancelar</button>' +
      '<button type="button" class="ge-btn-primary' + (danger ? ' ge-btn-danger' : '') + '" data-dialog-confirm>' + esc(confirmLabel) + '</button></div></div>';
    document.body.appendChild(backdrop);
    function close() { backdrop.remove(); }
    backdrop.querySelector('[data-dialog-cancel]').addEventListener('click', close);
    backdrop.addEventListener('click', function (event) { if (event.target === backdrop) close(); });
    backdrop.querySelector('[data-dialog-confirm]').addEventListener('click', function () {
      if (!onConfirm || onConfirm(backdrop) !== false) close();
    });
    var first = backdrop.querySelector('input,select,button');
    if (first) first.focus();
  }

  function field(label, control) {
    return '<label class="ge-crud-field"><span class="ge-field-label">' + label + '</span>' + control + '</label>';
  }

  function showCrudForm(page, kind, row) {
    var isEdit = !!row;
    var cells = row ? row.querySelectorAll('td') : [];
    var title = '';
    var body = '';
    var submit = '';
    if (kind === 'currency') {
      title = isEdit ? 'Editar divisa' : 'Nueva divisa';
      submit = 'Guardar cambios';
      body = '<div class="ge-form-grid">' +
        field('CÓDIGO (ISO)', '<input class="ge-input" name="code" maxlength="3" required placeholder="USD" value="' + (isEdit ? esc(cells[1].textContent.trim()) : '') + '">') +
        field('BANDERA (EMOJI)', '<input class="ge-input" name="flag" required placeholder="🇺🇸" value="' + (isEdit ? esc(cells[0].textContent.trim()) : '') + '">') + '</div>' +
        field('NOMBRE DE LA MONEDA', '<input class="ge-input" name="name" required placeholder="Dólar estadounidense" value="' + (isEdit ? esc(cells[2].textContent.trim()) : '') + '">') +
        '<label class="ge-crud-check"><input type="checkbox" checked> Divisa activa</label>';
    } else if (kind === 'payment') {
      title = isEdit ? 'Editar medio de pago' : 'Nuevo medio de pago';
      submit = 'Guardar medio de pago';
      body = field('CLIENTE ASOCIADO', '<select class="ge-input" name="client" required><option>KNG S.A.</option><option>Importadora del Norte</option><option>Exportaciones Río S.R.L.</option></select>') +
        '<div class="ge-form-grid">' +
        field('TIPO DE MEDIO', '<select class="ge-input" name="type"><option>Cuenta bancaria</option><option>Billetera electrónica</option><option>Efectivo / Caja</option></select>') +
        field('ENTIDAD (EJ: BANCO ITAÚ)', '<input class="ge-input" name="entity" required placeholder="Banco Itaú" value="' + (isEdit ? esc(cells[1].textContent.trim()) : '') + '">') + '</div>' +
        field('NÚMERO DE CUENTA / TELÉFONO', '<input class="ge-input" name="account" required placeholder="Número de cuenta o teléfono" value="' + (isEdit ? esc(cells[3].textContent.trim()) : '') + '">');
    } else {
      title = isEdit ? 'Editar tasa' : 'Actualizar tasa';
      submit = 'Confirmar actualización';
      body = field('DIVISA', '<select class="ge-input" name="currency"><option>🇺🇸 USD - Dólar estadounidense</option><option>🇪🇺 EUR - Euro</option><option>🇧🇷 BRL - Real brasileño</option><option>🇦🇷 ARS - Peso argentino</option></select>') +
        '<div class="ge-form-grid">' +
        field('PRECIO COMPRA (PYG)', '<input class="ge-input ge-mono" type="number" min="0.0001" step="0.0001" name="buy" required value="' + (isEdit ? esc(cells[1].textContent.trim().replace('.', '')) : '') + '">') +
        field('PRECIO VENTA (PYG)', '<input class="ge-input ge-mono" type="number" min="0.0001" step="0.0001" name="sell" required value="' + (isEdit ? esc(cells[2].textContent.trim().replace('.', '')) : '') + '">') + '</div>';
    }

    var list = page.innerHTML;
    page.innerHTML = '<div class="ge-crud-form-view"><div class="ge-crud-form-head"><button type="button" class="ge-btn-ghost" data-crud-back>← Volver</button><h2 class="ge-figma-h2">' + esc(title) + '</h2></div>' +
      '<div class="ge-card ge-crud-form-card"><form data-crud-form>' + body + '<div class="ge-modal-actions"><button type="button" class="ge-btn-outline" data-crud-back>Cancelar</button><button class="ge-btn-primary" type="submit">' + esc(submit) + '</button></div></form></div></div>';
    function restore(message) {
      page.innerHTML = list;
      delete page.dataset.crudReady;
      init(page);
      if (message && window.GEApp) window.GEApp.toast(message);
    }
    Array.prototype.forEach.call(page.querySelectorAll('[data-crud-back]'), function (button) { button.addEventListener('click', function () { restore(); }); });
    page.querySelector('[data-crud-form]').addEventListener('submit', function (event) {
      event.preventDefault();
      var form = event.currentTarget;
      if (!form.reportValidity()) return;
      if (kind === 'rate') {
        var buy = parseFloat(form.elements.buy.value);
        var sell = parseFloat(form.elements.sell.value);
        if (!(sell > buy)) {
          form.elements.sell.setCustomValidity('El precio de venta debe ser mayor al precio de compra.');
          form.elements.sell.reportValidity();
          return;
        }
      }
      restore(kind === 'currency' ? 'Divisa guardada correctamente.' : kind === 'payment' ? 'Medio de pago guardado correctamente.' : 'Tasa actualizada correctamente.');
    });
  }

  function initSprintCrud(root) {
    var page = root.matches && root.matches('.ge-figma-main-pad')
      ? root
      : root.querySelector ? root.querySelector('.ge-figma-main-pad') : null;
    if (!page || page.dataset.crudReady === 'true') return;
    var heading = page.querySelector('.ge-figma-section-head h2');
    if (!heading) return;
    var title = heading.textContent.trim();
    var kind = title === 'Gestión de divisas' ? 'currency' : title === 'Medios de pago del cliente' ? 'payment' : title === 'Cotizaciones y Tasas' ? 'rate' : '';
    if (!kind) return;
    page.dataset.crudReady = 'true';
    var primary = page.querySelector('.ge-figma-section-head .ge-btn-primary');
    if (primary) primary.addEventListener('click', function () { showCrudForm(page, kind, null); });
    Array.prototype.forEach.call(page.querySelectorAll('tbody tr'), function (row) {
      Array.prototype.forEach.call(row.querySelectorAll('button'), function (button) {
        var action = button.textContent.trim();
        if (action === 'Editar') button.addEventListener('click', function () { showCrudForm(page, kind, row); });
        if (action === 'Historial') button.addEventListener('click', function () {
          createDialog('ge-rate-history', 'Histórico de tasas', '<p>Registro visual de cambios para <strong class="ge-mono">' + esc(row.cells[0].textContent.trim()) + '</strong>.</p><div class="ge-empty"><strong>Histórico en preparación</strong><p>Se conectará al backend cuando el servicio esté disponible.</p></div>', 'Cerrar');
        });
        if (action === 'Desactivar' || action === 'Eliminar') button.addEventListener('click', function () {
          var noun = kind === 'currency' ? 'Divisa' : 'Medio de Pago';
          createDialog('ge-delete-confirm', action + ' ' + noun, '<p>¿Confirmás esta acción sobre <strong>' + esc(row.cells[kind === 'currency' ? 2 : 0].textContent.trim()) + '</strong>?</p>', action, function () {
            row.remove();
            if (window.GEApp) window.GEApp.toast(noun + ' actualizado correctamente.');
          }, true);
        });
      });
    });
  }

  function initDashboardActions(root) {
    Array.prototype.forEach.call(root.querySelectorAll('.ge-figma-quick'), function (button) {
      button.addEventListener('click', function () {
        var label = button.textContent.trim();
        var target = label.indexOf('historial') >= 0 ? 'transacciones' : 'operaciones';
        var tab = root.querySelector('.ge-tabs-line [data-panel="' + target + '"]');
        if (tab) tab.click();
      });
    });
    Array.prototype.forEach.call(root.querySelectorAll('.ge-page-num'), function (button) {
      button.addEventListener('click', function () {
        Array.prototype.forEach.call(root.querySelectorAll('.ge-page-num'), function (item) { item.classList.remove('is-active'); });
        button.classList.add('is-active');
      });
    });
    Array.prototype.forEach.call(root.querySelectorAll('button'), function (button) {
      if (button.textContent.trim() !== 'Continuar →') return;
      button.addEventListener('click', function () {
        var converter = button.closest('[data-converter]');
        var amount = converter && converter.querySelector('[data-conv-monto]');
        if (!amount || !(parseFloat(amount.value) > 0)) {
          if (amount) amount.reportValidity();
          return;
        }
        createDialog('ge-operation-confirm', 'Confirmar operación', '<p>Estás a punto de registrar esta operación para <strong>KNG S.A.</strong>. Revisá los valores simulados antes de continuar.</p>', 'Confirmar operación', function () {
          if (window.GEApp) window.GEApp.toast('Operación confirmada en modo demostración.');
        });
      });
    });
  }

  /* ── Contadores de billetes ── */
  function initBillCurrencySwitch(root) {
    var selects = $('[data-bill-currency-select]', root);
    Array.prototype.forEach.call(selects, function (sel) {
      function apply() {
        Array.prototype.forEach.call(document.querySelectorAll('[data-bill-currency]'), function (table) {
          table.hidden = table.getAttribute('data-bill-currency') !== sel.value;
        });
      }
      sel.addEventListener('change', apply);
      apply();
    });
  }

  function initCounters(root) {
    var rows = $('[data-bill-currency]', root);
    Array.prototype.forEach.call(rows, function (table) {
      var totalEl = table.querySelector('[data-bill-total]');
      function recompute() {
        var total = 0;
        Array.prototype.forEach.call(table.querySelectorAll('[data-denom]'), function (row) {
          var denom = parseInt(row.getAttribute('data-denom'), 10);
          var count = parseInt(row.getAttribute('data-count'), 10) || 0;
          var sub = row.querySelector('[data-subtotal]');
          if (sub) sub.textContent = fmtNum(denom * count);
          total += denom * count;
        });
        if (totalEl) totalEl.textContent = fmtNum(total);
      }
      function bump(row, delta) {
        var count = parseInt(row.getAttribute('data-count'), 10) || 0;
        row.setAttribute('data-count', String(Math.max(0, count + delta)));
        var badge = row.querySelector('[data-count-label]');
        if (badge) badge.textContent = String(Math.max(0, count + delta));
        recompute();
      }
      Array.prototype.forEach.call(table.querySelectorAll('[data-dec]'), function (btn) {
        btn.addEventListener('click', function () { bump(btn.closest('[data-denom]'), -1); });
      });
      Array.prototype.forEach.call(table.querySelectorAll('[data-inc]'), function (btn) {
        btn.addEventListener('click', function () { bump(btn.closest('[data-denom]'), 1); });
      });
      recompute();
    });
  }

  /* ── Arqueo de caja ── */
  function initArqueo(root) {
    var rows = $('[data-arqueo-row]', root);
    Array.prototype.forEach.call(rows, function (row) {
      var input = row.querySelector('[data-real]');
      var expected = parseFloat(row.getAttribute('data-expected')) || 0;
      var diffEl = row.querySelector('[data-diff]');
      var stateEl = row.querySelector('[data-diff-state]');
      function update() {
        var real = parseFloat(input ? input.value : '0') || 0;
        var diff = real - expected;
        var cls = diff === 0 ? 'ge-trend-flat' : diff > 0 ? 'ge-trend-up' : 'ge-trend-down';
        var label = diff === 0 ? 'Cuadre exacto' : diff > 0 ? 'Sobrante' : 'Faltante';
        if (diffEl) {
          diffEl.textContent = (diff >= 0 ? '+' : '') + fmtNum(diff);
          diffEl.className = 'ge-note-label ge-note-label--12 ' + cls;
        }
        if (stateEl) {
          stateEl.textContent = label;
          stateEl.className = 'ge-diff-state ' + cls;
        }
      }
      if (input) {
        input.addEventListener('input', update);
        input.addEventListener('change', update);
      }
      update();
    });
  }

  /* ── Conversión simulada (solamente UI; lógica vía GEServices) ── */
  function initConverter(root) {
    var box = $('[data-converter]', root);
    if (!box.length) return;
    Array.prototype.forEach.call(box, function (el) {
      var amount = el.querySelector('[data-conv-monto]');
      var from = el.querySelector('[data-conv-origen]');
      var to = el.querySelector('[data-conv-destino]');
      var rateEl = el.querySelector('[data-conv-tasa]');
      var resultEl = el.querySelector('[data-conv-resultado]');
      var deliveredEl = el.querySelector('[data-conv-entregado]');
      var swapBtn = el.querySelector('[data-conv-swap]');

      function compute() {
        if (!window.GEServices || !from || !to) return;
        var a = parseFloat(amount ? amount.value : '0');
        if (!(a > 0)) {
          if (resultEl) resultEl.textContent = '0';
          if (deliveredEl) deliveredEl.textContent = '0 ' + from.value;
          if (rateEl) rateEl.textContent = '1 ' + from.value + ' = — ' + to.value;
          return;
        }
        window.GEServices.consultaConversion({
          monedaOrigen: from.value,
          monedaDestino: to.value,
          monto: a
        }).then(function (res) {
          if (rateEl) rateEl.textContent = '1 ' + from.value + ' = ' + fmtNum(res.tasa, res.tasa < 100 ? 4 : 2) + ' ' + to.value;
          if (deliveredEl) deliveredEl.textContent = fmtNum(a, a < 100 ? 4 : 0) + ' ' + from.value;
          if (resultEl) resultEl.textContent = fmtNum(res.resultado, res.resultado < 100 ? 4 : 0) + (deliveredEl ? ' ' + to.value : '');
        }).catch(function () {
          if (resultEl) resultEl.textContent = '—';
        });
      }

      if (amount) amount.addEventListener('input', compute);
      if (from) from.addEventListener('change', compute);
      if (to) to.addEventListener('change', compute);
      if (swapBtn) {
        swapBtn.addEventListener('click', function () {
          if (!from || !to) return;
          var temp = from.value;
          from.value = to.value;
          to.value = temp;
          swapBtn.classList.add('is-swapping');
          compute();
          window.setTimeout(function () { swapBtn.classList.remove('is-swapping'); }, 400);
        });
      }
      compute();
    });
  }

  function init(root) {
    root = root || document;
    initTabs(root);
    initBillCurrencySwitch(root);
    initCounters(root);
    initArqueo(root);
    initConverter(root);
    initTableSearch(root);
    initSprintCrud(root);
    initDashboardActions(root);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { init(); redrawAll(); });
  } else {
    init(); redrawAll();
  }

  window.addEventListener('resize', function () { initCharts(document); });

  return {
    init: init,
    redrawAll: redrawAll,
    lineChart: lineChart,
    barChart: barChart,
    donutChart: donutChart,
    sparkline: sparkline,
    format: fmtNum
  };
})();
