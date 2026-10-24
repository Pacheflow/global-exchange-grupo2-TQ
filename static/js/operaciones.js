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

  function showFeedback(message, type) {
    feedback.hidden = false;
    feedback.className = 'ge-operation-feedback is-' + type;
    feedback.textContent = message;
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
      document.querySelector('[data-confirm-message]').textContent = [aviso, !methods.length ? 'No hay métodos de pago habilitados disponibles.' : ''].filter(Boolean).join(' ');
      if (initial) document.querySelector('[data-new-method-message]').textContent = document.querySelector('[data-confirm-message]').textContent;
    }).catch(function (error) {
      if (state.methodsVersion !== version) return;
      state.methodsLoading = false;
      document.querySelector('[data-confirm-message]').textContent = [aviso, error.message].filter(Boolean).join(' ');
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
        ? ' registrada y pendiente de liquidación; la disponibilidad futura no está garantizada.'
        : ' registrada. Estado: ' + data.transaccion.estado + '.';
      showFeedback('Transacción #' + data.transaccion.id + statusMessage + repeated, 'success');
      window.GEApp.toast('Operación' + statusMessage, 'success');
      invalidatePreview();
      loadHistory();
      showDetail(data.transaccion);
    }).catch(function (error) {
      if (error.status === 400 && error.codigo === 'METODO_NO_DISPONIBLE') {
        recargarMetodos = error.message;
        state.confirmationPayload = null;
        state.selectedMethod = '';
      }
      if (error.codigo === 'DISPONIBILIDAD_INSUFICIENTE') window.GEApp.closeModal('confirmar-operacion');
      showFeedback(error.message, 'error');
      window.GEApp.toast(error.message, 'error');
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
      historyBody.innerHTML = '<tr><td colspan="' + (page.dataset.operativeInbox === 'true' ? 8 : 6) + '" class="no-data">Todavía no hay transacciones disponibles.</td></tr>';
      return;
    }

    historyBody.innerHTML = state.transactions.map(function (transaction, index) {
      if (page.dataset.operativeInbox === 'true') {
        var liquidable = transaction.estado === 'PENDIENTE' &&
          (transaction.tipo === 'VENTA' || (transaction.tipo === 'COMPRA' && transaction.pago_estado === 'APROBADO'));
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
        '<td><div class="ge-operation-row-actions"><button type="button" class="ge-btn-ghost" data-detail-index="' + index + '">Ver detalle</button>' + cancelButton + '</div></td>' +
        '</tr>';
    }).join('');
  }

  function loadHistory() {
    historyBody.innerHTML = '<tr><td colspan="' + (page.dataset.operativeInbox === 'true' ? 8 : 6) + '" class="no-data">Cargando historial…</td></tr>';
    apiRequest(page.dataset.historyUrl, { credentials: 'same-origin' }).then(function (data) {
      state.transactions = data.transacciones || [];
      renderHistory();
    }).catch(function (error) {
      historyBody.innerHTML = '<tr><td colspan="' + (page.dataset.operativeInbox === 'true' ? 8 : 6) + '" class="no-data">' + escapeHtml(error.message) + '</td></tr>';
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
    document.querySelector('[data-payment-message]').textContent = message;
  }

  function renderPayment(data, transaction) {
    var messages = {
      PAGO_NO_INICIADO: 'Pago no iniciado',
      EN_PROCESO: 'Pago en proceso',
      APROBADO: transaction && transaction.estado === 'PENDIENTE'
        ? 'Pago aprobado. La operación está pendiente de liquidación.' : 'Pago aprobado.',
      RECHAZADO: 'Pago rechazado',
      ERROR: 'No se pudo completar el pago.',
      INDETERMINADO: 'Pago pendiente de verificación.'
    };
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
      ? (status === 'PAGO_NO_INICIADO' ? '' : messages[status]) : 'Estado de pago no disponible.';
    var actions = document.querySelector('[data-payment-actions]');
    actions.replaceChildren();
    actions.hidden = true;
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
      EN_PROCESO: ['recover', 'Recuperar estado']
    };
    var action = options[status];
    if (!action || (action[0] !== 'recover' && page.dataset.canPay !== 'true')) return;
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'ge-btn-primary';
    button.dataset.paymentAction = action[0];
    button.textContent = action[1];
    button.disabled = Boolean(state.paymentPending[transaction.id]);
    actions.appendChild(button);
    actions.hidden = false;
  }

  function submitPayment(event) {
    var button = event.target.closest('[data-payment-action]');
    if (!button || button.disabled) return;
    var id = state.detailId;
    var version = state.detailVersion;
    if (!isCurrentDetail(id, version) || state.paymentPending[id]) return;
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
      if (data.estado === 'APROBADO') loadPayment(state.detailTransaction, version);
    }).catch(function (error) {
      if (!isCurrentDetail(id, version)) return;
      if (error.status === 400 && ['DISPONIBILIDAD_INSUFICIENTE', 'METODO_INACTIVO', 'METODO_NO_ELECTRONICO'].indexOf(error.codigo) !== -1) {
        document.querySelector('[data-payment-message]').textContent = error.message;
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
      if (data.transaccion.tipo === 'VENTA') loadLiquidation();
    }).catch(function (error) {
      if (!isCurrentDetail(transaction.id, version)) return;
      container.innerHTML = '<p class="ge-operation-feedback is-error">' +
        escapeHtml(error.message) + '</p>';
    });
  }

  function canLiquidate() {
    var transaction = state.detailTransaction;
    return transaction && transaction.id === state.detailId && transaction.estado === 'PENDIENTE' &&
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
    container.textContent = state.liquidationErrors[state.detailId] || '';
    container.hidden = !container.textContent;
  }

  function setLiquidationError(message) {
    if (message) state.liquidationErrors[state.detailId] = message;
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
      SALDO_INSUFICIENTE: 'Saldo insuficiente para liquidar la operación.',
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
      liquidationMessage(data.transaccion.estado === 'COMPLETADA' ? 'Operación completada.' : 'Estado de la operación actualizado.');
    }).catch(function () {
      if (!isCurrentDetail(id, version)) return;
      state.liquidationUncertain[id] = true;
      liquidationMessage('No se pudo verificar el estado. Actualizá el detalle antes de volver a intentar.');
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
      showFeedback('Transacción #' + id + ' completada.', 'success');
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
      showFeedback(data.mensaje || 'La transacción fue cancelada correctamente.', 'success');
      window.GEApp.toast('Transacción cancelada correctamente.', 'success');
      loadHistory();
    }).catch(function (error) {
      showFeedback(error.message, 'error');
      window.GEApp.toast(error.message, 'error');
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
        }).catch(function (error) { document.querySelector('[data-client-search-message]').textContent = error.message; })
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
        document.querySelector('[data-new-method-label]').textContent = button.dataset.operationType === 'VENTA' ? 'Medio de recepción' : 'Método de pago';
        invalidatePreview();
        clearFeedback();
      });
    });

    function formChanged(event) {
      if (event.target === form.elements.metodo_pago_id) syncMethodSelection(event.target);
      else invalidatePreview();
    }
    form.addEventListener('input', formChanged);
    form.addEventListener('change', formChanged);
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearFeedback();
      if (!form.reportValidity()) return;
      var payload = formPayload();
      if (payload.moneda_origen_id === payload.moneda_destino_id) {
        showFeedback('Seleccioná monedas de origen y destino diferentes.', 'error');
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
        showFeedback(error.message, 'error');
        window.GEApp.toast(error.message, 'error');
      }).finally(function () {
        setBusy(button, false);
      });
    });

    page.querySelector('[data-open-confirm]').addEventListener('click', openConfirmation);
    loadPaymentMethods();
  }

  historyBody.addEventListener('click', function (event) {
    var detailButton = event.target.closest('[data-detail-index]');
    var cancelButton = event.target.closest('[data-cancel-index]');
    if (detailButton) showDetail(state.transactions[Number(detailButton.dataset.detailIndex)]);
    if (cancelButton) openCancellation(state.transactions[Number(cancelButton.dataset.cancelIndex)]);
  });

  page.querySelector('[data-reload-history]').addEventListener('click', loadHistory);
  document.querySelector('[data-payment-actions]').addEventListener('click', submitPayment);
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
