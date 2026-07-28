import assert from 'node:assert/strict';
import test from 'node:test';

import { initAuthGate } from '../../apps/companion-web/companion-ui/js/features/auth/auth-gate.js';

class FakeElement extends EventTarget {
  constructor() {
    super();
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.value = '';
    this.textContent = '';
    this.focused = false;
  }

  focus() {
    this.focused = true;
  }
}

function response(status = 200) {
  return { ok: status >= 200 && status < 300, status };
}

function harness(fetchImpl, { online = true } = {}) {
  const body = new FakeElement();
  const elements = {
    '[data-hook="auth-gate"]': new FakeElement(),
    '[data-hook="auth-form"]': new FakeElement(),
    '[data-hook="auth-code"]': new FakeElement(),
    '[data-hook="auth-submit"]': new FakeElement(),
    '[data-hook="auth-error"]': new FakeElement(),
  };
  const events = new EventTarget();
  let reloads = 0;
  const documentRef = {
    body,
    querySelector: (selector) => elements[selector] ?? null,
  };
  const windowRef = {
    fetch: fetchImpl,
    setTimeout(callback) { callback(); },
    addEventListener: (...args) => events.addEventListener(...args),
    removeEventListener: (...args) => events.removeEventListener(...args),
    dispatchEvent: (...args) => events.dispatchEvent(...args),
    navigator: { onLine: online },
    location: { reload() { reloads += 1; } },
  };
  return {
    body,
    gate: elements['[data-hook="auth-gate"]'],
    form: elements['[data-hook="auth-form"]'],
    input: elements['[data-hook="auth-code"]'],
    submit: elements['[data-hook="auth-submit"]'],
    error: elements['[data-hook="auth-error"]'],
    documentRef,
    windowRef,
    reloads: () => reloads,
  };
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
}

test('fixture mode bypasses session checks', async () => {
  let calls = 0;
  const ui = harness(async () => { calls += 1; return response(); });
  const auth = initAuthGate({
    runtimeMode: 'fixture',
    documentRef: ui.documentRef,
    windowRef: ui.windowRef,
  });

  assert.deepEqual(await auth.ready, { authenticated: true });
  assert.equal(calls, 0);
  assert.equal(ui.body.dataset.authStatus, 'authenticated');
  assert.equal(ui.gate.hidden, true);
});

test('an existing session starts the application without showing the gate', async () => {
  const calls = [];
  const ui = harness(async (path, options) => {
    calls.push({ path, options });
    return response();
  });
  const auth = initAuthGate({
    runtimeMode: 'api',
    documentRef: ui.documentRef,
    windowRef: ui.windowRef,
  });

  await auth.ready;
  assert.equal(calls[0].path, '/api/auth/session');
  assert.equal(calls[0].options.credentials, 'same-origin');
  assert.equal(ui.body.dataset.authStatus, 'authenticated');
  assert.equal(ui.gate.hidden, true);
});

test('offline startup opens only the local shell without asking for the invite code', async () => {
  const ui = harness(async () => { throw new TypeError('offline'); }, { online: false });
  const auth = initAuthGate({
    runtimeMode: 'api',
    documentRef: ui.documentRef,
    windowRef: ui.windowRef,
  });

  await auth.ready;
  assert.equal(ui.body.dataset.authStatus, 'authenticated');
  assert.equal(ui.gate.hidden, true);
});

test('missing session shows the login gate and invalid codes remain there', async () => {
  const calls = [];
  const ui = harness(async (path) => {
    calls.push(path);
    return response(401);
  });
  initAuthGate({ runtimeMode: 'api', documentRef: ui.documentRef, windowRef: ui.windowRef });
  await flush();

  assert.equal(ui.body.dataset.authStatus, 'required');
  assert.equal(ui.gate.hidden, false);
  assert.equal(ui.input.focused, true);

  ui.input.value = 'wrong-code';
  ui.form.dispatchEvent(new Event('submit', { cancelable: true }));
  await flush();

  assert.deepEqual(calls, ['/api/auth/session', '/api/auth/login']);
  assert.equal(ui.error.textContent, '这个邀请码暂时无法进入。');
  assert.equal(ui.error.hidden, false);
  assert.equal(ui.submit.disabled, false);
});

test('a valid first login resolves startup and clears the access code', async () => {
  const ui = harness(async (path) => response(path === '/api/auth/session' ? 401 : 200));
  const auth = initAuthGate({
    runtimeMode: 'api',
    documentRef: ui.documentRef,
    windowRef: ui.windowRef,
  });
  await flush();
  ui.input.value = 'invite-code';
  ui.form.dispatchEvent(new Event('submit', { cancelable: true }));

  assert.deepEqual(await auth.ready, { authenticated: true });
  assert.equal(ui.input.value, '');
  assert.equal(ui.body.dataset.authStatus, 'authenticated');
  assert.equal(ui.reloads(), 0);
});

test('an expired running session requires login and reloads after success', async () => {
  const ui = harness(async () => response(200));
  const auth = initAuthGate({
    runtimeMode: 'api',
    documentRef: ui.documentRef,
    windowRef: ui.windowRef,
  });
  await auth.ready;
  auth.markStarted();

  ui.windowRef.dispatchEvent(new Event('luminous:auth-required'));
  assert.equal(ui.body.dataset.authStatus, 'required');
  assert.equal(ui.error.textContent, '登录已过期，请再次输入邀请码。');

  ui.input.value = 'invite-code';
  ui.form.dispatchEvent(new Event('submit', { cancelable: true }));
  await flush();
  assert.equal(ui.reloads(), 1);
});
