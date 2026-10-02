(function () {
  'use strict';

  function esc(value) {
    var node = document.createElement('span');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML;
  }

  function number(value) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed.toLocaleString('es-PY', { maximumFractionDigits: 10 }) : '—';
  }

  function rateNumber(value) {
    return window.GEApp && window.GEApp.formatRate ? window.GEApp.formatRate(value) : number(value);
  }

  function localDate(value) {
    var parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('es-PY');
  }

  function request(url, options, acceptState) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers.Accept = 'application/json';
    return fetch(url, options).catch(function () {
      throw new Error('No fue posible conectar con el servicio.');
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok && !(acceptState && data.estado)) {
          var details = data.detalles && Object.keys(data.detalles).map(function (key) {
            var value = data.detalles[key];
            return Array.isArray(value) ? value.join(' ') : String(value);
          }).join(' ');
          throw new Error(details || data.error || data.mensaje || 'No fue posible consultar el servicio.');
        }
        return data;
      });
    });
  }

  function statusLabel(data, rate) {
    if (rate && rate.desactualizada) return 'Respaldo';
    return { actualizado: 'Vigente', desactualizado: 'Respaldo', indisponible: 'No disponible', vacio: 'Sin datos' }[data.estado] || 'Sin datos';
  }

  function initMarketBoard(landing, data) {
    var board = landing.querySelector('[data-market-board]');
    var rates = data.tasas_comerciales || [];

    function byCode(code) {
      return rates.find(function (rate) {
        return rate.moneda_origen === code || rate.moneda_destino === code;
      });
    }

    function render(rate) {
      board.querySelector('[data-market-status]').textContent = rate ? 'Vigente' : 'Sin datos';
      if (!rate) {
        board.querySelector('[data-market-primary]').textContent = '—';
        board.querySelector('[data-market-buy]').textContent = '—';
        board.querySelector('[data-market-sell]').textContent = '—';
        board.querySelector('[data-market-change]').textContent = 'Sin datos';
        return;
      }
      board.querySelector('[data-market-pair]').textContent = rate.par;
      board.querySelector('[data-market-subtitle]').textContent = rate.moneda_origen + ' / ' + rate.moneda_destino;
      board.querySelector('[data-market-primary]').textContent = rateNumber(rate.compra);
      board.querySelector('[data-market-buy]').textContent = rateNumber(rate.compra);
      board.querySelector('[data-market-sell]').textContent = rateNumber(rate.venta);
      board.querySelector('[data-market-change]').textContent = 'Vigente';
      board.querySelector('[data-market-chart-pair]').textContent = rate.par;
      board.querySelector('[data-market-updated]').textContent = 'Actualizado · ' + localDate(rate.fecha_hora);
    }

    board.querySelectorAll('[data-market-code]').forEach(function (button) {
      var rate = byCode(button.dataset.marketCode);
      button.querySelector('small').textContent = rate ? rate.par : button.dataset.marketCode;
      button.querySelector('[data-market-quote]').textContent = rate ? rateNumber(rate.compra) : '—';
      button.querySelector('[data-market-option-state]').textContent = rate ? 'Vigente' : 'Sin datos';
      button.addEventListener('click', function () { render(rate); });
    });
    board.querySelectorAll('[data-market-stage]').forEach(function (stage, index) {
      window.setTimeout(function () { stage.classList.add('is-visible'); }, [260, 560, 800, 1000][index]);
    });
    render(byCode('USD') || rates[0]);
  }

  function renderRates(landing, data) {
    var rates = data.tasas_comerciales || [];
    var body = landing.querySelector('[data-public-rates-body]');
    body.innerHTML = rates.length ? rates.map(function (rate) {
      return '<tr><td><strong>' + esc(rate.par) + '</strong><small>' + esc(rate.moneda_origen + ' / ' + rate.moneda_destino) + '</small></td>' +
        '<td><span class="ge-animated-price">' + rateNumber(rate.compra) + '</span></td>' +
        '<td><span class="ge-animated-price">' + rateNumber(rate.venta) + '</span></td>' +
        '<td><span>Vigente</span></td>' +
        '<td><small>' + esc(localDate(rate.fecha_hora)) + '</small></td></tr>';
    }).join('') : '<tr><td colspan="5">No hay cotizaciones comerciales vigentes.</td></tr>';
    landing.querySelector('[data-rates-status]').textContent = rates.length
      ? 'Cotizaciones comerciales vigentes'
      : 'Sin cotizaciones comerciales disponibles';
    initMarketBoard(landing, data);
  }

  function renderCurrencies(landing, currencies) {
    var list = landing.querySelector('.frontend-currency-list');
    list.innerHTML = currencies.map(function (currency) {
      return '<article class="ge-frontend-card"><span class="material-symbols landing-currency-icon">paid</span><strong>' + esc(currency.codigo) + '</strong><small>' + esc(currency.nombre) + '</small></article>';
    }).join('') + '<article class="ge-frontend-card future"><span class="material-symbols landing-currency-icon">add</span><strong>Próximamente</strong><small>Más monedas</small></article>';
  }

  function initConverter(landing, currencies) {
    var root = landing.querySelector('[data-public-converter]');
    var amount = root.querySelector('#ge-converter-amount');
    var from = root.querySelector('[data-converter-from]');
    var to = root.querySelector('[data-converter-to]');
    var output = root.querySelector('[data-converter-output]');
    var rateOutput = root.querySelector('[data-converter-rate]');
    var rateType = root.querySelector('[data-converter-type]');
    var updated = root.querySelector('[data-converter-updated]');
    var error = root.querySelector('[data-converter-error]');
    var timer;

    function resetResult() {
      output.textContent = '—';
      rateOutput.textContent = '—';
      rateType.textContent = '—';
      updated.textContent = '—';
    }

    function validResult(result) {
      return result &&
        typeof result.moneda_origen === 'string' && result.moneda_origen &&
        typeof result.moneda_destino === 'string' && result.moneda_destino &&
        Number.isFinite(Number(result.resultado)) &&
        Number.isFinite(Number(result.tasa)) &&
        typeof result.tipo_tasa === 'string' && result.tipo_tasa &&
        !Number.isNaN(new Date(result.fecha_hora).getTime());
    }

    var options = currencies.map(function (currency) { return '<option value="' + currency.id + '" data-code="' + esc(currency.codigo) + '">' + esc(currency.codigo) + '</option>'; }).join('');
    from.innerHTML = options || '<option value="">Sin monedas</option>';
    to.innerHTML = options || '<option value="">Sin monedas</option>';
    var usd = currencies.find(function (currency) { return currency.codigo === 'USD'; });
    var pyg = currencies.find(function (currency) { return currency.codigo === 'PYG'; });
    if (pyg) from.value = String(pyg.id);
    if (usd) to.value = String(usd.id);

    function showError(message) { error.textContent = message; error.hidden = false; resetResult(); }
    function simulate() {
      error.hidden = true;
      error.textContent = '';
      var raw = amount.value.trim().replace(',', '.');
      var value = Number(raw);
      if (!raw) { resetResult(); return; }
      if (!Number.isFinite(value) || value <= 0) return showError('El monto debe ser mayor que cero.');
      if (!from.value || !to.value || from.value === to.value) return showError('Elegí monedas diferentes.');
      output.textContent = 'Calculando…';
      var token = document.querySelector('[name=csrfmiddlewaretoken]');
      request(landing.dataset.simulateUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token ? token.value : '' }, body: JSON.stringify({ moneda_origen_id: Number(from.value), moneda_destino_id: Number(to.value), monto: raw }) }).then(function (result) {
        if (!validResult(result)) throw new Error('El servicio devolvió una respuesta de simulación inválida.');
        output.textContent = number(result.resultado);
        rateOutput.textContent = '1 ' + result.moneda_origen + ' = ' + rateNumber(result.tasa) + ' ' + result.moneda_destino;
        rateType.textContent = result.tipo_tasa || '—';
        updated.textContent = localDate(result.fecha_hora);
      }).catch(function (requestError) { showError(requestError.message); });
    }
    function schedule() { window.clearTimeout(timer); timer = window.setTimeout(simulate, 300); }
    amount.addEventListener('input', schedule); from.addEventListener('change', simulate); to.addEventListener('change', simulate);
    root.querySelector('[data-converter-swap]').addEventListener('click', function (event) { var previous = from.value; from.value = to.value; to.value = previous; event.currentTarget.classList.add('is-swapping'); window.setTimeout(function () { event.currentTarget.classList.remove('is-swapping'); }, 320); simulate(); });
  }

  function initLanding() {
    var landing = document.querySelector('[data-django-landing]');
    if (!landing) return;
    landing.querySelectorAll('.reveal').forEach(function (element) { var observer = new IntersectionObserver(function (entries) { if (entries[0].isIntersecting) { element.classList.add('visible'); observer.disconnect(); } }, { threshold: .1 }); observer.observe(element); });
    landing.querySelectorAll('a[href^="#"]').forEach(function (link) { link.addEventListener('click', function (event) { var target = document.querySelector(link.getAttribute('href')); if (!target) return; event.preventDefault(); history.pushState(null, '', link.getAttribute('href')); target.scrollIntoView({ behavior: 'smooth' }); }); });
    request(landing.dataset.ratesUrl, {}, true).then(function (data) { renderRates(landing, data); }).catch(function (error) { renderRates(landing, { estado: 'indisponible', mensaje: error.message, tasas_referencia: [] }); });
    request(landing.dataset.currenciesUrl).then(function (data) {
      if (!Array.isArray(data.monedas)) throw new Error('El catálogo de monedas no tiene un formato válido.');
      renderCurrencies(landing, data.monedas);
      initConverter(landing, data.monedas);
    }).catch(function (error) {
      renderCurrencies(landing, []);
      initConverter(landing, []);
      var message = landing.querySelector('[data-converter-error]');
      message.hidden = false;
      message.textContent = error.message || 'No se pudieron cargar las monedas.';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initLanding, { once: true });
  else initLanding();
}());
