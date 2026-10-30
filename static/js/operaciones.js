(function () {
  'use strict';

  var page = document.querySelector('[data-operaciones-page]');
  if (!page) return;

  var form = page.querySelector('[data-operation-form]');
  var previewCard = page.querySelector('[data-preview-card]');
  var historyBody = page.querySelector('[data-history-body]');
  var feedback = page.querySelector('[data-operation-feedback]');
  var state = {
    preview: null,
    payload: null,
    idempotencyKey: null,
    transactions: [],
    cashRecentVersion: 0,
    cancelTarget: null,
    detailId: null,
    detailTransaction: null,
    detailVersion: 0,
    paymentVersion: 0,
    paymentPending: {},
    methodsLoading: false,
    methodsVersion: 0,
    confirmationPending: false,
    confirmationPayload: null,
    selectedMethod: null,
    paymentStatus: null,
    paymentData: null,
    methodChangePending: {},
    methodChangeRequests: {},
    methodChangeVersion: 0,
    liquidationVersion: 0,
    liquidationLoading: false,
    liquidationPeriods: [],
    liquidationPending: {},
    liquidationUncertain: {},
    liquidationErrors: {}
  };

  function csrfToken() {
    var input = page.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function detailMessages(value) {
    if (!value) return [];
    if (Array.isArray(value)) {
      return value.reduce(function (all, item) { return all.concat(detailMessages(item)); }, []);
    }
    if (typeof value === 'object') {
      return Object.keys(value).reduce(function (all, key) {
        return all.concat(detailMessages(value[key]));
      }, []);
    }
    return [String(value)];
  }

  function responseMessage(data, fallback) {
    var details = detailMessages(data && data.detalles);
    if (details.length) return details.join(' ');
    return data && (data.error || data.mensaje) ? data.error || data.mensaje : fallback;
  }

  function apiRequest(url, options) {
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        var authError = window.GEApp && window.GEApp.authenticationError(response);
        if (authError) {
          authError.status = response.status;
          authError.codigo = data.codigo;
          throw authError;
        }
        if (!response.ok) {
          var error = new Error(responseMessage(data, 'No se pudo completar la solicitud.'));
          error.status = response.status;
          error.codigo = data.codigo;
          error.fields = data.detalles || data.errores;
          error.payload = data;
          throw error;
        }
        return data;
      });
    });
  }

  function post(url, payload) {
    return apiRequest(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken()
      },
      body: JSON.stringify(payload)
    });
  }

  function resourceUrl(template, id) {
    return template.replace('/0/', '/' + encodeURIComponent(id) + '/');
  }

  function notify(message, type) {
    clearFeedback();
    window.GEApp.toast(message, type);
  }

  function destinationCurrency(operation) {
    if (operation && operation.moneda_destino) return operation.moneda_destino.codigo;
    var select = form && form.elements.moneda_destino_id;
    var option = select && select.options[select.selectedIndex];
    return option && option.value ? option.textContent.split(' · ')[0].trim() : '';
  }

  var amountLimits = (function () {
    var script = document.getElementById('operacion-limites-monto');
    try { return script ? JSON.parse(script.textContent) : null; }
    catch (_error) { return null; }
  })();

  function currentAmountLimits() {
    if (!amountLimits || !form) return null;
    var origin = form.elements.moneda_origen_id;
    var option = origin && origin.options && origin.options[origin.selectedIndex];
    var currency = option && option.dataset.codigo;
    var onlinePurchase = page.dataset.presencial !== 'true' && form.elements.tipo && form.elements.tipo.value === 'COMPRA';
    return onlinePurchase && amountLimits.compra_online && amountLimits.compra_online[currency]
      ? amountLimits.compra_online[currency] : amountLimits.general;
  }

  function updateAmountLimits() {
    var input = form && form.elements.monto_origen;
    var limits = currentAmountLimits();
    if (!input || !limits) return;
    input.min = limits.minimo;
    input.step = limits.minimo;
    input.max = limits.maximo;
  }

  // Mantener dígitos y exponente separados evita redondear o expandir importes grandes.
  function exactPositiveAmount(raw) {
    var match = /^\+?(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(String(raw).trim());
    if (!match) return null;
    var fraction = match[2] || match[3] || '';
    var digits = ((match[1] || '') + fraction).replace(/^0+/, '');
    if (!digits) return null;
    var significant = digits.replace(/0+$/, '');
    var exponent = Number(match[4] || 0) - fraction.length + digits.length - significant.length;
    return { digits: significant, exponent: exponent, order: significant.length + exponent };
  }

  function exceedsAmount(value, maximum) {
    if (value.order !== maximum.order) return value.order > maximum.order;
    var length = Math.max(value.digits.length, maximum.digits.length);
    return value.digits.padEnd(length, '0') > maximum.digits.padEnd(length, '0');
  }

  function validateAmount() {
    var input = form && form.elements.monto_origen;
    if (!input) return true;
    var value = exactPositiveAmount(input.value);
    var limits = currentAmountLimits();
    var message = '';
    if (!value) message = 'Ingresá un monto válido mayor a cero.';
    else if (limits && exceedsAmount(value, exactPositiveAmount(limits.maximo))) {
      message = 'El monto ingresado supera el límite permitido para una operación.';
    } else if (limits && value.exponent < -limits.decimales) {
      message = limits.decimales === 0 ? 'Ingresá un monto sin decimales para esta moneda.'
        : 'Ingresá un monto con hasta ' + limits.decimales + ' decimales.';
    }
    if (!message) return true;
    invalidatePreview();
    notify(message, 'error');
    return false;
  }

  function errorMessage(error, operation) {
    if (error.codigo === 'MONTO_EXCESIVO') return 'El monto ingresado supera el límite permitido para una operación.';
    if (error.codigo === 'MONTO_INVALIDO') return 'Ingresá un monto válido mayor a cero.';
    if (error.codigo === 'DISPONIBILIDAD_INSUFICIENTE' || error.codigo === 'SALDO_INSUFICIENTE') {
      var currency = destinationCurrency(operation || state.preview);
      return window.GEApp.insufficientFundsMessage(currency);
    }
    return window.GEApp.userMessage ? window.GEApp.userMessage(error.message) : error.message;
  }

  function fieldErrors(error) {
    if (/^MONTO_(INVALIDO|EXCESIVO|PRECISION)$/.test(error.codigo)) return false;
    if (!form || !error.fields || typeof error.fields !== 'object' || Array.isArray(error.fields)) return false;
    var shown = false;
    Object.keys(error.fields).forEach(function (name) {
      var input = form.elements[name === 'monto' ? 'monto_origen' : name];
      if (!input || !input.setCustomValidity) return;
      var message = detailMessages(error.fields[name]).join(' ');
      message = window.GEApp.userMessage ? window.GEApp.userMessage(message) : message;
      input.setCustomValidity(message);
      input.setAttribute('aria-invalid', 'true');
      var note = document.createElement('small');
      note.className = 'ge-field-error';
      note.dataset.operationFieldError = 'true';
      note.textContent = message;
      input.insertAdjacentElement('afterend', note);
      shown = true;
    });
    return shown;
  }

  function clearFieldErrors() {
    if (!form) return;
    form.querySelectorAll('[data-operation-field-error]').forEach(function (note) { note.remove(); });
    Array.prototype.forEach.call(form.elements, function (input) {
      if (input.setCustomValidity) input.setCustomValidity('');
      input.removeAttribute('aria-invalid');
    });
  }

  function clearFeedback() {
    feedback.hidden = true;
    feedback.textContent = '';
    feedback.className = 'ge-operation-feedback';
  }

  function setBusy(button, busy, busyText) {
    if (!button) return;
    if (busy) {
      button.dataset.originalText = button.textContent;
      button.textContent = busyText;
      button.disabled = true;
    } else {
      button.textContent = button.dataset.originalText || button.textContent;
      button.disabled = false;
    }
  }

  function formatNumber(value) {
    var number = Number(value);
    if (!Number.isFinite(number)) return String(value || '—');
    return number.toLocaleString('es-PY', { maximumFractionDigits: 6 });
  }

  function formatAmount(value, currency) {
    return formatNumber(value) + ' ' + (currency || '');
  }

  function formatRate(value) {
    return window.GEApp && window.GEApp.formatRate
      ? window.GEApp.formatRate(value)
      : formatNumber(value);
  }

  function formatDate(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('es-PY', { dateStyle: 'short', timeStyle: 'short' });
  }

  function field(name) {
    return previewCard && previewCard.querySelector('[data-preview-field="' + name + '"]');
  }

  function setField(name, value) {
    var element = field(name);
    if (element) element.textContent = value;
  }

  function invalidatePreview() {
    state.preview = null;
    state.payload = null;
    state.idempotencyKey = null;
    state.confirmationPayload = null;
    if (previewCard) previewCard.hidden = true;
  }

  function formPayload() {
    var data = new FormData(form);
    return {
      cliente_id: data.get('cliente_id'),
      tipo: data.get('tipo'),
      moneda_origen_id: data.get('moneda_origen_id'),
      moneda_destino_id: data.get('moneda_destino_id'),
      monto: data.get('monto_origen'),
      metodo_pago_id: data.get('metodo_pago_id')
    };
  }

  function loadPaymentMethods(aviso) {
    if (!page.dataset.methodsUrl) return;
    var initial = document.querySelector('[data-new-method]');
    var select = document.querySelector('[data-confirm-method]');
    var button = document.querySelector('[data-confirm-operation]');
    if (state.selectedMethod === null && initial && initial.value) state.selectedMethod = initial.value;
    var version = ++state.methodsVersion;
    state.methodsLoading = true;
    select.disabled = true;
    if (initial) initial.disabled = true;
    button.disabled = true;
    page.querySelector('[data-open-confirm]').disabled = true;
    if (form) form.querySelector('[data-preview-button]').disabled = true;
    document.querySelector('[data-confirm-message]').textContent = aviso || 'Consultando métodos disponibles…';
    return apiRequest(page.dataset.methodsUrl, { credentials: 'same-origin' }).then(function (data) {
      if (state.methodsVersion !== version) return;
      var preferred = data.metodo_pago_preferido && data.metodo_pago_preferido.id;
      var methods = data.metodos_pago || [];
      var chosen = state.selectedMethod === null && !aviso ? String(preferred || '') : state.selectedMethod;
      if (page.dataset.presencial === 'true' && methods.length === 1) chosen = String(methods[0].id);
      chosen = methods.some(function (method) { return String(method.id) === chosen; }) ? chosen : '';
      select.innerHTML = '<option value="">Seleccionar método</option>' + methods.map(function (method) {
        return '<option value="' + escapeHtml(method.id) + '"' + (String(method.id) === chosen ? ' selected' : '') + '>' + escapeHtml(method.nombre) + '</option>';
      }).join('');
      select.value = chosen;
      state.selectedMethod = chosen;
      if (initial) { initial.innerHTML = select.innerHTML; initial.value = chosen; }
      state.methodsLoading = false;
      select.disabled = !methods.length || state.confirmationPending;
      if (initial) initial.disabled = select.disabled;
      button.disabled = select.disabled || !select.value;
      page.querySelector('[data-open-confirm]').disabled = button.disabled;
      if (form) form.querySelector('[data-preview-button]').disabled = !methods.length;
      document.querySelector('[data-confirm-message]').textContent = '';
      if (initial) document.querySelector('[data-new-method-message]').textContent = '';
      if (!methods.length) notify(page.dataset.presencial === 'true'
        ? 'No hay métodos de efectivo activos. Solicitá que se habilite uno para previsualizar la operación.'
        : 'No hay métodos de pago habilitados disponibles.', 'error');
    }).catch(function (error) {
      if (state.methodsVersion !== version) return;
      state.methodsLoading = false;
      // Una consulta fallida no debe dejar los controles de edición bloqueados.
      select.disabled = state.confirmationPending || Boolean(state.confirmationPayload);
      if (initial) initial.disabled = select.disabled;
      button.disabled = select.disabled || !select.value;
      page.querySelector('[data-open-confirm]').disabled = button.disabled;
      if (form) form.querySelector('[data-preview-button]').disabled = false;
      document.querySelector('[data-confirm-message]').textContent = '';
      notify(errorMessage(error), 'error');
    });
  }

  function syncMethodSelection(select) {
    if (state.confirmationPending || state.confirmationPayload) return;
    state.selectedMethod = select.value;
    var initial = document.querySelector('[data-new-method]');
    if (initial) initial.value = select.value;
    document.querySelector('[data-confirm-method]').value = select.value;
    var disabled = state.methodsLoading || !select.value;
    document.querySelector('[data-confirm-operation]').disabled = disabled;
    page.querySelector('[data-open-confirm]').disabled = disabled;
  }

  function renderPreview(preview) {
    // Los valores financieros se presentan tal como llegan del backend.
    setField('tipo', preview.tipo === 'COMPRA' ? 'Compra' : 'Venta');
    setField('cliente', preview.cliente.nombre_razon_social);
    setField('origen', formatAmount(preview.monto_origen, preview.moneda_origen.codigo));
    setField('tasa', formatRate(preview.tasa));
    setField('convertido', formatAmount(preview.monto_convertido, preview.moneda_destino.codigo));
    setField('comision', formatAmount(preview.importe_comision, preview.moneda_destino.codigo) + ' (' + formatNumber(preview.porcentaje_comision) + '%)');
    setField('destino', formatAmount(preview.monto_destino, preview.moneda_destino.codigo));
    var initial = document.querySelector('[data-new-method]');
    var select = document.querySelector('[data-confirm-method]');
    select.innerHTML = initial.innerHTML;
    select.disabled = initial.disabled;
    syncMethodSelection(initial);
    document.querySelector('[data-confirm-method-label]').textContent = preview.tipo === 'VENTA' ? 'Medio de recepción' : 'Método de pago';
    previewCard.hidden = false;
    previewCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function createIdempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.floor(Math.random() * 16);
      return (c === 'x' ? r : (r & 3) | 8).toString(16);
    });
  }

  function openConfirmation() {
    if (!state.preview || !state.payload || state.methodsLoading || !document.querySelector('[data-confirm-method]').value) return;
    // La misma clave se conserva si el usuario reintenta esta confirmación.
    if (!state.idempotencyKey) state.idempotencyKey = createIdempotencyKey();
    document.querySelector('[data-confirm-method-label]').textContent = state.preview.tipo === 'VENTA' ? 'Medio de recepción' : 'Método de pago';
    window.GEApp.openModal('confirmar-operacion');
  }

  function confirmOperation(event) {
    var button = event.currentTarget;
    if (!state.preview || !state.payload || button.disabled || state.confirmationPending || state.methodsLoading) return;
    if (!state.idempotencyKey) state.idempotencyKey = createIdempotencyKey();

    var select = document.querySelector('[data-confirm-method]');
    if (!state.confirmationPayload && !select.value) return;
    var payload = state.confirmationPayload || Object.assign({}, state.payload, {
      metodo_pago_id: Number(select.value),
      firma_preview: state.preview.firma_preview,
      clave_idempotencia: state.idempotencyKey,
      version_preview: state.preview.tasa_comercial.version,
      tasa_preview: state.preview.tasa,
      categoria_preview_id: state.preview.categoria_preview_id,
      porcentaje_comision_preview: state.preview.porcentaje_comision
    });

    state.confirmationPayload = payload;
    state.confirmationPending = true;
    select.disabled = true;
    var initial = document.querySelector('[data-new-method]');
    if (initial) initial.disabled = true;
    var recargarMetodos = null;
    setBusy(button, true, 'Confirmando…');
    post(page.dataset.createUrl, payload).then(function (data) {
      window.GEApp.closeModal('confirmar-operacion');
      var repeated = data.repetida ? ' La solicitud ya había sido procesada.' : '';
      var statusMessage = data.transaccion.estado === 'PENDIENTE'
        ? (data.transaccion.canal === 'ONLINE' ? ' registrada y pendiente de pago.' : ' registrada y pendiente de intercambio físico.')
        : ' registrada. Estado: ' + data.transaccion.estado + '.';
      notify('Transacción #' + data.transaccion.id + statusMessage + repeated, 'success');
      invalidatePreview();
      loadHistory();
      showDetail(data.transaccion);
    }).catch(function (error) {
      if (error.status === 400 && error.codigo === 'METODO_NO_DISPONIBLE') {
        recargarMetodos = error.message;
        state.confirmationPayload = null;
        state.selectedMethod = '';
      }
      if (error.status === 400 && /^MONTO_(INVALIDO|EXCESIVO|PRECISION)$/.test(error.codigo)) {
        invalidatePreview();
        window.GEApp.closeModal('confirmar-operacion');
      }
      if (error.codigo === 'DISPONIBILIDAD_INSUFICIENTE') window.GEApp.closeModal('confirmar-operacion');
      notify(errorMessage(error), 'error');
    }).finally(function () {
      state.confirmationPending = false;
      setBusy(button, false);
      select.disabled = Boolean(state.confirmationPayload);
      if (initial) initial.disabled = select.disabled;
      if (recargarMetodos) loadPaymentMethods(recargarMetodos);
    });
  }

  function statusBadge(status) {
    var modifier = status === 'COMPLETADA' ? 'success' : status === 'PENDIENTE' ? 'warning' : 'danger';
    return '<span class="ge-status-badge ge-status-badge--' + modifier + ' ge-status-badge--sm"><span class="ge-status-dot"></span>' + escapeHtml(status) + '</span>';
  }

  function renderHistory() {
    if (!state.transactions.length) {
      historyBody.innerHTML = '<tr><td colspan="' + (page.dataset.operativeInbox === 'true' ? 8 : 7) + '" class="no-data">Todavía no hay transacciones disponibles.</td></tr>';
      return;
    }

    var limit = Number(page.dataset.historyLimit);
    var visible = limit > 0 ? state.transactions.slice(0, limit) : state.transactions;
    historyBody.innerHTML = visible.map(function (transaction, index) {
      if (page.dataset.operativeInbox === 'true') {
        var liquidable = transaction.estado === 'PENDIENTE' &&
          transaction.canal === 'PRESENCIAL' && transaction.version_flujo === 1 && isCash(transaction);
        var payment = isCash(transaction) || transaction.liquidacion_efectivo ? cashPaymentLabel(transaction)
          : transaction.tipo === 'VENTA' ? 'No aplica' : (transaction.pago_estado || 'Pago no iniciado');
        return '<tr><td>#' + escapeHtml(transaction.id) + '</td><td>' + escapeHtml(transaction.cliente.nombre_razon_social) +
          '</td><td>' + escapeHtml(transaction.tipo) + '</td><td>' + escapeHtml(formatAmount(transaction.monto_origen, transaction.moneda_origen.codigo)) +
          '</td><td>' + escapeHtml(formatAmount(transaction.monto_destino, transaction.moneda_destino.codigo)) +
          '</td><td>' + escapeHtml(payment) + '</td><td>' + statusBadge(transaction.estado) +
          '</td><td><button type="button" class="ge-btn-ghost" data-detail-index="' + index + '">' +
          (liquidable ? 'Ver / Liquidar' : 'Ver detalle') + '</button></td></tr>';
      }
      var cancelButton = page.dataset.canCancel === 'true' && transaction.estado === 'PENDIENTE'
        ? '<button type="button" class="ge-btn-ghost ge-btn-ghost--danger" data-cancel-index="' + index + '">Cancelar</button>'
        : '';
      return '<tr>' +
        '<td><span class="ge-operation-id">#' + escapeHtml(transaction.id) + '</span><span class="ge-operation-date">' + escapeHtml(formatDate(transaction.fecha_creacion)) + '</span></td>' +
        '<td class="strong">' + escapeHtml(transaction.cliente.nombre_razon_social) + '</td>' +
        '<td><strong>' + escapeHtml(transaction.tipo === 'COMPRA' ? 'Compra' : 'Venta') + '</strong><br><span class="muted">' + escapeHtml(transaction.moneda_origen.codigo + ' → ' + transaction.moneda_destino.codigo) + '</span></td>' +
        '<td><span class="ge-operation-amount">' + escapeHtml(formatAmount(transaction.monto_origen, transaction.moneda_origen.codigo)) + '</span><span class="ge-operation-amount muted">→ ' + escapeHtml(formatAmount(transaction.monto_destino, transaction.moneda_destino.codigo)) + '</span></td>' +
        '<td>' + statusBadge(transaction.estado) + '</td>' +
        '<td>' + escapeHtml(transaction.metodo_pago && transaction.metodo_pago.nombre || '—') + '</td>' +
        '<td><div class="ge-operation-row-actions"><button type="button" class="ge-btn-ghost" data-detail-index="' + index + '">Ver detalle</button>' + cancelButton + '</div></td>' +
        '</tr>';
    }).join('');
  }

  function cashRecentAmount(value) {
    // El importe del ledger llega como decimal string; no redondearlo con Number.
    var parts = String(value).split('.');
    var integer = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    var fraction = (parts[1] || '').replace(/0+$/, '');
    return integer + (fraction ? ',' + fraction : '');
  }

  function cashRecentMessage(message) {
    historyBody.innerHTML = '<tr><td colspan="7" class="no-data">' + escapeHtml(message) + '</td></tr>';
  }

  function updateCashSelection(data) {
    var select = page.querySelector('[data-cash-period]');
    var periods = data.periodos || [];
    select.innerHTML = '<option value="">' + (periods.length ? 'Seleccionar caja / período' : 'No hay cajas abiertas') + '</option>' +
      periods.map(function (period) {
        return '<option value="' + escapeHtml(period.id) + '">' + escapeHtml(period.caja_codigo + ' · ' + period.caja_nombre + ' / período ' + period.id) + '</option>';
      }).join('');
    select.value = data.periodo_id ? String(data.periodo_id) : '';
    select.disabled = !periods.length;
    page.dataset.cashPeriodId = select.value;
    page.querySelector('[data-cash-history-link]').setAttribute('href', data.history_url);
  }

  function loadCashRecent() {
    var version = ++state.cashRecentVersion;
    var select = page.querySelector('[data-cash-period]');
    var message = page.querySelector('[data-cash-recent-message]');
    var refresh = page.querySelector('[data-reload-history]');
    var selected = select.value || page.dataset.cashPeriodId;
    var url = page.dataset.cashRecentUrl + (selected ? '?periodo_id=' + encodeURIComponent(selected) : '');
    state.transactions = [];
    refresh.disabled = true;
    message.textContent = 'Consultando movimientos de caja…';
    cashRecentMessage('Cargando movimientos…');
    return apiRequest(url, { credentials: 'same-origin' }).then(function (data) {
      if (version !== state.cashRecentVersion) return;
      updateCashSelection(data);
      if (!data.periodo_id) {
        var empty = data.periodos.length ? 'Seleccioná una caja para consultar sus movimientos.' : 'No hay períodos abiertos de cajas habilitadas.';
        message.textContent = empty;
        cashRecentMessage(empty);
        return;
      }
      message.textContent = 'Hasta 5 movimientos del período seleccionado. Consulta de solo lectura.';
      var movements = (data.movimientos || []).slice(0, 5);
      if (!movements.length) { cashRecentMessage('Todavía no hay movimientos registrados en este período.'); return; }
      historyBody.innerHTML = movements.map(function (movement) {
        return '<tr><td><span class="ge-operation-id">#' + escapeHtml(movement.id) + '</span><span class="ge-operation-date">' + escapeHtml(formatDate(movement.fecha_registro)) + '</span></td>' +
          '<td>' + escapeHtml(movement.tipo) + '</td><td>' + escapeHtml(movement.moneda) + '</td><td class="strong">' + escapeHtml(cashRecentAmount(movement.importe)) + '</td>' +
          '<td>' + escapeHtml(movement.metodo) + '</td><td>' + escapeHtml(movement.origen) + '</td><td><span class="ge-status-badge ge-status-badge--success ge-status-badge--sm"><span class="ge-status-dot"></span>' + escapeHtml(movement.estado) + '</span></td></tr>';
      }).join('');
    }).catch(function (error) {
      if (version !== state.cashRecentVersion) return;
      if (error.status === 400 && error.payload && error.payload.periodos) updateCashSelection(error.payload);
      message.textContent = 'Movimientos de caja no disponibles. Actualizá para reintentar.';
      cashRecentMessage('Movimientos de caja no disponibles.');
      notify(errorMessage(error), 'error');
    }).finally(function () {
      if (version === state.cashRecentVersion) refresh.disabled = false;
    });
  }

  function loadHistory() {
    if (page.dataset.presencial === 'true' && page.dataset.cashRecentUrl) return loadCashRecent();
    historyBody.innerHTML = '<tr><td colspan="' + (page.dataset.operativeInbox === 'true' ? 8 : 7) + '" class="no-data">Cargando historial…</td></tr>';
    apiRequest(page.dataset.historyUrl, { credentials: 'same-origin' }).then(function (data) {
      state.transactions = data.transacciones || [];
      renderHistory();
    }).catch(function (error) {
      historyBody.innerHTML = '<tr><td colspan="' + (page.dataset.operativeInbox === 'true' ? 8 : 7) + '" class="no-data">Historial no disponible.</td></tr>';
      notify(errorMessage(error), 'error');
    });
  }

  function detailItem(label, value) {
    return '<div><dt>' + escapeHtml(label) + '</dt><dd>' + escapeHtml(value || '—') + '</dd></div>';
  }

  function renderDetail(transaction) {
    var cancellation = transaction.cancelacion || {};
    var html = '<dl class="ge-transaction-detail">' +
      detailItem('Identificador', '#' + transaction.id) +
      detailItem('Estado', transaction.estado) +
      detailItem('Tipo', transaction.tipo === 'COMPRA' ? 'Compra' : 'Venta') +
      detailItem('Cliente', transaction.cliente.nombre_razon_social) +
      detailItem('Categoría', transaction.cliente.categoria || 'Sin categoría') +
      detailItem('Monto de origen', formatAmount(transaction.monto_origen, transaction.moneda_origen.codigo)) +
      detailItem('Tasa aplicada', formatRate(transaction.tasa_aplicada)) +
      detailItem('Monto convertido', formatAmount(transaction.monto_convertido, transaction.moneda_destino.codigo)) +
      detailItem('Comisión', formatAmount(transaction.importe_comision, transaction.moneda_destino.codigo) + ' (' + formatNumber(transaction.porcentaje_comision) + '%)') +
      detailItem('Monto final', formatAmount(transaction.monto_destino, transaction.moneda_destino.codigo)) +
      detailItem(transaction.tipo === 'VENTA' ? 'Medio de recepción' : 'Método de pago', transaction.metodo_pago.nombre) +
      detailItem('Creada por', transaction.creado_por.username || transaction.creado_por.keycloak_id) +
      detailItem('Fecha de creación', formatDate(transaction.fecha_creacion)) +
      detailItem('Última actualización', formatDate(transaction.fecha_actualizacion));
    if (transaction.liquidacion_efectivo) {
      var cash = transaction.liquidacion_efectivo;
      html += detailItem('Intercambio físico simulado', cash.caja + ' · Período ' + cash.periodo_id) +
        detailItem('Confirmado por', cash.confirmado_por) + detailItem('Fecha del intercambio', formatDate(cash.fecha)) +
        detailItem('Movimientos', 'Ingreso #' + cash.ingreso_id + ' · Egreso #' + cash.egreso_id);
    }

    if (transaction.estado === 'CANCELADA') {
      html += detailItem('Cancelada por', cancellation.cancelado_por_username || cancellation.cancelado_por_keycloak_id) +
        detailItem('Fecha de cancelación', formatDate(cancellation.cancelado_en)) +
        detailItem('Motivo', cancellation.motivo_cancelacion);
    }
    html += '</dl>';
    document.querySelector('[data-transaction-detail]').innerHTML = html;
  }

  function isCurrentDetail(id, version) {
    return state.detailId === id && state.detailVersion === version &&
      document.getElementById('detalle-operacion').classList.contains('is-open');
  }

  function paymentError(message) {
    var actions = document.querySelector('[data-payment-actions]');
    actions.replaceChildren();
    actions.hidden = true;
    document.querySelector('[data-payment-state]').textContent = '';
    document.querySelector('[data-payment-message]').textContent = '';
    document.querySelector('[data-payment-method-change]').hidden = true;
    state.paymentData = null;
    notify(message, 'error');
  }

  function renderPayment(data, transaction) {
    var messages = {
      PAGO_NO_INICIADO: 'Pago no iniciado',
      EN_PROCESO: 'Pago en proceso',
      APROBADO: transaction && transaction.estado === 'PENDIENTE'
        ? 'Pago aprobado. Finalización automática pendiente de recuperación. Recuperar no vuelve a cobrar.' : 'Pago aprobado.',
      RECHAZADO: 'Pago rechazado',
      ERROR: 'No se pudo completar el pago.',
      INDETERMINADO: 'Pago pendiente de verificación.'
    };
    state.paymentData = data;
    renderMethodChange(data, transaction);
    var status = data.estado;
    if (data.codigo === 'PAGO_NO_INICIADO' && data.pago_id === null && status === null) {
      status = 'PAGO_NO_INICIADO';
    }
    var codes = {
      PAGO_NO_INICIADO: 'PAGO_NO_INICIADO', EN_PROCESO: 'EN_PROCESO',
      APROBADO: 'APROBADO', RECHAZADO: 'RECHAZADO',
      ERROR: 'ERROR_SIN_EJECUCION', INDETERMINADO: 'RESULTADO_DESCONOCIDO'
    };
    var known = Object.prototype.hasOwnProperty.call(messages, status) && data.codigo === codes[status];
    document.querySelector('[data-payment-state]').textContent = known ? (status === 'PAGO_NO_INICIADO' ? 'Pago no iniciado' : status) : '';
    document.querySelector('[data-payment-message]').textContent = known
      ? (status === 'APROBADO' && transaction && transaction.estado === 'PENDIENTE'
        ? 'Podés recuperar la finalización sin volver a cobrar.' : '') : '';
    var actions = document.querySelector('[data-payment-actions]');
    actions.replaceChildren();
    actions.hidden = true;
    if (transaction && transaction.version_flujo === 0) {
      document.querySelector('[data-payment-message]').textContent = 'Operación histórica pendiente de revisión. No se iniciarán nuevos cobros.';
      return;
    }
    if (!known || !transaction || transaction.tipo !== 'COMPRA' ||
        transaction.estado !== 'PENDIENTE' || page.dataset.canViewPayment !== 'true') return;
    if (status === 'PAGO_NO_INICIADO' && transaction.metodo_pago &&
        (!transaction.metodo_pago.activo || transaction.metodo_pago.naturaleza !== 'ELECTRONICO')) {
      document.querySelector('[data-payment-message]').textContent = !transaction.metodo_pago.activo
        ? 'El método está inactivo. No se puede iniciar un nuevo pago para esta operación.'
        : transaction.metodo_pago.naturaleza === 'EFECTIVO'
          ? 'El procesamiento en efectivo todavía no está disponible.'
          : 'El método requiere clasificación antes de iniciar un pago electrónico.';
      return;
    }
    var options = {
      PAGO_NO_INICIADO: ['start', 'Iniciar pago'],
      ERROR: ['retry', 'Reintentar pago'],
      INDETERMINADO: ['recover', 'Recuperar estado'],
      EN_PROCESO: ['recover', 'Recuperar estado'],
      APROBADO: transaction.version_flujo === 1 && transaction.canal === 'ONLINE' &&
        transaction.metodo_pago && transaction.metodo_pago.naturaleza === 'ELECTRONICO'
        ? ['recover', 'Recuperar finalización'] : null
    };
    var action = options[status];
    if (!action || (action[0] !== 'recover' && page.dataset.canPay !== 'true')) return;
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'ge-btn-primary';
    button.dataset.paymentAction = action[0];
    button.textContent = action[1];
    button.disabled = Boolean(state.paymentPending[transaction.id] || state.methodChangePending[transaction.id] ||
      state.methodChangeRequests[transaction.id] && action[0] !== 'recover');
    actions.appendChild(button);
    actions.hidden = false;
  }

  function submitPayment(event) {
    var button = event.target.closest('[data-payment-action]');
    if (!button || button.disabled) return;
    var id = state.detailId;
    var version = state.detailVersion;
    if (!isCurrentDetail(id, version) || state.paymentPending[id] || state.methodChangePending[id] ||
        state.methodChangeRequests[id] && button.dataset.paymentAction !== 'recover') return;
    var urls = {
      start: page.dataset.paymentStartUrl,
      retry: page.dataset.paymentRetryUrl,
      recover: page.dataset.paymentRecoverUrl
    };
    if (button.dataset.paymentAction !== 'recover' && page.dataset.canPay !== 'true') return;
    var url = urls[button.dataset.paymentAction];
    if (!url) return;
    state.paymentPending[id] = true;
    ++state.paymentVersion;
    setBusy(button, true, 'Procesando…');
    post(resourceUrl(url, id), {}).then(function (data) {
      if (!isCurrentDetail(id, version)) return;
      if (data.transaccion_id !== id) {
        paymentError('Estado de pago no disponible.');
        return;
      }
      renderPayment(data, state.detailTransaction);
      var notices = {
        APROBADO: [button.dataset.paymentAction === 'recover' ? 'Recuperación realizada correctamente.' : 'Pago aprobado.', 'success'],
        RECHAZADO: ['Pago rechazado.', 'error'],
        EN_PROCESO: ['El pago sigue en proceso. Podés recuperar su estado más tarde.', 'info'],
        INDETERMINADO: ['El pago está pendiente de verificación. Recuperá su estado antes de intentar otra acción.', 'warning'],
        ERROR: ['No se pudo completar el pago. Podés reintentar cuando se resuelva el inconveniente.', 'error']
      };
      if (notices[data.estado]) notify(notices[data.estado][0], notices[data.estado][1]);
      if (data.estado === 'APROBADO') {
        refreshLiquidationDetail(id, version);
        loadHistory();
      } else if (data.estado === 'RECHAZADO' || data.estado === 'ERROR') {
        // El resultado del POST no incluye las capacidades del pago actual.
        // Consultarlas permite elegir otro método sin cerrar el detalle.
        loadPayment(state.detailTransaction, version, true);
        loadPaymentAttempts(state.detailTransaction, version);
      }
    }).catch(function (error) {
      if (!isCurrentDetail(id, version)) return;
      if (error.status === 400 && ['DISPONIBILIDAD_INSUFICIENTE', 'METODO_INACTIVO', 'METODO_NO_ELECTRONICO'].indexOf(error.codigo) !== -1) {
        document.querySelector('[data-payment-message]').textContent = '';
        notify(errorMessage(error, state.detailTransaction), 'error');
        return;
      }
      paymentError('No se pudo confirmar el resultado de la solicitud. Volvé a abrir el detalle para consultar el estado del pago.');
    }).finally(function () {
      delete state.paymentPending[id];
      if (!isCurrentDetail(id, state.detailVersion)) return;
      if (state.detailVersion !== version) {
        loadPayment(state.detailTransaction, state.detailVersion);
        return;
      }
      var currentButton = document.querySelector('[data-payment-actions] [data-payment-action]');
      if (currentButton === button) setBusy(currentButton, false);
      else if (currentButton) currentButton.disabled = false;
      if (state.paymentData) renderMethodChange(state.paymentData, state.detailTransaction);
    });
  }

  function canChangeMethod(data, transaction) {
    return Boolean(data && data.puede_cambiar_metodo === true && transaction &&
      transaction.tipo === 'COMPRA' && transaction.estado === 'PENDIENTE' &&
      transaction.canal === 'ONLINE' && transaction.version_flujo === 1 &&
      page.dataset.canPay === 'true' && page.dataset.canViewPayment === 'true' &&
      (data.codigo === 'PAGO_NO_INICIADO' && data.pago_id === null ||
       data.estado === 'RECHAZADO' || data.estado === 'ERROR' && data.codigo === 'ERROR_SIN_EJECUCION'));
  }

  function renderMethodChange(data, transaction) {
    var section = document.querySelector('[data-payment-method-change]');
    section.hidden = true;
    var optionsVersion = ++state.methodChangeVersion;
    if (!canChangeMethod(data, transaction) || !page.dataset.paymentChangeMethodUrl || !page.dataset.methodsUrl) return;
    var id = transaction.id;
    var version = state.detailVersion;
    var select = document.querySelector('[data-payment-method-options]');
    var button = document.querySelector('[data-payment-method-submit]');
    var request = state.methodChangeRequests[id];
    // Una lectura posterior puede confirmar que el cambio incierto ya se aplicó.
    if (request && Number(data.metodo_pago_id) === request.metodo_pago_id) {
      delete state.methodChangeRequests[id];
      request = null;
    }
    section.hidden = false;
    select.disabled = true;
    button.disabled = true;
    button.textContent = request ? 'Reintentar cambio' : 'Cambiar método';
    select.innerHTML = '<option value="">Consultando métodos…</option>';
    apiRequest(page.dataset.methodsUrl, { credentials: 'same-origin' }).then(function (catalog) {
      if (!isCurrentDetail(id, version) || state.methodChangeVersion !== optionsVersion) return;
      var current = Number(data.metodo_pago_id || transaction.metodo_pago.id);
      var methods = (catalog.metodos_pago || []).filter(function (method) { return Number(method.id) !== current; });
      select.innerHTML = '<option value="">' + (methods.length ? 'Seleccionar método' : 'No hay otros métodos electrónicos activos') + '</option>' + methods.map(function (method) {
        return '<option value="' + escapeHtml(method.id) + '">' + escapeHtml(method.nombre) + '</option>';
      }).join('');
      select.value = request ? String(request.metodo_pago_id) : '';
      select.disabled = Boolean(request || state.methodChangePending[id] || state.paymentPending[id]) || !methods.length;
      button.disabled = Boolean(state.methodChangePending[id] || state.paymentPending[id]) || !select.value;
    }).catch(function (error) {
      if (!isCurrentDetail(id, version) || state.methodChangeVersion !== optionsVersion) return;
      section.hidden = true;
      notify(errorMessage(error), 'error');
    });
  }

  function submitMethodChange(event) {
    var button = event.currentTarget;
    var transaction = state.detailTransaction;
    var data = state.paymentData;
    var id = state.detailId;
    var version = state.detailVersion;
    var select = document.querySelector('[data-payment-method-options]');
    if (button.disabled || !isCurrentDetail(id, version) || !canChangeMethod(data, transaction) ||
        state.paymentPending[id] || state.methodChangePending[id]) return;
    var request = state.methodChangeRequests[id];
    if (!request) {
      var selected = Number(select.value);
      var previous = Number(data.metodo_pago_id || transaction.metodo_pago.id);
      if (!Number.isSafeInteger(selected) || selected <= 0 || selected === previous) return;
      request = { metodo_pago_id: selected, metodo_anterior_id: previous,
        pago_esperado_id: data.pago_id || null, clave_idempotencia: createIdempotencyKey() };
      state.methodChangeRequests[id] = request;
    }
    state.methodChangePending[id] = true;
    select.disabled = true;
    setBusy(button, true, 'Cambiando…');
    var pay = document.querySelector('[data-payment-actions] [data-payment-action]');
    if (pay) pay.disabled = true;
    post(resourceUrl(page.dataset.paymentChangeMethodUrl, id), request).then(function (response) {
      if (response.transaccion_id !== id) throw new Error('No se pudo confirmar el cambio de método.');
      delete state.methodChangeRequests[id];
      if (isCurrentDetail(id, version)) notify('Cambio de método confirmado. Consultá el estado actualizado del pago.', 'success');
      loadHistory();
    }).catch(function (error) {
      // Ante incertidumbre, el próximo clic repite exactamente la misma solicitud.
      if (error.status && error.status < 500) delete state.methodChangeRequests[id];
      if (isCurrentDetail(id, version)) notify(errorMessage(error), 'error');
    }).finally(function () {
      delete state.methodChangePending[id];
      if (isCurrentDetail(id, version)) showDetail(state.detailTransaction);
    });
  }

  function loadPaymentAttempts(transaction, version) {
    var section = document.querySelector('[data-payment-attempts]');
    section.hidden = true;
    if (!page.dataset.paymentAttemptsUrl || transaction.tipo !== 'COMPRA' ||
        transaction.canal !== 'ONLINE' || transaction.version_flujo !== 1 || page.dataset.canViewPayment !== 'true') return;
    apiRequest(resourceUrl(page.dataset.paymentAttemptsUrl, transaction.id), { credentials: 'same-origin' }).then(function (data) {
      if (!isCurrentDetail(transaction.id, version) || data.transaccion_id !== transaction.id) return;
      var attempts = data.intentos || [];
      section.hidden = !attempts.length;
      document.querySelector('[data-payment-attempts-body]').innerHTML = attempts.map(function (attempt) {
        return '<tr><td>' + escapeHtml(attempt.pago_id) + '<span class="ge-operation-date">' + escapeHtml(formatDate(attempt.fecha_creacion)) +
          '</span></td><td>' + escapeHtml(attempt.metodo_pago_nombre) + '</td><td>' + escapeHtml(attempt.estado) +
          (attempt.vigente ? ' · Vigente' : '') + '</td><td>' + escapeHtml(attempt.codigo || '—') + '</td></tr>';
      }).join('');
    }).catch(function (error) {
      if (isCurrentDetail(transaction.id, version)) notify(errorMessage(error), 'error');
    });
  }

  function isCash(transaction) {
    return Boolean(transaction && transaction.metodo_pago && transaction.metodo_pago.naturaleza === 'EFECTIVO');
  }

  function cashPaymentLabel(transaction) {
    return transaction.liquidacion_efectivo ? 'Aprobado' : 'Pendiente';
  }

  function loadPayment(transaction, version, preserveLiquidationMessage) {
    var section = document.querySelector('[data-payment-section]');
    if (isCash(transaction) || transaction.liquidacion_efectivo) {
      section.hidden = false;
      document.querySelector('[data-payment-actions]').replaceChildren();
      document.querySelector('[data-payment-state]').textContent = cashPaymentLabel(transaction);
      document.querySelector('[data-payment-message]').textContent = 'La recepción y entrega físicas se simulan únicamente al confirmar el intercambio. No utiliza Stripe.';
      if (!preserveLiquidationMessage && transaction.tipo === 'COMPRA') loadLiquidation();
      return;
    }
    if (transaction.tipo !== 'COMPRA' || page.dataset.canViewPayment !== 'true') return;
    state.paymentStatus = null;
    if (!preserveLiquidationMessage) document.querySelector('[data-liquidation-section]').hidden = true;
    var paymentVersion = ++state.paymentVersion;
    section.hidden = false;
    document.querySelector('[data-payment-actions]').replaceChildren();
    document.querySelector('[data-payment-actions]').hidden = true;
    document.querySelector('[data-payment-state]').textContent = '';
    document.querySelector('[data-payment-message]').textContent = 'Consultando estado de pago…';
    apiRequest(resourceUrl(page.dataset.paymentUrl, transaction.id), {
      credentials: 'same-origin'
    }).then(function (data) {
      if (!isCurrentDetail(transaction.id, version) || state.paymentVersion !== paymentVersion) return;
      if (data.transaccion_id !== transaction.id) {
        renderPayment({});
        return;
      }
      renderPayment(data, transaction);
      state.paymentStatus = data.estado === 'APROBADO' && data.codigo === 'APROBADO' ? 'APROBADO' : null;
      if (!preserveLiquidationMessage) loadLiquidation();
      else {
        document.querySelector('[data-liquidation-section]').hidden = !canLiquidate();
        liquidationControls();
      }
    }).catch(function () {
      if (!isCurrentDetail(transaction.id, version) || state.paymentVersion !== paymentVersion) return;
      paymentError('No se pudo consultar el estado del pago.');
      if (preserveLiquidationMessage) liquidationControls();
    });
  }

  function showDetail(transaction) {
    state.detailId = transaction.id;
    state.detailTransaction = transaction;
    var version = ++state.detailVersion;
    state.paymentStatus = null;
    state.paymentData = null;
    ++state.methodChangeVersion;
    document.querySelector('[data-payment-method-change]').hidden = true;
    document.querySelector('[data-payment-attempts]').hidden = true;
    ++state.liquidationVersion;
    state.liquidationLoading = false;
    document.querySelector('[data-liquidation-section]').hidden = true;
    renderLiquidationError();
    document.querySelector('[data-payment-section]').hidden = true;
    document.querySelector('[data-payment-state]').textContent = '';
    document.querySelector('[data-payment-message]').textContent = '';
    var container = document.querySelector('[data-transaction-detail]');
    container.innerHTML = '<p class="ge-frontend-note">Cargando detalle…</p>';
    window.GEApp.openModal('detalle-operacion');
    apiRequest(resourceUrl(page.dataset.detailUrl, transaction.id), {
      credentials: 'same-origin'
    }).then(function (data) {
      if (!isCurrentDetail(transaction.id, version)) return;
      if (!data.transaccion || data.transaccion.id !== transaction.id) {
        throw new Error('No se pudo consultar el detalle de la transacción.');
      }
      renderDetail(data.transaccion);
      state.detailTransaction = data.transaccion;
      if (!state.liquidationPending[transaction.id]) delete state.liquidationUncertain[transaction.id];
      loadPayment(data.transaccion, version);
      loadPaymentAttempts(data.transaccion, version);
      if (data.transaccion.tipo === 'VENTA') loadLiquidation();
    }).catch(function (error) {
      if (!isCurrentDetail(transaction.id, version)) return;
      container.innerHTML = '<p class="ge-frontend-note">Detalle no disponible.</p>';
      notify(errorMessage(error), 'error');
    });
  }

  function canLiquidate() {
    var transaction = state.detailTransaction;
    return transaction && transaction.id === state.detailId && transaction.estado === 'PENDIENTE' &&
      transaction.canal === 'PRESENCIAL' && transaction.version_flujo === 1 &&
      page.dataset.canLiquidate === 'true' &&
      (isCash(transaction) || transaction.tipo === 'VENTA' || (transaction.tipo === 'COMPRA' && state.paymentStatus === 'APROBADO'));
  }

  function liquidationControls() {
    var busy = Boolean(state.liquidationPending[state.detailId] || state.liquidationUncertain[state.detailId]);
    var select = document.querySelector('[data-liquidation-period]');
    var cash = isCash(state.detailTransaction);
    var selectedPeriod = state.liquidationPeriods.find(function (period) { return String(period.periodo_id) === select.value; });
    select.disabled = busy || state.liquidationLoading || select.options.length <= 1;
    document.querySelector('[data-liquidation-submit]').disabled = busy || state.liquidationLoading ||
      !canLiquidate() || !select.value || (cash && (!selectedPeriod || !selectedPeriod.disponible));
    if (!state.liquidationPending[state.detailId]) document.querySelector('[data-liquidation-submit]').textContent = cash ? 'Confirmar intercambio en efectivo' : 'Liquidar operación';
    document.querySelector('[data-liquidation-refresh]').disabled = state.liquidationLoading;
  }

  function liquidationMessage(message) {
    document.querySelector('[data-liquidation-message]').textContent = message;
  }

  function renderLiquidationError() {
    var container = document.querySelector('[data-liquidation-error]');
    container.textContent = '';
    container.hidden = true;
  }

  function setLiquidationError(message) {
    if (message) { state.liquidationErrors[state.detailId] = message; notify(message, 'error'); }
    else delete state.liquidationErrors[state.detailId];
    renderLiquidationError();
  }

  function loadLiquidation() {
    var section = document.querySelector('[data-liquidation-section]');
    section.hidden = !canLiquidate();
    renderLiquidationError();
    if (section.hidden) return;
    if (isCash(state.detailTransaction)) {
      var tx = state.detailTransaction;
      document.querySelector('[data-cash-summary]').hidden = false;
      document.querySelector('[data-cash-summary]').textContent = 'Simulación: el cajero recibe ' + formatAmount(tx.monto_origen, tx.moneda_origen.codigo) +
        ' y entrega ' + formatAmount(tx.monto_destino, tx.moneda_destino.codigo) + ' netos a ' + tx.cliente.nombre_razon_social + '.';
    } else document.querySelector('[data-cash-summary]').hidden = true;
    var id = state.detailId;
    var version = state.detailVersion;
    var requestVersion = ++state.liquidationVersion;
    var select = document.querySelector('[data-liquidation-period]');
    select.innerHTML = '<option value="">Seleccioná una Caja/Período</option>';
    state.liquidationLoading = true;
    state.liquidationPeriods = [];
    liquidationMessage('Consultando cajas/períodos abiertos…');
    liquidationControls();
    apiRequest(resourceUrl(page.dataset.liquidationPeriodsUrl, id), { credentials: 'same-origin' }).then(function (data) {
      if (!isCurrentDetail(id, version) || state.liquidationVersion !== requestVersion) return;
      if (data.transaccion_id !== id || !Array.isArray(data.periodos) || data.periodos.some(function (period) {
        return !Number.isSafeInteger(period.periodo_id) || period.periodo_id <= 0 || period.estado !== 'ABIERTO' || !period.caja;
      })) throw new Error('Respuesta de períodos inválida.');
      state.liquidationPeriods = data.periodos;
      data.periodos.forEach(function (period) {
        var option = document.createElement('option');
        option.value = period.periodo_id;
        option.textContent = period.caja.codigo + ' — ' + period.caja.nombre + ' · Período ' + period.periodo_id;
        if (isCash(state.detailTransaction) && period.disponible !== true) {
          option.disabled = true;
          option.textContent += ' · Sin disponibilidad o monedas no configuradas';
        }
        select.appendChild(option);
      });
      liquidationMessage(data.periodos.length ? 'Seleccioná explícitamente una Caja/Período. La disponibilidad de fondos se valida al liquidar.'
        : 'No hay cajas/períodos abiertos disponibles para liquidar.');
    }).catch(function (error) {
      if (!isCurrentDetail(id, version) || state.liquidationVersion !== requestVersion) return;
      setLiquidationError(liquidationError(error));
    }).finally(function () {
      if (!isCurrentDetail(id, version) || state.liquidationVersion !== requestVersion) return;
      state.liquidationLoading = false;
      liquidationControls();
    });
  }

  function liquidationError(error) {
    var messages = {
      SALDO_INSUFICIENTE: errorMessage(error, state.detailTransaction),
      PERIODO_NO_DISPONIBLE: 'El período de caja ya no está disponible. Actualizá el catálogo.',
      PAGO_NO_APROBADO: 'La compra requiere un pago aprobado.',
      OPERACION_NO_PENDIENTE: 'La operación ya no permite liquidación.',
      MONEDA_NO_ADMITIDA: 'El período no admite las monedas de la operación.',
      CONFLICTO_IDEMPOTENCIA: 'No se pudo liquidar por un conflicto de idempotencia.',
      OBLIGACION_CAMBIADA: 'El pago no corresponde a la obligación de la operación.',
      PAGO_INCOMPATIBLE: 'La operación en efectivo tiene un Pago electrónico incompatible.',
      METODO_INACTIVO: 'El método de efectivo está deshabilitado.'
    };
    if (Object.prototype.hasOwnProperty.call(messages, error.codigo)) return messages[error.codigo];
    if ([401, 403, 404].indexOf(error.status) !== -1) return 'No tenés acceso a esta operación o tu sesión ya no es válida.';
    return 'No se pudo confirmar la liquidación. Consultá el estado de la operación antes de volver a intentar.';
  }

  function refreshLiquidationDetail(id, version, message) {
    return apiRequest(resourceUrl(page.dataset.detailUrl, id), { credentials: 'same-origin' }).then(function (data) {
      if (!isCurrentDetail(id, version)) return;
      if (!data.transaccion || data.transaccion.id !== id) throw new Error('Detalle inválido.');
      state.detailTransaction = data.transaccion;
      renderDetail(data.transaccion);
      delete state.liquidationUncertain[id];
      document.querySelector('[data-liquidation-section]').hidden = !canLiquidate();
      loadPayment(data.transaccion, version, true);
      renderLiquidationError();
      liquidationMessage('');
    }).catch(function () {
      if (!isCurrentDetail(id, version)) return;
      state.liquidationUncertain[id] = true;
      liquidationMessage('');
      notify('No se pudo verificar el estado. Actualizá el detalle antes de volver a intentar.', 'warning');
    });
  }

  function submitLiquidation() {
    var id = state.detailId;
    var version = state.detailVersion;
    var select = document.querySelector('[data-liquidation-period]');
    var periodId = Number(select.value);
    if (!isCurrentDetail(id, version) || !canLiquidate() || state.liquidationLoading ||
        state.liquidationPending[id] || state.liquidationUncertain[id] ||
        !Number.isSafeInteger(periodId) || periodId <= 0 || select.disabled ||
        document.querySelector('[data-liquidation-submit]').disabled) return;
    state.liquidationPending[id] = true;
    state.liquidationUncertain[id] = true;
    ++state.liquidationVersion;
    liquidationControls();
    setLiquidationError('');
    liquidationMessage('Liquidando operación…');
    post(resourceUrl(page.dataset.liquidationUrl, id), { periodo_id: periodId }).then(function (data) {
      if (!isCurrentDetail(id, version)) return;
      if (data.transaccion_id !== id || data.estado !== 'COMPLETADA' || typeof data.repetida !== 'boolean') {
        throw new Error('Respuesta de liquidación inválida.');
      }
      setLiquidationError('');
      state.detailTransaction = Object.assign({}, state.detailTransaction, { estado: data.estado });
      document.querySelector('[data-liquidation-section]').hidden = true;
      document.querySelector('[data-payment-actions]').replaceChildren();
      if (state.paymentStatus === 'APROBADO') renderPayment({ estado: 'APROBADO', codigo: 'APROBADO' }, state.detailTransaction);
      renderDetail(state.detailTransaction);
      notify('Transacción #' + id + ' completada.', 'success');
      loadHistory();
      return refreshLiquidationDetail(id, version, 'Operación completada.');
    }).catch(function (error) {
      if (!isCurrentDetail(id, version)) return;
      state.liquidationUncertain[id] = true;
      var message = liquidationError(error);
      setLiquidationError(message);
      liquidationMessage('Consultando el estado de la operación…');
      loadHistory();
      return refreshLiquidationDetail(id, version, message);
    }).finally(function () {
      delete state.liquidationPending[id];
      if (isCurrentDetail(id, version)) liquidationControls();
    });
  }

  function openCancellation(transaction) {
    state.cancelTarget = transaction;
    document.querySelector('[data-cancel-summary]').textContent =
      'Vas a cancelar la transacción #' + transaction.id + ' de ' +
      formatAmount(transaction.monto_origen, transaction.moneda_origen.codigo) + '. Esta acción conservará su trazabilidad.';
    window.GEApp.openModal('cancelar-operacion');
  }

  function confirmCancellation(event) {
    var button = event.currentTarget;
    if (!state.cancelTarget || button.disabled) return;
    setBusy(button, true, 'Cancelando…');
    post(page.dataset.cancelUrl, { transaccion_id: state.cancelTarget.id }).then(function (data) {
      window.GEApp.closeModal('cancelar-operacion');
      state.cancelTarget = null;
      notify(data.mensaje || 'La transacción fue cancelada correctamente.', 'success');
      loadHistory();
    }).catch(function (error) {
      notify(errorMessage(error), 'error');
    }).finally(function () {
      setBusy(button, false);
    });
  }

  if (form) {
    if (page.dataset.presencial === 'true') {
      var searchButton = document.querySelector('[data-client-search-button]');
      var searchVersion = 0;
      searchButton.addEventListener('click', function () {
        var version = ++searchVersion;
        var query = document.querySelector('[data-client-search]').value.trim();
        if (query.length < 2) { document.querySelector('[data-client-search-message]').textContent = 'Ingresá al menos 2 caracteres.'; return; }
        setBusy(searchButton, true, 'Buscando…');
        apiRequest(page.dataset.clientSearchUrl + '?q=' + encodeURIComponent(query), { credentials: 'same-origin' }).then(function (data) {
          if (version !== searchVersion) return;
          form.elements.cliente_id.innerHTML = '<option value="">Seleccionar cliente</option>' + data.clientes.map(function (client) {
            return '<option value="' + client.id + '">' + escapeHtml(client.nombre_razon_social) + ' · #' + client.id + '</option>';
          }).join('');
          invalidatePreview();
          document.querySelector('[data-client-search-message]').textContent = data.clientes.length ? 'Seleccioná el cliente titular.' : 'No se encontraron clientes habilitados.';
        }).catch(function (error) { document.querySelector('[data-client-search-message]').textContent = ''; notify(errorMessage(error), 'error'); })
          .finally(function () { setBusy(searchButton, false); });
      });
    }
    form.querySelectorAll('[data-operation-type]').forEach(function (button) {
      button.addEventListener('click', function () {
        form.querySelectorAll('[data-operation-type]').forEach(function (item) {
          var active = item === button;
          item.classList.toggle('is-active', active);
          item.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        form.elements.tipo.value = button.dataset.operationType;
        updateAmountLimits();
        clearFieldErrors();
        document.querySelector('[data-new-method-label]').textContent = button.dataset.operationType === 'VENTA' ? 'Medio de recepción' : 'Método de pago';
        invalidatePreview();
        clearFeedback();
      });
    });

    function formChanged(event) {
      clearFieldErrors();
      updateAmountLimits();
      if (event.target === form.elements.metodo_pago_id) syncMethodSelection(event.target);
      else invalidatePreview();
    }
    form.addEventListener('input', formChanged);
    form.addEventListener('change', formChanged);
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearFeedback();
      // FormData omite los selects deshabilitados: nunca enviar durante la carga.
      if (state.methodsLoading || state.confirmationPending || (form.elements.metodo_pago_id && form.elements.metodo_pago_id.disabled)) return;
      updateAmountLimits();
      if (!validateAmount()) return;
      if (!form.reportValidity()) return;
      var payload = formPayload();
      if (payload.moneda_origen_id === payload.moneda_destino_id) {
        fieldErrors({ fields: { moneda_destino_id: ['Seleccioná monedas de origen y destino diferentes.'] } });
        return;
      }
      var button = form.querySelector('[data-preview-button]');
      setBusy(button, true, 'Consultando…');
      post(page.dataset.previewUrl, payload).then(function (preview) {
        state.preview = preview;
        state.payload = payload;
        state.idempotencyKey = null;
        state.confirmationPayload = null;
        renderPreview(preview);
      }).catch(function (error) {
        invalidatePreview();
        if (!fieldErrors(error)) notify(errorMessage(error), 'error');
      }).finally(function () {
        setBusy(button, false);
      });
    });

    page.querySelector('[data-open-confirm]').addEventListener('click', openConfirmation);
    updateAmountLimits();
    loadPaymentMethods();
  }

  historyBody.addEventListener('click', function (event) {
    if (page.dataset.presencial === 'true' && page.dataset.cashRecentUrl) return;
    var detailButton = event.target.closest('[data-detail-index]');
    var cancelButton = event.target.closest('[data-cancel-index]');
    if (detailButton) showDetail(state.transactions[Number(detailButton.dataset.detailIndex)]);
    if (cancelButton) openCancellation(state.transactions[Number(cancelButton.dataset.cancelIndex)]);
  });

  page.querySelector('[data-reload-history]').addEventListener('click', loadHistory);
  if (page.dataset.presencial === 'true' && page.dataset.cashRecentUrl) {
    page.querySelector('[data-cash-period]').addEventListener('change', function () {
      page.dataset.cashPeriodId = this.value;
      loadHistory();
    });
  }
  document.querySelector('[data-payment-actions]').addEventListener('click', submitPayment);
  document.querySelector('[data-payment-method-submit]').addEventListener('click', submitMethodChange);
  document.querySelector('[data-payment-method-options]').addEventListener('change', function () {
    if (state.methodChangePending[state.detailId]) return;
    delete state.methodChangeRequests[state.detailId];
    document.querySelector('[data-payment-method-submit]').disabled = !this.value || Boolean(state.paymentPending[state.detailId]);
  });
  var reviewMethod = document.querySelector('[data-confirm-method]');
  if (reviewMethod) reviewMethod.addEventListener('change', function () { syncMethodSelection(this); });
  document.querySelector('[data-liquidation-period]').addEventListener('change', liquidationControls);
  document.querySelector('[data-liquidation-submit]').addEventListener('click', submitLiquidation);
  document.querySelector('[data-liquidation-refresh]').addEventListener('click', function () {
    if (state.liquidationPending[state.detailId]) return;
    if (state.liquidationUncertain[state.detailId]) showDetail(state.detailTransaction);
    else loadLiquidation();
  });
  document.querySelector('[data-confirm-operation]').addEventListener('click', confirmOperation);
  document.querySelector('[data-confirm-cancel]').addEventListener('click', confirmCancellation);
  loadHistory();
})();
