(function () {
  'use strict';

  document.querySelectorAll('[data-cliente-classic-form]').forEach(function (form) {
    bindFiscalForm(form, form.dataset.existente === 'true' ? {
      tipo_persona: form.dataset.originalTipo,
      documento: form.dataset.originalDocumento,
      dv: form.dataset.originalDv
    } : null);
    form.addEventListener('submit', function (event) {
      if (!validateClienteForm(form)) event.preventDefault();
    });
  });

  var page = document.querySelector('[data-clientes-page]');
  if (!page) return;

  var tokenInput = page.querySelector('input[name="csrfmiddlewaretoken"]');
  var csrfToken = tokenInput ? tokenInput.value : '';

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function notify(message, type) {
    if (window.GEApp && window.GEApp.toast) window.GEApp.toast(message, type);
  }

  function endpoint(template, id) {
    return template.replace('/0/', '/' + id + '/');
  }

  function recargar() {
    window.setTimeout(function () { window.location.reload(); }, 600);
  }

  function request(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify(payload || {})
    }).then(function (response) {
      var authError = window.GEApp && window.GEApp.authenticationError
        ? window.GEApp.authenticationError(response)
        : null;
      if (authError) throw authError;
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var error = new Error(data.error || 'No fue posible completar la operación.');
          error.details = data.detalles;
          throw error;
        }
        return data;
      });
    });
  }

  function consultar(url) {
    return fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    }).then(function (response) {
      var authError = window.GEApp && window.GEApp.authenticationError
        ? window.GEApp.authenticationError(response)
        : null;
      if (authError) throw authError;
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'No fue posible consultar los métodos de pago.');
        return data;
      });
    });
  }

  function dialog(id, title, body, confirmLabel, onConfirm, danger) {
    var previous = document.getElementById(id);
    if (previous) previous.remove();
    var backdrop = document.createElement('div');
    backdrop.id = id;
    backdrop.className = 'ge-modal-backdrop is-open';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.setAttribute('aria-labelledby', id + '-title');
    backdrop.innerHTML = '<div class="ge-modal"><h3 id="' + id + '-title">' + esc(title) + '</h3>' + body +
      '<div class="ge-modal-actions"><button type="button" class="ge-btn-outline" data-close>Cancelar</button>' +
      '<button type="button" class="ge-btn-primary' + (danger ? ' ge-btn-primary--danger' : '') + '" data-confirm>' + esc(confirmLabel) + '</button></div></div>';
    document.body.appendChild(backdrop);
    function close() { backdrop.remove(); }
    backdrop.querySelector('[data-close]').addEventListener('click', close);
    backdrop.addEventListener('click', function (event) { if (event.target === backdrop) close(); });
    backdrop.querySelector('[data-confirm]').addEventListener('click', function () {
      if (!onConfirm || onConfirm(backdrop, close) !== false) close();
    });
    var first = backdrop.querySelector('input,select,button');
    if (first) first.focus();
    return backdrop;
  }

  function field(label, control, name) {
    return '<label class="ge-crud-field"' + (name ? ' data-cliente-field="' + name + '"' : '') + '><span class="ge-field-label">' + label + '</span>' + control + '</label>';
  }

  function clearFieldErrors(form) {
    form.querySelectorAll('[data-cliente-error]').forEach(function (node) { node.remove(); });
    Array.prototype.forEach.call(form.elements, function (input) {
      input.removeAttribute('aria-invalid');
      var descriptions = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (id) {
        return id && id.indexOf('cliente-error-') !== 0 && !/_error$/.test(id);
      });
      if (descriptions.length) input.setAttribute('aria-describedby', descriptions.join(' '));
      else input.removeAttribute('aria-describedby');
    });
  }

  function showFieldError(form, name, message) {
    var input = form.elements[name];
    if (!input) return false;
    var note = document.createElement('span');
    note.className = 'field-error';
    note.dataset.clienteError = name;
    note.id = 'cliente-error-' + name;
    note.textContent = message;
    input.setAttribute('aria-invalid', 'true');
    input.setAttribute('aria-describedby', [input.getAttribute('aria-describedby'), note.id].filter(Boolean).join(' '));
    input.parentElement.appendChild(note);
    return true;
  }

  function bindFiscalForm(form, original) {
    var tipo = form.elements.tipo_persona;
    var documento = form.elements.documento;
    var dv = form.elements.dv;
    var dvField = form.querySelector('[data-cliente-field="dv"]');
    var label = form.querySelector('[data-cliente-field="documento"] .ge-field-label, [data-cliente-field="documento"] label');
    function sync() {
      var juridica = tipo.value === 'JURIDICA';
      var legacy = original && original.tipo_persona === 'JURIDICA' &&
        (!/^[0-9]+$/.test(original.documento) || !original.dv) &&
        tipo.value === original.tipo_persona && documento.value.trim() === original.documento &&
        dv.value.trim() === original.dv;
      if (label) label.textContent = juridica ? 'RUC' : 'Cédula o pasaporte';
      documento.placeholder = juridica ? 'Número principal, sin guion ni DV' : 'Cédula o pasaporte';
      if (juridica && !legacy) {
        documento.setAttribute('pattern', '[0-9]+');
        documento.setAttribute('inputmode', 'numeric');
      } else {
        documento.removeAttribute('pattern');
        documento.removeAttribute('inputmode');
      }
      dv.required = juridica && !legacy;
      dv.disabled = !juridica;
      dvField.hidden = !juridica;
    }
    form.addEventListener('input', function () { clearFieldErrors(form); sync(); });
    tipo.addEventListener('change', function () { clearFieldErrors(form); sync(); });
    sync();
  }

  function validateClienteForm(form) {
    clearFieldErrors(form);
    var valid = true;
    Array.prototype.forEach.call(form.elements, function (input) {
      if (input.disabled || !input.checkValidity || input.checkValidity()) return;
      var message = input.validity.typeMismatch ? 'Ingresá un correo electrónico válido.' :
        input.validity.patternMismatch ? (input.name === 'dv' ? 'El DV debe ser un dígito del 0 al 9.' : 'El RUC debe contener solo números, sin guion ni DV.') :
        input.validity.tooLong ? 'El valor supera la longitud permitida.' : 'Completá este campo.';
      showFieldError(form, input.name, message);
      valid = false;
    });
    if (!valid) {
      var first = form.querySelector('[aria-invalid="true"]');
      if (first) first.focus();
    }
    return valid;
  }

  function formValue(form, name) {
    return form.elements[name] ? form.elements[name].value.trim() : '';
  }

  function tipoPersonaOptions(selected) {
    var options = [['FISICA', 'Persona Física'], ['JURIDICA', 'Persona Jurídica']];
    return options.map(function (entry) {
      return '<option value="' + entry[0] + '"' + (entry[0] === selected ? ' selected' : '') + '>' + entry[1] + '</option>';
    }).join('');
  }

  function clienteForm(cliente) {
    var editando = !!cliente;
    var url = editando ? endpoint(page.dataset.editarUrl, cliente.id) : page.dataset.crearUrl;
    var content = '<form data-cliente-form novalidate>' +
      field('NOMBRE O RAZÓN SOCIAL', '<input class="ge-input" name="nombre_razon_social" maxlength="150" required placeholder="Razón social o nombre completo" value="' + esc(editando ? cliente.nombre_razon_social : '') + '">', 'nombre_razon_social') +
      field('TIPO DE PERSONA', '<select class="ge-input" name="tipo_persona" required>' + tipoPersonaOptions(editando ? cliente.tipo_persona : 'FISICA') + '</select>', 'tipo_persona') +
      field('CÉDULA O PASAPORTE', '<input class="ge-input" name="documento" maxlength="30" required value="' + esc(editando ? cliente.documento : '') + '">', 'documento') +
      field('DV', '<input class="ge-input" name="dv" maxlength="1" pattern="[0-9]" inputmode="numeric" placeholder="0–9" value="' + esc(editando ? cliente.dv : '') + '"><small>Dígito verificador, separado del RUC.</small>', 'dv') +
      field('CORREO ELECTRÓNICO', '<input class="ge-input" type="email" name="correo_facturacion" maxlength="254" autocomplete="email" value="' + esc(editando ? cliente.correo_facturacion : '') + '"><small>Opcional. Las facturas se consultan en la web.</small>', 'correo_facturacion') +
      '</form>';
    var backdrop = dialog(editando ? 'ge-cliente-editar' : 'ge-cliente-nuevo', editando ? 'Editar cliente' : 'Nuevo cliente', content,
      editando ? 'Guardar cambios' : 'Registrar cliente', function (box, close) {
        var form = box.querySelector('form');
        var confirm = box.querySelector('[data-confirm]');
        if (confirm.disabled || !validateClienteForm(form)) return false;
        var payload = {
          nombre_razon_social: formValue(form, 'nombre_razon_social'),
          tipo_persona: formValue(form, 'tipo_persona'),
          documento: formValue(form, 'documento'),
          dv: formValue(form, 'tipo_persona') === 'JURIDICA' ? formValue(form, 'dv') : '',
          correo_facturacion: formValue(form, 'correo_facturacion')
        };
        confirm.disabled = true;
        request(url, payload).then(function (data) {
          close();
          notify(data.message || 'Cliente guardado correctamente.');
          recargar();
        }).catch(function (error) {
          var shown = false;
          if (error.details) {
            Object.keys(error.details).forEach(function (name) {
              var messages = error.details[name].map(function (entry) { return entry.message; }).join(' ');
              shown = showFieldError(form, name, messages) || shown;
            });
          }
          if (shown) {
            var first = form.querySelector('[aria-invalid="true"]');
            if (first) first.focus();
          } else notify(error.message, 'error');
        }).finally(function () { confirm.disabled = false; });
        return false;
      });
    var form = backdrop.querySelector('form');
    bindFiscalForm(form, cliente);
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      backdrop.querySelector('[data-confirm]').click();
    });
  }

  function darDeBaja(id, nombre) {
    dialog('ge-cliente-baja', 'Dar de baja cliente',
      '<p>¿Confirmás la baja de <strong>' + esc(nombre) + '</strong>? El cliente quedará inactivo y no podrá operar en la plataforma.</p>',
      'Dar de baja', function (_box, close) {
        request(endpoint(page.dataset.bajaUrl, id)).then(function (data) {
          close();
          notify(data.message);
          recargar();
        }).catch(function (error) {
          notify(error.message, 'error');
        });
        return false;
      }, true);
  }

  function seleccionar(id) {
    request(endpoint(page.dataset.seleccionarUrl, id)).then(function (data) {
      notify(data.message);
      recargar();
    }).catch(function (error) {
      notify(error.message, 'error');
    });
  }

  function configurarComisiones() {
    consultar(page.dataset.comisionesUrl).then(function (data) {
      var content = '<form data-comisiones-form><p class="ge-frontend-subtitle" style="margin-bottom:16px">Definí el porcentaje aplicado a las nuevas operaciones de cada categoría.</p>' +
        data.categorias.map(function (categoria) {
          return field(esc(categoria.nombre), '<input class="ge-input" type="number" name="categoria_' + categoria.id + '" data-categoria-id="' + categoria.id + '" min="0" max="100" step="0.01" required value="' + esc(categoria.porcentaje_comision) + '">');
        }).join('') + '</form>';
      dialog('ge-comisiones-configurar', 'Configurar comisiones', content, 'Guardar comisiones', function (box, close) {
        var form = box.querySelector('[data-comisiones-form]');
        if (!form.reportValidity()) return false;
        var comisiones = Array.prototype.map.call(form.querySelectorAll('[data-categoria-id]'), function (input) {
          return {
            id: Number(input.dataset.categoriaId),
            porcentaje_comision: input.value
          };
        });
        request(page.dataset.comisionesUrl, { comisiones: comisiones }).then(function (resultado) {
          close();
          notify(resultado.message);
          recargar();
        }).catch(function (error) {
          notify(error.message, 'error');
        });
        return false;
      });
    }).catch(function (error) {
      notify(error.message, 'error');
    });
  }

  var nuevoBtn = page.querySelector('[data-cliente-nuevo]');
  if (nuevoBtn) nuevoBtn.addEventListener('click', function () { clienteForm(null); });

  var comisionesBtn = page.querySelector('[data-comisiones-configurar]');
  if (comisionesBtn) comisionesBtn.addEventListener('click', configurarComisiones);

  page.querySelectorAll('[data-cliente-editar]').forEach(function (button) {
    button.addEventListener('click', function () {
      clienteForm({
        id: Number(button.dataset.clienteEditar),
        nombre_razon_social: button.dataset.nombre,
        tipo_persona: button.dataset.tipo,
        documento: button.dataset.documento,
        dv: button.dataset.dv,
        correo_facturacion: button.dataset.correo
      });
    });
  });

  page.querySelectorAll('[data-cliente-baja]').forEach(function (button) {
    button.addEventListener('click', function () {
      darDeBaja(Number(button.dataset.clienteBaja), button.dataset.nombre);
    });
  });

  page.querySelectorAll('[data-cliente-seleccionar]').forEach(function (button) {
    button.addEventListener('click', function () {
      seleccionar(Number(button.dataset.clienteSeleccionar));
    });
  });

  var preferenciaForm = page.querySelector('[data-metodo-preferido-form]');
  var preferenciaAbrir = page.querySelector('[data-metodo-preferido-abrir]');

  function urlPreferencia() {
    return endpoint(page.dataset.preferenciaUrl, preferenciaForm.dataset.clienteId);
  }

  function cargarMetodosPreferidos() {
    var opciones = preferenciaForm.querySelector('[data-metodos-pago-activos]');
    var guardar = preferenciaForm.querySelector('[data-metodo-preferido-guardar]');
    opciones.innerHTML = '<p class="ge-frontend-subtitle">Cargando métodos disponibles…</p>';
    guardar.disabled = true;

    consultar(urlPreferencia()).then(function (data) {
      var preferidoId = data.metodo_pago_preferido && data.metodo_pago_preferido.activo
        ? data.metodo_pago_preferido.id
        : null;
      if (!data.metodos_disponibles.length) {
        opciones.innerHTML = '<p class="ge-frontend-subtitle">No hay métodos de pago activos disponibles.</p>';
        return;
      }
      opciones.innerHTML = data.metodos_disponibles.map(function (metodo) {
        var checked = metodo.id === preferidoId ? ' checked' : '';
        var descripcion = metodo.descripcion
          ? '<small style="color:var(--text-muted)">' + esc(metodo.descripcion) + '</small>'
          : '';
        return '<label class="ge-card" style="display:flex;align-items:center;gap:10px;padding:12px;cursor:pointer">' +
          '<input type="radio" name="metodo_pago_id" value="' + metodo.id + '"' + checked + '>' +
          '<span><strong style="display:block">' + esc(metodo.nombre) + '</strong>' + descripcion + '</span></label>';
      }).join('');
      guardar.disabled = false;
    }).catch(function (error) {
      opciones.innerHTML = '<p class="ge-frontend-subtitle">No fue posible cargar los métodos disponibles.</p>';
      notify(error.message, 'error');
    });
  }

  if (preferenciaAbrir && preferenciaForm) {
    preferenciaAbrir.addEventListener('click', cargarMetodosPreferidos);
    preferenciaForm.addEventListener('submit', function (event) {
      event.preventDefault();
      var seleccionado = preferenciaForm.querySelector('input[name="metodo_pago_id"]:checked');
      if (!seleccionado) {
        notify('Seleccioná un método de pago.', 'error');
        return;
      }
      request(urlPreferencia(), { metodo_pago_id: Number(seleccionado.value) })
        .then(function (data) {
          if (window.GEApp) window.GEApp.closeModal('metodo-pago-preferido');
          notify(data.message);
          recargar();
        })
        .catch(function (error) {
          notify(error.message, 'error');
        });
    });
  }
}());
