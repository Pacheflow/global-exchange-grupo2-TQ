window.GEApp = (function () {
  'use strict';

  function toast(message, type) {
    var allowedTypes = ['success', 'warning', 'error', 'info'];
    type = allowedTypes.indexOf(type) >= 0 ? type : 'success';
    var existing = document.querySelector('.ge-toast');
    if (existing) existing.remove();
    var el = document.createElement('div');
    el.className = 'ge-toast ge-toast--' + type;
    el.setAttribute('role', type === 'error' || type === 'warning' ? 'alert' : 'status');
    var icon = document.createElement('span');
    icon.className = 'ge-toast-icon';
    var icons = {
      success: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></svg>',
      warning: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5"/><path d="M12 18h.01"/></svg>',
      error: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/></svg>',
      info: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/></svg>'
    };
    icon.innerHTML = icons[type];
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

  var loginRedirectScheduled = false;

  function authenticationError(response) {
    if (!response || response.status !== 401) return null;

    if (!loginRedirectScheduled) {
      loginRedirectScheduled = true;
      window.setTimeout(function () {
        window.location.href = '/login/';
      }, 1000);
    }

    return new Error('Tu sesión expiró. Redirigiendo al inicio de sesión…');
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
    formatValue: formatValue,
    authenticationError: authenticationError
  };
})();

/*
 * Adaptador preservado para prototipos futuros.
 * Las pantallas activas de Sprint 2 usan frontend-api.js o landing.js.
 */
window.GEServices = (function () {
  'use strict';

  function consultaConversion() {
    return Promise.reject(new Error('funcionalidad_pendiente'));
  }

  return {
    consultaConversion: consultaConversion
  };
})();
