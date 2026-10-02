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
    cancelTarget: null
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
        if (authError) throw authError;
        if (!response.ok) {
          var error = new Error(responseMessage(data, 'No se pudo completar la solicitud.'));
          error.status = response.status;
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
      showFeedback('Transacción #' + data.transaccion.id + ' completada correctamente.' + repeated, 'success');
      window.GEApp.toast('Operación completada correctamente.', 'success');
      invalidatePreview();
      loadHistory();
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

  function showDetail(transaction) {
    var container = document.querySelector('[data-transaction-detail]');
    container.innerHTML = '<p class="ge-frontend-note">Cargando detalle…</p>';
    window.GEApp.openModal('detalle-operacion');
    apiRequest(resourceUrl(page.dataset.detailUrl, transaction.id), {
      credentials: 'same-origin'
    }).then(function (data) {
      renderDetail(data.transaccion);
    }).catch(function (error) {
      container.innerHTML = '<p class="ge-operation-feedback is-error">' +
        escapeHtml(error.message) + '</p>';
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
  document.querySelector('[data-confirm-operation]').addEventListener('click', confirmOperation);
  document.querySelector('[data-confirm-cancel]').addEventListener('click', confirmCancellation);
  loadHistory();
})();
