window.GEApp = (function () {
  'use strict';

  function toast(message) {
    var existing = document.querySelector('.ge-toast');
    if (existing) existing.remove();
    var el = document.createElement('div');
    el.className = 'ge-toast';
    el.setAttribute('role', 'status');
    var icon = document.createElement('span');
    icon.className = 'ge-toast-icon';
    icon.textContent = '\u2713';
    el.appendChild(icon);
    var text = document.createElement('span');
    text.textContent = message;
    el.appendChild(text);
    var close = document.createElement('button');
    close.className = 'ge-toast-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Cerrar');
    close.textContent = '\u00D7';
    close.addEventListener('click', function () { el.remove(); });
    el.appendChild(close);
    document.body.appendChild(el);
    window.setTimeout(function () { el.remove(); }, 4000);
  }

  function openModal(id) {
    var modal = document.getElementById(id);
    if (modal) modal.classList.add('is-open');
  }

  function closeModal(id) {
    var modal = document.getElementById(id);
    if (modal) modal.classList.remove('is-open');
  }

  function sparklineSvg(data, trend, width, height) {
    if (!data || data.length < 2) return '';
    width = width || 300;
    height = height || 60;
    var color = trend === 'up' ? '#22C55E' : trend === 'down' ? '#F87171' : '#5A7AAC';
    var min = Math.min.apply(null, data);
    var max = Math.max.apply(null, data);
    var range = max - min || 1;
    var points = data.map(function (v, i) {
      return {
        x: (i / (data.length - 1)) * width,
        y: height - ((v - min) / range) * (height - 4) - 2
      };
    });
    var line = points.map(function (p, i) { return (i === 0 ? 'M' : 'L') + p.x.toFixed(2) + ',' + p.y.toFixed(2); }).join(' ');
    var area = 'M' + points[0].x.toFixed(2) + ',' + height + ' ' + line + ' L' + points[points.length - 1].x.toFixed(2) + ',' + height + ' Z';
    var last = points[points.length - 1];
    return '<svg width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '" overflow="visible" aria-hidden="true">' +
      '<defs><linearGradient id="ge-spark" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.3"/><stop offset="100%" stop-color="' + color + '" stop-opacity="0"/>' +
      '</linearGradient></defs>' +
      '<path d="' + area + '" fill="url(#ge-spark)"/>' +
      '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<circle cx="' + last.x.toFixed(2) + '" cy="' + last.y.toFixed(2) + '" r="2.5" fill="' + color + '"/>' +
      '</svg>';
  }

  function formatValue(value) {
    return Number(value).toLocaleString('es-PY', { maximumFractionDigits: Number(value) < 100 ? 4 : 0 });
  }

  function initTabs(container) {
    var tabs = container.querySelectorAll('[data-ge-tab]');
    var panels = container.querySelectorAll('[data-ge-panel]');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        tabs.forEach(function (t) { t.classList.remove('is-active'); });
        tab.classList.add('is-active');
        var target = tab.getAttribute('data-ge-tab');
        panels.forEach(function (p) { p.hidden = p.getAttribute('data-ge-panel') !== target; });
      });
    });
  }

  function initModals(root) {
    root = root || document;
    var openers = root.querySelectorAll('[data-ge-modal-open]');
    openers.forEach(function (btn) {
      btn.addEventListener('click', function () { openModal(btn.getAttribute('data-ge-modal-open')); });
    });
    var closers = root.querySelectorAll('[data-ge-modal-close]');
    closers.forEach(function (btn) {
      btn.addEventListener('click', function () { closeModal(btn.getAttribute('data-ge-modal-close')); });
    });
  }

  function initBackdropClose(root) {
    root = root || document;
    var backdrops = root.querySelectorAll('.ge-modal-backdrop');
    backdrops.forEach(function (bd) {
      bd.addEventListener('click', function (event) {
        if (event.target === bd) bd.classList.remove('is-open');
      });
    });
  }

  function init() {
    document.querySelectorAll('.ge-tabs').forEach(initTabs);
    initModals();
    initBackdropClose();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    toast: toast,
    openModal: openModal,
    closeModal: closeModal,
    sparkline: sparklineSvg,
    formatValue: formatValue
  };
})();

/*
 * Adaptador de servicios (HU-19).
 * Contrato de integración con el backend: las páginas consumen estas
 * funciones y NO implementan lógica de negocio (conversión, tasas).
 * Hoy resuelve con datos simulados; en la integración real cada función
 * debe reemplazarse por una petición al endpoint correspondiente.
 */
window.GEServices = (function () {
  'use strict';

  function currencyByCode(code) {
    var currencies = (window.GEData && window.GEData.currencies) || [];
    for (var i = 0; i < currencies.length; i++) {
      if (currencies[i].code === code) return currencies[i];
    }
    return null;
  }

  function consultaConversion(params) {
    var de = params.monedaOrigen;
    var hacia = params.monedaDestino;

    if (de === hacia) return Promise.resolve({
      monto: params.monto,
      monedaOrigen: de,
      monedaDestino: hacia,
      tasa: 1,
      resultado: params.monto,
      actualizadoEn: window.GEData.updatedAt
    });

    if (!window.GEData || typeof window.GEData.rate !== 'function') {
      return Promise.reject(new Error('servicio_no_disponible'));
    }

    return new Promise(function (resolve, reject) {
      window.setTimeout(function () {
        var from = currencyByCode(de);
        var to = currencyByCode(hacia);
        var tasa = window.GEData.rate(de, hacia);
        if (!from || !to || !(tasa > 0)) {
          reject(new Error('tasa_inexistente'));
          return;
        }
        resolve({
          monto: params.monto,
          monedaOrigen: de,
          monedaDestino: hacia,
          tasa: tasa,
          resultado: params.monto * tasa,
          actualizadoEn: window.GEData.updatedAt
        });
      }, 250);
    });
  }

  return {
    consultaConversion: consultaConversion
  };
})();