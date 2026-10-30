// Ejecuta clientes.js real con un DOM mínimo; sin dependencias adicionales.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.children = [];
    this.value = '';
    this.hidden = false;
    this.disabled = false;
    this.required = false;
    this.textContent = '';
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  getAttribute(name) { return this.attributes[name] || null; }
  appendChild(node) { this.children.push(node); node.parentElement = this; }
  remove() { this.removed = true; }
  focus() { this.focused = true; }
  click() { if (!this.disabled) this.listeners.click?.({ target: this }); }
  dispatch(name) { this.listeners[name]?.({ target: this }); }
  checkValidity() {
    const pattern = this.attributes.pattern;
    this.validity = {
      valueMissing: this.required && !this.value,
      typeMismatch: Boolean(this.invalidEmail),
      patternMismatch: Boolean(this.value && pattern && !new RegExp('^(?:' + pattern + ')$').test(this.value))
    };
    return !Object.values(this.validity).some(Boolean);
  }
}

function formFor(values = {}) {
  const form = new Element();
  const fields = {};
  const names = ['nombre_razon_social', 'tipo_persona', 'documento', 'dv', 'correo_facturacion'];
  form.elements = names.map(name => {
    const input = new Element(); input.name = name; input.value = values[name] || '';
    input.required = ['nombre_razon_social', 'tipo_persona', 'documento'].includes(name);
    const wrapper = new Element(); wrapper.appendChild(input); fields[name] = wrapper;
    return input;
  });
  names.forEach((name, index) => { form.elements[name] = form.elements[index]; });
  form.elements.dv.setAttribute('pattern', '[0-9]');
  const label = new Element();
  form.querySelector = selector => selector.startsWith('[data-cliente-field="documento"]') ? label :
    selector === '[data-cliente-field="dv"]' ? fields.dv :
    selector === '[aria-invalid="true"]' ? form.elements.find(input => input.attributes['aria-invalid'] === 'true') : null;
  form.querySelectorAll = selector => selector === '[data-cliente-error]' ?
    Object.values(fields).flatMap(field => field.children).filter(node => node.dataset.clienteError && !node.removed) : [];
  return { form, fields, label };
}

function runtime() {
  const boxes = [];
  const page = new Element();
  page.dataset = { crearUrl: '/crear/', editarUrl: '/editar/0/' };
  page.querySelector = () => null;
  page.querySelectorAll = () => [];
  const calls = [], toasts = [];
  const context = {
    document: {
      querySelector: () => page,
      querySelectorAll: () => [],
      getElementById: id => boxes.find(box => box.id === id && !box.removed),
      body: { appendChild: box => boxes.push(box) },
      createElement: tag => {
        const node = new Element();
        if (tag === 'div') {
          Object.defineProperty(node, 'innerHTML', { set(html) {
            node.html = html;
            const values = {};
            for (const match of html.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g)) values[match[1]] = match[2];
            values.tipo_persona = /<option value="JURIDICA" selected>/.test(html) ? 'JURIDICA' : 'FISICA';
            node.formInfo = formFor(values);
            const confirm = new Element(), cancel = new Element();
            node.confirm = confirm;
            node.querySelector = selector => selector === '[data-confirm]' ? confirm : selector === '[data-close]' ? cancel :
              selector === 'form' ? node.formInfo.form : node.formInfo.form.elements[0];
          } });
        }
        return node;
      }
    },
    window: { GEApp: { toast: (message, type) => toasts.push({ message, type }) }, setTimeout() {} },
    fetch: async (url, options) => {
      calls.push({ url, payload: JSON.parse(options.body) });
      return { ok: true, json: async () => ({ message: 'Guardado' }) };
    }
  };
  const source = fs.readFileSync(path.join(__dirname, '../clientes.js'), 'utf8').replace(/\}\(\)\);\s*$/, '\n globalThis.ui = { bindFiscalForm, validateClienteForm, clienteForm };\n}());');
  vm.runInNewContext(source, context);
  return { ...context, boxes, calls, toasts, setFetch(fn) { context.fetch = fn; } };
}

const cliente = { id: 1, nombre_razon_social: 'Empresa', tipo_persona: 'JURIDICA', documento: '80012345', dv: '0', correo_facturacion: 'contacto@example.com' };
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };

test('persona física oculta y desactiva DV sin exigir RUC', () => {
  const app = runtime(), info = formFor({ ...cliente, tipo_persona: 'FISICA', documento: 'PAS-1', dv: '' });
  app.ui.bindFiscalForm(info.form, null);
  assert.equal(info.fields.dv.hidden, true);
  assert.equal(info.form.elements.dv.disabled, true);
  assert.equal(info.label.textContent, 'Cédula o pasaporte');
  assert.equal(app.ui.validateClienteForm(info.form), true);
});

test('jurídica exige RUC ASCII y DV de un dígito; cero es válido', () => {
  const app = runtime(), info = formFor(cliente);
  app.ui.bindFiscalForm(info.form, null);
  assert.equal(info.label.textContent, 'RUC');
  assert.equal(info.form.elements.dv.required, true);
  assert.equal(app.ui.validateClienteForm(info.form), true);
  for (const value of ['ABC', '80012345-0', '１２３']) {
    info.form.elements.documento.value = value;
    assert.equal(app.ui.validateClienteForm(info.form), false);
    assert.equal(info.form.elements.documento.attributes['aria-invalid'], 'true');
  }
  info.form.elements.documento.value = cliente.documento;
  info.form.elements.dv.value = '';
  assert.equal(app.ui.validateClienteForm(info.form), false);
});

