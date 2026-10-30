const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(className = '', text = '') {
    this.className = className; this.textContent = text; this.dataset = {};
    this.children = []; this.listeners = {}; this.attributes = {}; this.hidden = false;
    this.classList = { contains: name => this.className.split(' ').includes(name) };
  }
  appendChild(node) { this.children.push(node); node.parent = this; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  remove() { this.removed = true; }
  closest(selector) {
    for (let node = this; node; node = node.parent) {
      if (selector === '[hidden]' && node.hidden || selector === '.messages' && node.classList.contains('messages')) return node;
    }
    return null;
  }
}

function runtime() {
  const body = new Element(); const timers = []; const notices = [];
  const document = { body, readyState: 'loading', addEventListener() {},
    createElement() { return new Element(); },
    querySelector(selector) { return selector === '.ge-toast' ? body.children.find(node => !node.removed && node.classList.contains('ge-toast')) : null; },
    querySelectorAll() { return notices; }
  };
  const context = { document, window: { setTimeout(fn, delay) { timers.push({ fn, delay }); } } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../ge-app.js'), 'utf8'), context);
  return { app: context.window.GEApp, body, timers, notices, document,
    visible() { return body.children.filter(node => !node.removed); } };
}

test('cuatro variantes conservan toast único flotante, cierre y desaparición automática', () => {
  for (const type of ['success', 'error', 'warning', 'info']) {
    const ui = runtime(); const toast = ui.app.toast('Mensaje de prueba', type);
    assert.equal(ui.visible().length, 1);
    assert.equal(toast.className, 'ge-toast ge-toast--' + type);
    assert.equal(toast.attributes.role, ['error', 'warning'].includes(type) ? 'alert' : 'status');
    assert.equal(ui.timers[0].delay, 6000);
    assert.equal(toast.children[2].attributes['aria-label'], 'Cerrar');
    ui.timers[0].fn();
    assert.equal(ui.visible().length, 0);
  }
});

test('un mismo aviso activo o en cola no se duplica; avisos distintos se muestran sin perderse', () => {
  const ui = runtime(); const first = ui.app.toast('Guardado correctamente.', 'success');
  ui.app.toast('Guardado correctamente.', 'success');
  ui.app.toast('No se pudo cargar el historial.', 'error');
  ui.app.toast('No se pudo cargar el historial.', 'error');
  assert.equal(ui.visible().length, 1);
  assert.equal(ui.body.children.length, 1);
  assert.equal(ui.timers.length, 1);
  first.children[2].listeners.click();
  assert.equal(ui.visible().length, 1);
  assert.equal(ui.visible()[0].dataset.message, 'No se pudo cargar el historial.');
  ui.timers[0].fn(); // El timer anterior no descarta el aviso siguiente.
  assert.equal(ui.visible().length, 1);
  ui.timers[1].fn();
  assert.equal(ui.visible().length, 0);
});

test('mensajes Django y banners generales se adaptan una vez; errores de campos quedan visibles', () => {
  const ui = runtime();
  const messages = new Element('messages'); messages.hidden = true;
  const server = new Element('message success', 'Carga de fondos registrada.'); messages.appendChild(server);
  const banner = new Element('ge-success-banner', 'Carga de fondos registrada.');
  const field = new Element('errorlist', 'El monto es obligatorio.');
  ui.notices.push(server, banner);
  ui.app.initNotifications();
  ui.app.initNotifications();
  assert.equal(server.hidden, true);
  assert.equal(banner.hidden, true);
  assert.equal(field.hidden, false);
  assert.equal(ui.visible().length, 1);
  assert.equal(ui.body.children.length, 1);
  assert.equal(ui.visible()[0].dataset.message, 'Carga de fondos registrada.');
  const general = new Element('errorlist nonfield', 'La carga no pudo registrarse.');
  ui.notices.push(general);
  ui.app.initNotifications();
  assert.equal(general.hidden, true);
  ui.visible()[0].children[2].listeners.click();
  assert.equal(ui.visible()[0].className, 'ge-toast ge-toast--error');
});

test('los detalles técnicos se reemplazan por un mensaje amigable y los textos usan textContent', () => {
  for (const message of ['400 Bad Request', '500 Internal Server Error', 'DatabaseError: secreto', 'Traceback (most recent call last)', 'TypeError: undefined', 'Failed to fetch', '<!doctype html>']) {
    const ui = runtime(); ui.app.toast(message, 'error');
    assert.equal(ui.visible()[0].children[1].textContent, 'No se pudo completar la solicitud. Intentá nuevamente más tarde.');
  }
  const ui = runtime(); ui.app.toast('<img src=x onerror=alert(1)>', 'info');
  assert.equal(ui.visible()[0].children[1].textContent, '<img src=x onerror=alert(1)>');
  assert.equal(ui.visible()[0].children[1].innerHTML, undefined);
});

test('fondos insuficientes usa la moneda recibida sin fijar una por defecto', () => {
  const ui = runtime();
  for (const code of ['PYG', 'EUR', 'USD']) assert.equal(ui.app.insufficientFundsMessage(code),
    `No hay fondos suficientes en ${code} para completar esta operación. Probá con otro monto o intentá nuevamente más tarde.`);
  assert.equal(ui.app.insufficientFundsMessage(''), 'No hay fondos suficientes para completar esta operación. Probá con otro monto o intentá nuevamente más tarde.');
});
