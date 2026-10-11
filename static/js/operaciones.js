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
    paymentStatus: null,
    liquidationVersion: 0,
    liquidationLoading: false,
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

  function loadPaymentMethods() {
    if (!form || !page.dataset.methodsUrl) return;
    var select = form.elements.metodo_pago_id;
    apiRequest(page.dataset.methodsUrl, { credentials: 'same-origin' }).then(function (data) {
      var preferred = data.metodo_pago_preferido && data.metodo_pago_preferido.id;
      select.innerHTML = '<option value="">Seleccionar método</option>' +
        (data.metodos_pago || []).map(function (method) {
          var selected = method.id === preferred ? ' selected' : '';
          var suffix = method.id === preferred ? ' · Preferido' : '';
          return '<option value="' + escapeHtml(method.id) + '"' + selected + '>' +
            escapeHtml(method.nombre + suffix) + '</option>';
        }).join('');
    }).catch(function (error) {
      showFeedback(error.message, 'error');
    });
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
    setField('metodo', preview.metodo_pago.nombre);
    previewCard.hidden = false;
    previewCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function createIdempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'web-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }

  function openConfirmation() {
    if (!state.preview || !state.payload) return;
    // La misma clave se conserva si el usuario reintenta esta confirmación.
    if (!state.idempotencyKey) state.idempotencyKey = createIdempotencyKey();
    var summary = document.querySelector('[data-confirm-summary]');
    summary.textContent = (state.preview.tipo === 'COMPRA' ? 'Compra' : 'Venta') + ': ' +
      formatAmount(state.preview.monto_origen, state.preview.moneda_origen.codigo) + ' por ' +
      formatAmount(state.preview.monto_destino, state.preview.moneda_destino.codigo) + '.';
    window.GEApp.openModal('confirmar-operacion');
  }

  function confirmOperation(event) {
    var button = event.currentTarget;
    if (!state.preview || !state.payload || button.disabled) return;
    if (!state.idempotencyKey) state.idempotencyKey = createIdempotencyKey();

    var payload = Object.assign({}, state.payload, {
      clave_idempotencia: state.idempotencyKey,
      version_preview: state.preview.tasa_comercial.version,
      tasa_preview: state.preview.tasa,
      categoria_preview_id: state.preview.categoria_preview_id,
      porcentaje_comision_preview: state.preview.porcentaje_comision
    });

    setBusy(button, true, 'Confirmando…');
    post(page.dataset.createUrl, payload).then(function (data) {
      window.GEApp.closeModal('confirmar-operacion');
      var repeated = data.repetida ? ' La solicitud ya había sido procesada.' : '';
      var statusMessage = data.transaccion.estado === 'PENDIENTE'
        ? ' registrada y pendiente de procesamiento.'
        : ' registrada. Estado: ' + data.transaccion.estado + '.';
      showFeedback('Transacción #' + data.transaccion.id + statusMessage + repeated, 'success');
      window.GEApp.toast('Operación' + statusMessage, 'success');
      invalidatePreview();
      loadHistory();
      if (data.transaccion.tipo === 'COMPRA') showDetail(data.transaccion);
    }).catch(function (error) {
      showFeedback(error.message, 'error');
      window.GEApp.toast(error.message, 'error');
    }).finally(function () {
      setBusy(button, false);
    });
  }

  function statusBadge(status) {
    var modifier = status === 'COMPLETADA' ? 'success' : status === 'PENDIENTE' ? 'warning' : 'danger';
    return '<span class="ge-status-badge ge-status-badge--' + modifier + ' ge-status-badge--sm"><span class="ge-status-dot"></span>' + escapeHtml(status) + '</span>';
  }

  function renderHistory() {
    if (!state.transactions.length) {
      historyBody.innerHTML = '<tr><td colspan="6" class="no-data">Todavía no hay transacciones disponibles.</td></tr>';
      return;
    }

    historyBody.innerHTML = state.transactions.map(function (transaction, index) {
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
    historyBody.innerHTML = '<tr><td colspan="6" class="no-data">Cargando historial…</td></tr>';
    apiRequest(page.dataset.historyUrl, { credentials: 'same-origin' }).then(function (data) {
      state.transactions = data.transacciones || [];
      renderHistory();
    }).catch(function (error) {
      historyBody.innerHTML = '<tr><td colspan="6" class="no-data">' + escapeHtml(error.message) + '</td></tr>';
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
      detailItem('Método de pago', transaction.metodo_pago.nombre) +
      detailItem('Creada por', transaction.creado_por.username || transaction.creado_por.keycloak_id) +
      detailItem('Fecha de creación', formatDate(transaction.fecha_creacion)) +
      detailItem('Última actualización', formatDate(transaction.fecha_actualizacion));

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
    document.querySelector('[data-payment-state]').textContent = known ? status : '';
    document.querySelector('[data-payment-message]').textContent = known
      ? messages[status] : 'Estado de pago no disponible.';
    var actions = document.querySelector('[data-payment-actions]');
    actions.replaceChildren();
    actions.hidden = true;
    if (!known || !transaction || transaction.tipo !== 'COMPRA' ||
        transaction.estado !== 'PENDIENTE' || page.dataset.canViewPayment !== 'true') return;
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
    }).catch(function () {
      if (!isCurrentDetail(id, version)) return;
      paymentError('No se pudo confirmar el resultado de la solicitud. Volvé a abrir el detalle para consultar el estado del pago.');
    }).finally(function () {
      delete state.paymentPending[id];
      if (!isCurrentDetail(id, state.detailVersion)) return;
      if (state.detailVersion !== version) {
        loadPayment(state.detailTransaction, state.detailVersion);
        return;
      }
      var currentButton = document.querySelector('[data-payment-actions] [data-payment-action]');
      if (currentButton) currentButton.disabled = false;
    });
  }

  function loadPayment(transaction, version, preserveLiquidationMessage) {
    var section = document.querySelector('[data-payment-section]');
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
      (transaction.tipo === 'VENTA' || (transaction.tipo === 'COMPRA' && state.paymentStatus === 'APROBADO'));
  }

  function liquidationControls() {
    var busy = Boolean(state.liquidationPending[state.detailId] || state.liquidationUncertain[state.detailId]);
    var select = document.querySelector('[data-liquidation-period]');
    select.disabled = busy || state.liquidationLoading || select.options.length <= 1;
    document.querySelector('[data-liquidation-submit]').disabled = busy || state.liquidationLoading ||
      !canLiquidate() || !select.value;
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
    var id = state.detailId;
    var version = state.detailVersion;
    var requestVersion = ++state.liquidationVersion;
    var select = document.querySelector('[data-liquidation-period]');
    select.innerHTML = '<option value="">Seleccioná una Caja/Período</option>';
    state.liquidationLoading = true;
    liquidationMessage('Consultando cajas/períodos abiertos…');
    liquidationControls();
    apiRequest(resourceUrl(page.dataset.liquidationPeriodsUrl, id), { credentials: 'same-origin' }).then(function (data) {
      if (!isCurrentDetail(id, version) || state.liquidationVersion !== requestVersion) return;
      if (data.transaccion_id !== id || !Array.isArray(data.periodos) || data.periodos.some(function (period) {
        return !Number.isSafeInteger(period.periodo_id) || period.periodo_id <= 0 || period.estado !== 'ABIERTO' || !period.caja;
      })) throw new Error('Respuesta de períodos inválida.');
      data.periodos.forEach(function (period) {
        var option = document.createElement('option');
        option.value = period.periodo_id;
        option.textContent = period.caja.codigo + ' — ' + period.caja.nombre + ' · Período ' + period.periodo_id;
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
      OBLIGACION_CAMBIADA: 'El pago no corresponde a la obligación de la operación.'
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
        !Number.isSafeInteger(periodId) || periodId <= 0 || select.disabled) return;
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
    form.querySelectorAll('[data-operation-type]').forEach(function (button) {
      button.addEventListener('click', function () {
        form.querySelectorAll('[data-operation-type]').forEach(function (item) {
          var active = item === button;
          item.classList.toggle('is-active', active);
          item.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        form.elements.tipo.value = button.dataset.operationType;
        invalidatePreview();
        clearFeedback();
      });
    });

    form.addEventListener('input', invalidatePreview);
    form.addEventListener('change', invalidatePreview);
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