test('cambiar tipo preserva valores introducidos y restaura requisitos', () => {
  const app = runtime(), info = formFor(cliente);
  app.ui.bindFiscalForm(info.form, cliente);
  info.form.elements.tipo_persona.value = 'FISICA';
  info.form.elements.tipo_persona.dispatch('change');
  assert.equal(info.form.elements.dv.disabled, true);
  assert.equal(info.form.elements.dv.value, '0');
  info.form.elements.tipo_persona.value = 'JURIDICA';
  info.form.elements.tipo_persona.dispatch('change');
  assert.equal(info.form.elements.dv.disabled, false);
  assert.equal(info.form.elements.dv.required, true);
  assert.equal(info.form.elements.correo_facturacion.value, cliente.correo_facturacion);
});

test('legacy sin cambios fiscales permite nombre; cambiar RUC vuelve a exigir DV', () => {
  const app = runtime(), original = { ...cliente, documento: 'EMP-ANTIGUA', dv: '' }, info = formFor(original);
  app.ui.bindFiscalForm(info.form, original);
  info.form.elements.nombre_razon_social.value = 'Nuevo nombre';
  info.form.dispatch('input');
  assert.equal(app.ui.validateClienteForm(info.form), true);
  info.form.elements.documento.value = '80098765';
  info.form.dispatch('input');
  assert.equal(info.form.elements.dv.required, true);
  assert.equal(app.ui.validateClienteForm(info.form), false);
});

test('correo semánticamente inválido muestra error junto al campo sin toast', () => {
  const app = runtime(), info = formFor(cliente);
  app.ui.bindFiscalForm(info.form, cliente);
  info.form.elements.correo_facturacion.invalidEmail = true;
  assert.equal(app.ui.validateClienteForm(info.form), false);
  assert.match(info.fields.correo_facturacion.children.at(-1).textContent, /correo electrónico válido/);
  assert.equal(app.toasts.length, 0);
});

test('modal precarga email y DV y envía base separada; evita doble envío en curso', async () => {
  const app = runtime();
  app.ui.clienteForm(cliente);
  const box = app.boxes[0];
  assert.equal(box.formInfo.form.elements.dv.value, '0');
  assert.equal(box.formInfo.form.elements.correo_facturacion.value, cliente.correo_facturacion);
  box.confirm.click();
  box.confirm.click();
  assert.equal(app.calls.length, 1);
  assert.equal(app.calls[0].payload.documento, cliente.documento);
  assert.equal(app.calls[0].payload.dv, '0');
  assert.equal(app.calls[0].payload.correo_facturacion, cliente.correo_facturacion);
  await settle();
  assert.equal(box.removed, true);
});

test('modal al cambiar a física no envía el DV jurídico anterior', async () => {
  const app = runtime();
  app.ui.clienteForm(cliente);
  const box = app.boxes[0], form = box.formInfo.form;
  form.elements.tipo_persona.value = 'FISICA';
  form.elements.tipo_persona.dispatch('change');
  box.confirm.click();
  await settle();
  assert.equal(app.calls[0].payload.dv, '');
  assert.equal(form.elements.dv.value, '0');
});

test('error API de campo queda inline, conserva formulario y no duplica toast', async () => {
  const app = runtime();
  app.setFetch(async () => ({ ok: false, json: async () => ({ error: 'Inválido', detalles: { correo_facturacion: [{ message: 'Correo rechazado.' }] } }) }));
  app.ui.clienteForm(cliente);
  const box = app.boxes[0];
  box.confirm.click();
  await settle();
  assert.equal(box.formInfo.fields.correo_facturacion.children.at(-1).textContent, 'Correo rechazado.');
  assert.equal(box.removed, undefined);
  assert.equal(box.confirm.disabled, false);
  assert.equal(app.toasts.length, 0);
});

test('fallo general usa un solo toast y mantiene datos para reintentar', async () => {
  const app = runtime();
  app.setFetch(async () => { throw new Error('Sin conexión'); });
  app.ui.clienteForm(cliente);
  const box = app.boxes[0];
  box.confirm.click();
  await settle();
  assert.equal(app.toasts.length, 1);
  assert.equal(app.toasts[0].message, 'Sin conexión');
  assert.equal(box.removed, undefined);
  assert.equal(box.formInfo.form.elements.correo_facturacion.value, cliente.correo_facturacion);
});

test('valores del cliente se escapan antes de insertarse en modal', () => {
  const app = runtime();
  app.ui.clienteForm({ ...cliente, nombre_razon_social: '\"><img src=x onerror=alert(1)>' });
  assert.ok(app.boxes[0].html.includes('&quot;&gt;&lt;img'));
  assert.equal(app.boxes[0].html.includes('<img'), false);
});

test('limpiar errores conserva la descripción de ayuda del campo', () => {
  const app = runtime(), info = formFor(cliente);
  app.ui.bindFiscalForm(info.form, cliente);
  const email = info.form.elements.correo_facturacion;
  email.setAttribute('aria-describedby', 'id_correo_helptext');
  email.invalidEmail = true;
  assert.equal(app.ui.validateClienteForm(info.form), false);
  assert.equal(email.getAttribute('aria-describedby'), 'id_correo_helptext cliente-error-correo_facturacion');
  email.invalidEmail = false;
  info.form.dispatch('input');
  assert.equal(email.getAttribute('aria-describedby'), 'id_correo_helptext');
  assert.equal(info.form.querySelectorAll('[data-cliente-error]').length, 0);
});
