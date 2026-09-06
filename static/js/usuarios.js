(function () {
  'use strict';

  var page = document.querySelector('[data-usuarios-page]');
  if (!page) return;

  var tokenInput = page.querySelector('input[name="csrfmiddlewaretoken"]');
  var csrfToken = tokenInput ? tokenInput.value : '';

  var businessRoles = [];
  var rolesScript = document.getElementById('ge-business-roles');
  if (rolesScript) {
    try { businessRoles = JSON.parse(rolesScript.textContent); } catch (e) { businessRoles = []; }
  }

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

  function obtenerDetalle(id) {
    return fetch(endpoint(page.dataset.detalleUrl, id), {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'No fue posible cargar el usuario.');
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

  function rolesSection(selected) {
    var items = businessRoles.map(function (role) {
      var checked = selected.indexOf(role) !== -1;
      return '<label class="ge-check-field" style="display:flex;align-items:center;gap:10px;padding:6px 0">' +
        '<input type="checkbox" name="roles" value="' + role + '"' + (checked ? ' checked' : '') + '>' +
        '<span>' + role + '</span></label>';
    }).join('');
    return '<div class="ge-field-label" style="margin-bottom:2px">Roles del sistema</div>' +
      '<small style="color:var(--text-2);font-size:11px;display:block;margin-bottom:8px">Definen las funciones habilitadas para esta identidad.</small>' +
      items;
  }

  function rolesChecked(form) {
    return Array.prototype.map.call(
      form.querySelectorAll('input[name="roles"]:checked'),
      function (el) { return el.value; }
    );
  }

  function nuevoUsuario() {
    var content = '<form data-usuario-form>' +
      field('USUARIO', '<input class="ge-input" name="username" required autocomplete="off" placeholder="Nombre de usuario">') +
      field('NOMBRE', '<input class="ge-input" name="first_name" autocomplete="off" placeholder="Nombre">') +
      field('APELLIDO', '<input class="ge-input" name="last_name" autocomplete="off" placeholder="Apellido">') +
      field('EMAIL', '<input class="ge-input" type="email" name="email" required autocomplete="off" placeholder="usuario@globalexchange.com">') +
      field('CONTRASEÑA TEMPORAL', '<input class="ge-input" type="password" name="password" minlength="8" required placeholder="Mínimo 8 caracteres">' +
        '<small style="color:var(--text-2);font-size:11px;display:block;margin-top:6px">El usuario deberá cambiarla al ingresar.</small>') +
      rolesSection(['USUARIO']) +
      '</form>';
    dialog('ge-usuario-nuevo', 'Nuevo usuario', content, 'Registrar usuario', function (box, close) {
      var form = box.querySelector('form');
      if (!form.reportValidity()) return false;
      var payload = {
        username: formValue(form, 'username'),
        first_name: formValue(form, 'first_name'),
        last_name: formValue(form, 'last_name'),
        email: formValue(form, 'email'),
        password: form.elements['password'].value,
        roles: rolesChecked(form)
      };
      request(page.dataset.crearUrl, payload).then(function (data) {
        close();
        notify(data.message || 'Usuario creado correctamente.');
        recargar();
      }).catch(function (error) {
        notify(error.message, 'error');
      });
      return false;
    });
  }

  function editarUsuario(id) {
    obtenerDetalle(id).then(function (user) {
      var content = '<form data-usuario-form>' +
        '<p class="ge-field-label" style="margin:0 0 14px">@' + esc(user.username) + '</p>' +
        field('NOMBRE', '<input class="ge-input" name="first_name" value="' + esc(user.first_name) + '">') +
        field('APELLIDO', '<input class="ge-input" name="last_name" value="' + esc(user.last_name) + '">') +
        field('EMAIL', '<input class="ge-input" type="email" name="email" required value="' + esc(user.email) + '">') +
        '<label class="ge-check-field" style="display:flex;align-items:center;gap:10px;margin:16px 0 18px">' +
        '<input type="checkbox" name="enabled"' + (user.enabled ? ' checked' : '') + '>' +
        '<span>Usuario habilitado</span></label>' +
        rolesSection(user.roles) +
        '</form>';
      dialog('ge-usuario-editar', 'Editar usuario', content, 'Guardar cambios', function (box, close) {
        var form = box.querySelector('form');
        if (!form.reportValidity()) return false;
        var payload = {
          first_name: formValue(form, 'first_name'),
          last_name: formValue(form, 'last_name'),
          email: formValue(form, 'email'),
          enabled: form.elements['enabled'].checked,
          roles: rolesChecked(form)
        };
        request(endpoint(page.dataset.editarUrl, id), payload).then(function (data) {
          close();
          notify(data.message || 'Usuario y roles actualizados.');
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

  function darDeBaja(id) {
    dialog('ge-usuario-baja', 'Dar de baja usuario',
      '<p>¿Confirmás la baja de este usuario? La cuenta quedará deshabilitada, su información se conserva y podrá volver a habilitarse desde Editar.</p>',
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

  var nuevoBtn = page.querySelector('[data-usuario-nuevo]');
  if (nuevoBtn) nuevoBtn.addEventListener('click', nuevoUsuario);

  page.querySelectorAll('[data-usuario-editar]').forEach(function (button) {
    button.addEventListener('click', function () {
      editarUsuario(button.dataset.userId);
    });
  });

  page.querySelectorAll('[data-usuario-baja]').forEach(function (button) {
    button.addEventListener('click', function () {
      darDeBaja(button.dataset.userId);
    });
  });
}());