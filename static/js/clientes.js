(function () {
  'use strict';

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
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'No fue posible completar la operación.');
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
  }

  function field(label, control) {
    return '<label class="ge-crud-field"><span class="ge-field-label">' + label + '</span>' + control + '</label>';
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
    var content = '<form data-cliente-form>' +
      field('NOMBRE O RAZÓN SOCIAL', '<input class="ge-input" name="nombre_razon_social" maxlength="150" required placeholder="Razón social o nombre completo" value="' + esc(editando ? cliente.nombre_razon_social : '') + '">') +
      field('TIPO DE PERSONA', '<select class="ge-input" name="tipo_persona" required>' + tipoPersonaOptions(editando ? cliente.tipo_persona : 'FISICA') + '</select>') +
      field('DOCUMENTO', '<input class="ge-input" name="documento" maxlength="30" required placeholder="Cédula, RUC o pasaporte" value="' + esc(editando ? cliente.documento : '') + '">') +
      '</form>';
    dialog(editando ? 'ge-cliente-editar' : 'ge-cliente-nuevo', editando ? 'Editar cliente' : 'Nuevo cliente', content,
      editando ? 'Guardar cambios' : 'Registrar cliente', function (box, close) {
        var form = box.querySelector('form');
        if (!form.reportValidity()) return false;
        var payload = {
          nombre_razon_social: formValue(form, 'nombre_razon_social'),
          tipo_persona: formValue(form, 'tipo_persona'),
          documento: formValue(form, 'documento')
        };
        request(url, payload).then(function (data) {
          close();
          notify(data.message || 'Cliente guardado correctamente.');
          recargar();
        }).catch(function (error) {
          notify(error.message, 'error');
        });
        return false;
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

  var nuevoBtn = page.querySelector('[data-cliente-nuevo]');
  if (nuevoBtn) nuevoBtn.addEventListener('click', function () { clienteForm(null); });

  page.querySelectorAll('[data-cliente-editar]').forEach(function (button) {
    button.addEventListener('click', function () {
      clienteForm({
        id: Number(button.dataset.clienteEditar),
        nombre_razon_social: button.dataset.nombre,
        tipo_persona: button.dataset.tipo,
        documento: button.dataset.documento
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
}());