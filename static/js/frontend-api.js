(function () {
  'use strict';

  var page = document.querySelector('[data-ge-api]');
  if (!page) return;

  var body = page.querySelector('[data-api-body]');
  var csrfInput = page.querySelector('input[name="csrfmiddlewaretoken"]');
  var csrfToken = csrfInput ? csrfInput.value : '';
  var state = { items: [], clients: [], currencies: [], history: [], rateQuery: '' };

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function endpoint(template, id) {
    return template.replace('/0/', '/' + id + '/');
  }

  function notify(message, type) {
    if (window.GEApp && window.GEApp.toast) window.GEApp.toast(message, type);
  }

  function errorMessage(data, fallback) {
    if (data && data.error) return data.error;
    if (data && data.detalles) {
      return Object.keys(data.detalles).map(function (key) {
        var value = data.detalles[key];
        return Array.isArray(value) ? value.join(' ') : String(value);
      }).join(' ');
    }
    if (data && data.errores) {
      return Object.keys(data.errores).map(function (key) {
        var value = data.errores[key];
        return Array.isArray(value) ? value.join(' ') : String(value);
      }).join(' ');
    }
    return fallback;
  }

  function request(url, options) {
    options = options || {};
    options.headers = Object.assign({ 'Accept': 'application/json' }, options.headers || {});
    if (options.body) {
      options.headers['Content-Type'] = 'application/json';
      options.headers['X-CSRFToken'] = csrfToken;
    }
    return fetch(url, options).then(function (response) {
      var authError = window.GEApp && window.GEApp.authenticationError
        ? window.GEApp.authenticationError(response)
        : null;
      if (authError) throw authError;
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(errorMessage(data, 'No fue posible completar la operación.'));
        return data;
      });
    });
  }

  function emptyRow(message) {
    var columns = page.dataset.geApi === 'rates'
      ? 7
      : (page.dataset.geApi === 'currencies' && page.dataset.canManage !== 'true' ? 5 : 6);
    body.innerHTML = '<tr><td colspan="' + columns + '" class="ge-frontend-note">' + esc(message) + '</td></tr>';
  }

  function fail(error) {
    emptyRow(error.message || 'No fue posible cargar los datos.');
    notify(error.message || 'No fue posible cargar los datos.', 'error');
  }

  function dialog(id, title, content, confirmLabel, onConfirm, danger) {
    var previous = document.getElementById(id);
    if (previous) previous.remove();
    var backdrop = document.createElement('div');
    backdrop.id = id;
    backdrop.className = 'ge-modal-backdrop is-open';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.setAttribute('aria-labelledby', id + '-title');
    backdrop.innerHTML = '<div class="ge-modal"><h3 id="' + id + '-title">' + esc(title) + '</h3>' + content +
      '<div class="ge-modal-actions"><button type="button" class="ge-btn-outline" data-cancel>Cancelar</button>' +
      '<button type="button" class="ge-btn-primary' + (danger ? ' ge-btn-danger' : '') + '" data-confirm>' + esc(confirmLabel) + '</button></div></div>';
    document.body.appendChild(backdrop);
    function close() { backdrop.remove(); }
    backdrop.querySelector('[data-cancel]').addEventListener('click', close);
    backdrop.addEventListener('click', function (event) { if (event.target === backdrop) close(); });
    backdrop.querySelector('[data-confirm]').addEventListener('click', function () {
      if (!onConfirm || onConfirm(backdrop, close) !== false) close();
    });
    var first = backdrop.querySelector('input,select,button');
    if (first) first.focus();
  }

  function field(label, control) {
    return '<label class="ge-crud-field"><span class="ge-field-label">' + label + '</span>' + control + '</label>';
  }

  function flag(code) {
    return ({ USD: '🇺🇸', EUR: '🇪🇺', BRL: '🇧🇷', ARS: '🇦🇷', PYG: '🇵🇾', GBP: '🇬🇧', JPY: '🇯🇵' })[code] || '¤';
  }

  function formValue(form, name) {
    return form.elements[name] ? form.elements[name].value.trim() : '';
  }

  function renderCurrencies(items) {
    state.items = items;
    if (!items.length) return emptyRow('No hay monedas configuradas.');
    body.innerHTML = items.map(function (item) {
      var active = item.estado === 'ACTIVA';
      var actions = page.dataset.canManage === 'true'
        ? '<td><div class="ge-btn-row"><button class="ge-btn-ghost" data-action="edit" style="font-size:11px;padding:3px 8px">Editar</button>' +
          '<button class="ge-btn-ghost ge-btn-ghost--danger" data-action="state" style="font-size:11px;padding:3px 8px">' + (active ? 'Desactivar' : 'Activar') + '</button></div></td>'
        : '';
      return '<tr data-id="' + item.id + '"><td style="font-size:22px">' + flag(item.codigo) + '</td>' +
        '<td><span class="ge-mono" style="font-weight:700">' + esc(item.codigo) + '</span></td>' +
        '<td>' + esc(item.nombre) + '</td><td class="ge-mono">' + esc(item.simbolo) + '</td>' +
        '<td><span class="ge-state-dot ' + (active ? 'ge-state-dot--on' : '') + '"><i></i>' + (active ? 'Activa' : 'Inactiva') + '</span></td>' +
        actions + '</tr>';
    }).join('');
  }

  function loadCurrencies() {
    return request(page.dataset.listUrl).then(function (data) { renderCurrencies(data.monedas || []); }).catch(fail);
  }

  function currencyForm(item) {
    var editing = !!item;
    var content = '<form data-api-form><div class="ge-form-grid">' +
      field('CÓDIGO (ISO)', '<input class="ge-input" name="codigo" maxlength="10" required placeholder="USD" value="' + esc(editing ? item.codigo : '') + '">') +
      field('SÍMBOLO', '<input class="ge-input" name="simbolo" maxlength="10" required placeholder="$" value="' + esc(editing ? item.simbolo : '') + '">') + '</div>' +
      field('NOMBRE DE LA MONEDA', '<input class="ge-input" name="nombre" required placeholder="Dólar estadounidense" value="' + esc(editing ? item.nombre : '') + '">') +
      '<label class="ge-crud-check"><input type="checkbox" name="activa" ' + (!editing || item.estado === 'ACTIVA' ? 'checked' : '') + '> Moneda activa</label></form>';
    dialog('ge-currency-form', editing ? 'Editar moneda' : 'Nueva moneda', content, 'Guardar cambios', function (box, close) {
      var form = box.querySelector('form');
      if (!form.reportValidity()) return false;
      var payload = {
        codigo: formValue(form, 'codigo'), nombre: formValue(form, 'nombre'),
        simbolo: formValue(form, 'simbolo'), estado: form.elements.activa.checked ? 'ACTIVA' : 'INACTIVA'
      };
      request(editing ? endpoint(page.dataset.editUrl, item.id) : page.dataset.createUrl, {
        method: 'POST', body: JSON.stringify(payload)
      }).then(function (data) { close(); notify(data.message); loadCurrencies(); }).catch(function (error) { notify(error.message, 'error'); });
      return false;
    });
  }

  function initCurrencies() {
    loadCurrencies();
    var primary = page.querySelector('.ge-frontend-section-head .ge-btn-primary');
    if (primary) primary.addEventListener('click', function () {
      if (page.dataset.canManage !== 'true') return notify('Solo un administrador puede configurar monedas.', 'warning');
      currencyForm(null);
    });
    body.addEventListener('click', function (event) {
      var button = event.target.closest('[data-action]');
      if (!button) return;
      var id = Number(button.closest('tr').dataset.id);
      var item = state.items.find(function (entry) { return entry.id === id; });
      if (!item) return;
      if (page.dataset.canManage !== 'true') return notify('Solo un administrador puede configurar monedas.', 'warning');
      if (button.dataset.action === 'edit') return currencyForm(item);
      var next = item.estado === 'ACTIVA' ? 'INACTIVA' : 'ACTIVA';
      dialog('ge-currency-state', next === 'ACTIVA' ? 'Activar Moneda' : 'Desactivar Moneda',
        '<p>¿Confirmás esta acción sobre <strong>' + esc(item.nombre) + '</strong>?</p>', next === 'ACTIVA' ? 'Activar' : 'Desactivar',
        function (_box, close) {
          request(endpoint(page.dataset.stateUrl, item.id), { method: 'POST', body: JSON.stringify({ estado: next }) })
            .then(function (data) { close(); notify(data.message); loadCurrencies(); }).catch(function (error) { notify(error.message, 'error'); });
          return false;
        }, next !== 'ACTIVA');
    });
  }

  function number(value) {
    var parsed = Number(value);
    if (!Number.isFinite(parsed)) return '—';
    return parsed.toLocaleString('es-PY', { minimumFractionDigits: 0, maximumFractionDigits: 6 });
  }

  function relativeDate(value) {
    var seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60) return 'hace menos de 1 min';
    if (seconds < 3600) return 'hace ' + Math.floor(seconds / 60) + ' min';
    if (seconds < 86400) return 'hace ' + Math.floor(seconds / 3600) + ' h';
    return new Date(value).toLocaleDateString('es-PY');
  }

  function pairKey(rate) { return rate.moneda_origen.id + ':' + rate.moneda_destino.id; }

  function renderRates(history) {
    state.history = history;
    var ratesByPair = {};
    history.forEach(function (rate) {
      var key = pairKey(rate);
      if (!ratesByPair[key] || rate.vigente) ratesByPair[key] = rate;
    });
    var current = Object.keys(ratesByPair).map(function (key) { return ratesByPair[key]; }).filter(function (rate) {
      var pair = (rate.moneda_origen.codigo + '/' + rate.moneda_destino.codigo).toLowerCase();
      return !state.rateQuery || pair.indexOf(state.rateQuery) !== -1;
    });
    if (!current.length) return emptyRow(state.rateQuery ? 'No hay tasas comerciales que coincidan con la búsqueda.' : 'No hay tasas comerciales configuradas.');
    body.innerHTML = current.map(function (rate) {
      var previous = history.find(function (candidate) { return pairKey(candidate) === pairKey(rate) && candidate.id !== rate.id; });
      var change = previous ? ((Number(rate.compra) - Number(previous.compra)) / Number(previous.compra)) * 100 : 0;
      var trendClass = change > 0 ? 'ge-trend-up' : change < 0 ? 'ge-trend-down' : '';
      var trend = change > 0 ? '↑ ' : change < 0 ? '↓ ' : '— ';
      var pair = rate.moneda_origen.codigo + '/' + rate.moneda_destino.codigo;
      var edit = page.dataset.canManage === 'true' && rate.vigente
        ? '<button class="ge-btn-ghost" data-action="edit" style="font-size:11px;padding:3px 8px">Editar</button>' +
          '<button class="ge-btn-ghost ge-btn-ghost--danger" data-action="deactivate" style="font-size:11px;padding:3px 8px">Desactivar</button>'
        : '';
      var status = rate.vigente
        ? '<span class="ge-state-dot ge-state-dot--on"><i></i>Vigente</span>'
        : '<span class="ge-state-dot"><i></i>Inactiva</span>';
      return '<tr data-id="' + rate.id + '"><td><div class="ge-mono-cell"><span style="font-size:18px">' + flag(rate.moneda_origen.codigo) + '</span><strong class="ge-mono">' + esc(pair) + '</strong></div></td>' +
        '<td class="ge-mono">' + number(rate.compra) + '</td><td class="ge-mono">' + number(rate.venta) + '</td>' +
        '<td><span class="' + trendClass + '">' + trend + (previous ? Math.abs(change).toFixed(2) + '%' : '') + '</span></td>' +
        '<td>' + status + '</td>' +
        '<td class="ge-frontend-note">' + esc(relativeDate(rate.fecha_registro)) + '</td><td><div class="ge-btn-row">' + edit +
        '<button class="ge-btn-ghost" data-action="history" style="font-size:11px;padding:3px 8px">Historial</button></div></td></tr>';
    }).join('');
  }

  function loadRates() {
    return request(page.dataset.listUrl).then(function (data) {
      state.currencies = data.monedas || [];
      renderRates(data.tasas || []);
    }).catch(fail);
  }

  function currencyOptions(selected) {
    return state.currencies.map(function (currency) {
      return '<option value="' + currency.id + '" ' + (currency.id === selected ? 'selected' : '') + '>' + flag(currency.codigo) + ' ' + esc(currency.codigo + ' - ' + currency.nombre) + '</option>';
    }).join('');
  }

  function rateForm(rate) {
    var origin = rate ? rate.moneda_origen.id : (state.currencies[0] || {}).id;
    var pyg = state.currencies.find(function (currency) { return currency.codigo === 'PYG'; });
    var destination = rate ? rate.moneda_destino.id : (pyg || state.currencies[1] || {}).id;
    var content = '<form data-api-form><div class="ge-form-grid">' +
      field('MONEDA DE ORIGEN', '<select class="ge-input" name="origen" required>' + currencyOptions(origin) + '</select>') +
      field('MONEDA DE DESTINO', '<select class="ge-input" name="destino" required>' + currencyOptions(destination) + '</select>') + '</div><div class="ge-form-grid">' +
      field('PRECIO COMPRA', '<input class="ge-input ge-mono" type="number" min="0.000001" step="0.000001" name="compra" required value="' + esc(rate ? rate.compra : '') + '">') +
      field('PRECIO VENTA', '<input class="ge-input ge-mono" type="number" min="0.000001" step="0.000001" name="venta" required value="' + esc(rate ? rate.venta : '') + '">') + '</div></form>';
    dialog('ge-rate-form', rate ? 'Editar tasa comercial' : 'Nueva tasa comercial', content, rate ? 'Guardar nueva versión' : 'Crear tasa comercial', function (box, close) {
      var form = box.querySelector('form');
      if (!form.reportValidity()) return false;
      if (form.elements.origen.value === form.elements.destino.value) {
        notify('Las monedas de origen y destino deben ser diferentes.', 'warning'); return false;
      }
      request(page.dataset.createUrl, { method: 'POST', body: JSON.stringify({
        moneda_origen_id: Number(form.elements.origen.value), moneda_destino_id: Number(form.elements.destino.value),
        compra: formValue(form, 'compra'), venta: formValue(form, 'venta')
      }) }).then(function (data) { close(); notify(data.mensaje); loadRates(); }).catch(function (error) { notify(error.message, 'error'); });
      return false;
    });
  }

  function rateHistory(rate) {
    var entries = state.history.filter(function (candidate) { return pairKey(candidate) === pairKey(rate); });
    var rows = entries.map(function (entry) {
      var pair = entry.moneda_origen.codigo + '/' + entry.moneda_destino.codigo;
      var status = entry.vigente ? '<span class="ge-state-dot ge-state-dot--on"><i></i>Vigente</span>' : '<span class="ge-state-dot"><i></i>Histórica</span>';
      var user = entry.usuario_username || entry.usuario_id || '—';
      return '<tr><td class="ge-mono">v' + entry.version + '</td><td class="ge-mono">' + esc(pair) + '</td><td class="ge-mono">' + number(entry.compra) + '</td><td class="ge-mono">' + number(entry.venta) + '</td><td>' + status + '</td><td>' + esc(user) + '</td><td class="ge-frontend-note">' + esc(new Date(entry.fecha_registro).toLocaleString('es-PY')) + '</td></tr>';
    }).join('');
    dialog('ge-rate-history', 'Historial de tasa comercial', '<div class="ge-card" style="overflow:auto"><table class="ge-table"><thead><tr><th>Versión</th><th>Par</th><th>Compra</th><th>Venta</th><th>Estado</th><th>Usuario</th><th>Fecha</th></tr></thead><tbody>' + rows + '</tbody></table></div>', 'Cerrar');
  }

  function initRates() {
    loadRates();
    var primary = page.querySelector('.ge-frontend-section-head .ge-btn-primary');
    var search = page.querySelector('.ge-search-box input');
    if (search) search.addEventListener('input', function () {
      state.rateQuery = search.value.trim().toLowerCase();
      renderRates(state.history);
    });
    if (primary) primary.addEventListener('click', function () {
      if (page.dataset.canManage !== 'true') return notify('Solo un analista cambiario puede actualizar tasas.', 'warning');
      rateForm(null);
    });
    body.addEventListener('click', function (event) {
      var button = event.target.closest('[data-action]');
      if (!button) return;
      var id = Number(button.closest('tr').dataset.id);
      var rate = state.history.find(function (entry) { return entry.id === id; });
      if (!rate) return;
      if (button.dataset.action === 'edit') {
        if (page.dataset.canManage !== 'true') return notify('Solo un analista cambiario puede actualizar tasas.', 'warning');
        rateForm(rate);
      }
      if (button.dataset.action === 'deactivate') {
        if (page.dataset.canManage !== 'true' || !rate.vigente) return notify('Solo un analista cambiario puede desactivar tasas vigentes.', 'warning');
        dialog('ge-rate-deactivate', 'Desactivar tasa comercial',
          '<p>La tasa <strong>' + esc(rate.moneda_origen.codigo + '/' + rate.moneda_destino.codigo) + '</strong> dejará de estar vigente y permanecerá en el historial.</p>',
          'Desactivar', function (_box, close) {
            request(endpoint(page.dataset.deactivateUrl, rate.id), { method: 'POST', body: JSON.stringify({}) })
              .then(function (data) { close(); notify(data.mensaje); loadRates(); })
              .catch(function (error) { notify(error.message, 'error'); });
            return false;
          }, true);
      }
      if (button.dataset.action === 'history') rateHistory(rate);
    });
  }

  function renderPayments(items) {
    state.items = items;
    if (!items.length) return emptyRow('No hay medios de pago configurados.');
    body.innerHTML = items.map(function (item) {
      var active = item.estado === 'ACTIVO';
      return '<tr data-id="' + item.id + '"><td>' + esc(item.cliente.nombre) + '</td><td>' + esc(item.nombre) + '</td>' +
        '<td><span class="ge-chip">' + esc(item.tipo_display) + '</span></td><td class="ge-mono">—</td>' +
        '<td><span class="ge-state-dot ' + (active ? 'ge-state-dot--on' : '') + '"><i></i>' + (active ? 'Activo' : 'Inactivo') + '</span></td>' +
        '<td><div class="ge-btn-row"><button class="ge-btn-ghost" data-action="edit" style="font-size:11px;padding:3px 8px">Editar</button>' +
        '<button class="ge-btn-ghost ge-btn-ghost--danger" data-action="state" style="font-size:11px;padding:3px 8px">' + (active ? 'Desactivar' : 'Activar') + '</button></div></td></tr>';
    }).join('');
  }

  function loadPayments() {
    return request(page.dataset.listUrl).then(function (data) {
      state.clients = data.clientes || state.clients;
      renderPayments(data.metodos || []);
    }).catch(fail);
  }

  function clientOptions(selected) {
    return state.clients.map(function (client) {
      return '<option value="' + client.id + '" ' + (client.id === selected ? 'selected' : '') + '>' + esc(client.nombre) + '</option>';
    }).join('');
  }

  function paymentForm(item) {
    var selectedClient = item ? item.cliente.id : (state.clients[0] || {}).id;
    var type = item ? item.tipo : 'EFECTIVO';
    var types = [['EFECTIVO', 'Efectivo'], ['TARJETA', 'Tarjeta'], ['TRANSFERENCIA', 'Transferencia'], ['OTRO', 'Otro']];
    var typeOptions = types.map(function (entry) { return '<option value="' + entry[0] + '" ' + (entry[0] === type ? 'selected' : '') + '>' + entry[1] + '</option>'; }).join('');
    var content = '<form data-api-form>' + field('CLIENTE ASOCIADO', '<select class="ge-input" name="cliente" required>' + clientOptions(selectedClient) + '</select>') +
      '<div class="ge-form-grid">' + field('TIPO DE MEDIO', '<select class="ge-input" name="tipo" required>' + typeOptions + '</select>') +
      field('NOMBRE / ENTIDAD', '<input class="ge-input" name="nombre" required placeholder="Banco, tarjeta o efectivo" value="' + esc(item ? item.nombre : '') + '">') + '</div>' +
      '<label class="ge-crud-check"><input type="checkbox" name="activo" ' + (!item || item.estado === 'ACTIVO' ? 'checked' : '') + '> Medio de pago activo</label></form>';
    dialog('ge-payment-form', item ? 'Editar medio de pago' : 'Nuevo medio de pago', content, 'Guardar medio de pago', function (box, close) {
      var form = box.querySelector('form');
      if (!form.reportValidity()) return false;
      var payload = { cliente: Number(form.elements.cliente.value), nombre: formValue(form, 'nombre'), tipo: form.elements.tipo.value, estado: form.elements.activo.checked ? 'ACTIVO' : 'INACTIVO' };
      request(item ? endpoint(page.dataset.editUrl, item.id) : page.dataset.createUrl, { method: 'POST', body: JSON.stringify(payload) })
        .then(function (data) { close(); notify(data.message); loadPayments(); }).catch(function (error) { notify(error.message, 'error'); });
      return false;
    });
  }

  function initPayments() {
    loadPayments();
    var primary = page.querySelector('.ge-frontend-section-head .ge-btn-primary');
    if (primary) primary.addEventListener('click', function () {
      if (!state.clients.length) return notify('Primero debe existir un cliente para asociar el medio de pago.', 'warning');
      paymentForm(null);
    });
    body.addEventListener('click', function (event) {
      var button = event.target.closest('[data-action]');
      if (!button) return;
      var id = Number(button.closest('tr').dataset.id);
      var item = state.items.find(function (entry) { return entry.id === id; });
      if (!item) return;
      if (button.dataset.action === 'edit') return paymentForm(item);
      dialog('ge-payment-state', item.estado === 'ACTIVO' ? 'Desactivar Medio de Pago' : 'Activar Medio de Pago',
        '<p>¿Confirmás esta acción sobre <strong>' + esc(item.nombre) + '</strong>?</p>', item.estado === 'ACTIVO' ? 'Desactivar' : 'Activar',
        function (_box, close) {
          request(endpoint(page.dataset.stateUrl, item.id), { method: 'POST', body: JSON.stringify({}) })
            .then(function (data) { close(); notify(data.message); loadPayments(); }).catch(function (error) { notify(error.message, 'error'); });
          return false;
        }, item.estado === 'ACTIVO');
    });
  }

  function renderReferenceRates(data) {
    var status = page.querySelector('[data-reference-status]');
    var message = page.querySelector('[data-reference-message]');
    var items = data.tasas_referencia || [];
    var commercialBody = page.querySelector('[data-commercial-rates]');
    var commercialItems = data.tasas_comerciales || [];
    if (status) {
      status.textContent = {
        actualizado: 'Actualizadas',
        desactualizado: 'Respaldo disponible',
        vacio: 'Sin monedas',
        indisponible: 'No disponible'
      }[data.estado] || data.estado || 'Sin datos';
    }
    if (message) {
      message.hidden = !data.mensaje;
      message.textContent = data.mensaje || '';
      message.className = data.estado === 'desactualizado'
        ? 'ge-warning-banner'
        : 'ge-inline-banner';
    }
    if (commercialBody) {
      commercialBody.setAttribute('aria-busy', 'false');
      if (!commercialItems.length) {
        commercialBody.innerHTML = '<article class="ge-card ge-empty"><strong>Sin tasas comerciales vigentes</strong>' +
          '<p>Actualmente no existen tasas comerciales vigentes para mostrar.</p></article>';
      } else {
        commercialBody.innerHTML = commercialItems.map(function (item) {
          return '<article class="ge-card" style="padding:24px">' +
            '<div class="ge-quote-head"><div class="ge-quote-id"><span style="font-size:24px">' +
            flag(item.moneda_origen) + '</span><div><strong class="ge-mono">' +
            esc(item.par) + '</strong><span class="ge-frontend-note">Tasa comercial</span></div></div>' +
            '<span class="ge-state-dot ge-state-dot--on"><i></i>Vigente</span></div>' +
            '<div class="ge-quote-rates"><div><small>COMPRA</small><strong class="ge-mono">' +
            number(item.compra) + '</strong></div><div class="ge-quote-divider"></div>' +
            '<div><small>VENTA</small><strong class="ge-mono">' + number(item.venta) + '</strong></div></div>' +
            '<div class="ge-frontend-note" style="text-align:center">Actualizada ' +
            esc(relativeDate(item.fecha_hora)) + '</div></article>';
        }).join('');
      }
    }
    body.setAttribute('aria-busy', 'false');
    if (!items.length) {
      body.innerHTML = '<article class="ge-card ge-empty"><strong>Sin tasas disponibles</strong><p>' +
        esc(data.mensaje || 'Todavía no existen tasas de referencia para mostrar.') +
        '</p></article>';
      return;
    }
    body.innerHTML = items.map(function (item) {
      var stale = item.desactualizada
        ? '<span class="ge-badge ge-badge--warning">Dato de respaldo</span>'
        : '<span class="ge-state-dot ge-state-dot--on"><i></i>Vigente</span>';
      return '<article class="ge-card" style="padding:24px">' +
        '<div class="ge-quote-head"><div class="ge-quote-id"><span style="font-size:24px">' +
        flag(item.moneda_cotizada) + '</span><div><strong class="ge-mono">' +
        esc(item.par) + '</strong><span class="ge-frontend-note">Base ' +
        esc(item.moneda_base) + '</span></div></div><div>' + stale + '</div></div>' +
        '<div class="ge-quote-rates"><div><small>TASA DE REFERENCIA</small><strong class="ge-mono">' +
        number(item.valor) + '</strong></div><div class="ge-quote-divider"></div>' +
        '<div><small>FUENTE</small><strong>' + esc(item.fuente) + '</strong></div></div>' +
        '<div class="ge-frontend-note" style="text-align:center">Actualizada ' +
        esc(relativeDate(item.fecha_hora)) + ' · Vigente hasta ' +
        esc(new Date(item.vigente_hasta).toLocaleString('es-PY')) + '</div></article>';
    }).join('');
  }

  function initReferenceRates() {
    request(page.dataset.listUrl).then(renderReferenceRates).catch(function (error) {
      var commercialBody = page.querySelector('[data-commercial-rates]');
      body.setAttribute('aria-busy', 'false');
      if (commercialBody) commercialBody.setAttribute('aria-busy', 'false');
      body.innerHTML = '<article class="ge-card ge-empty"><strong>No se pudieron cargar las tasas</strong><p>' +
        esc(error.message) + '</p></article>';
      notify(error.message, 'error');
    });
  }

  function initSimulator() {
    var root = page.querySelector('[data-simulator]');
    var amount = root.querySelector('[data-sim-amount]');
    var from = root.querySelector('[data-sim-from]');
    var to = root.querySelector('[data-sim-to]');
    var result = root.querySelector('[data-sim-result]');
    var delivered = root.querySelector('[data-sim-delivered]');
    var rate = root.querySelector('[data-sim-rate]');
    var rateType = root.querySelector('[data-sim-rate-type]');
    var updated = root.querySelector('[data-sim-updated]');
    var error = root.querySelector('[data-sim-error]');
    var swap = root.querySelector('[data-sim-swap]');
    var timer = null;

    function showError(message) {
      error.textContent = message;
      error.hidden = false;
      result.textContent = '—';
      delivered.textContent = '—';
      rate.textContent = '—';
      rateType.textContent = '—';
      updated.textContent = '—';
      root.setAttribute('aria-busy', 'false');
    }

    function clearError() {
      error.hidden = true;
      error.textContent = '';
    }

    function simulate() {
      clearError();
      var raw = amount.value.trim().replace(',', '.');
      var value = Number(raw);
      if (!raw) {
        result.textContent = '—';
        delivered.textContent = '—';
        rate.textContent = '—';
        rateType.textContent = '—';
        updated.textContent = '—';
        return;
      }
      if (!Number.isFinite(value) || value <= 0) {
        showError('El monto debe ser mayor que cero.');
        return;
      }
      if (!from.value || !to.value || from.value === to.value) {
        showError('La moneda de origen y destino deben ser diferentes.');
        return;
      }
      result.textContent = 'Calculando…';
      delivered.textContent = 'Calculando…';
      root.setAttribute('aria-busy', 'true');
      request(page.dataset.simulateUrl, {
        method: 'POST',
        body: JSON.stringify({
          moneda_origen_id: Number(from.value),
          moneda_destino_id: Number(to.value),
          monto: raw
        })
      }).then(function (data) {
        result.textContent = number(data.resultado) + ' ' + data.moneda_destino;
        delivered.textContent = number(data.monto) + ' ' + data.moneda_origen;
        rate.textContent = '1 ' + data.moneda_origen + ' = ' +
          number(data.tasa) + ' ' + data.moneda_destino;
        rateType.textContent = data.tipo_tasa || '—';
        updated.textContent = new Date(data.fecha_hora).toLocaleString('es-PY');
        root.setAttribute('aria-busy', 'false');
      }).catch(function (requestError) {
        showError(requestError.message || 'No fue posible realizar la simulación.');
      });
    }

    function schedule() {
      window.clearTimeout(timer);
      timer = window.setTimeout(simulate, 300);
    }

    request(page.dataset.currenciesUrl).then(function (data) {
      state.currencies = data.monedas || [];
      var options = state.currencies.map(function (currency) {
        return '<option value="' + currency.id + '" data-code="' +
          esc(currency.codigo) + '">' + flag(currency.codigo) + ' ' +
          esc(currency.codigo) + '</option>';
      }).join('');
      from.innerHTML = options;
      to.innerHTML = options;
      var usd = state.currencies.find(function (currency) { return currency.codigo === 'USD'; });
      var pyg = state.currencies.find(function (currency) { return currency.codigo === 'PYG'; });
      if (usd) from.value = String(usd.id);
      if (pyg) to.value = String(pyg.id);
      if (!state.currencies.length) showError('No hay monedas activas disponibles.');
    }).catch(function (requestError) {
      showError(requestError.message || 'No fue posible cargar las monedas.');
    });

    amount.addEventListener('input', schedule);
    from.addEventListener('change', simulate);
    to.addEventListener('change', simulate);
    swap.addEventListener('click', function () {
      var previous = from.value;
      from.value = to.value;
      to.value = previous;
      swap.classList.add('is-swapping');
      simulate();
      window.setTimeout(function () { swap.classList.remove('is-swapping'); }, 320);
    });

  }

  if (page.dataset.geApi === 'currencies') initCurrencies();
  if (page.dataset.geApi === 'rates') initRates();
  if (page.dataset.geApi === 'payments') initPayments();
  if (page.dataset.geApi === 'reference-rates') initReferenceRates();
  if (page.dataset.geApi === 'simulator') initSimulator();
}());
