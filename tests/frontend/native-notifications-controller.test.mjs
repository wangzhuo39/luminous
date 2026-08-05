import assert from 'node:assert/strict';
import test from 'node:test';

import { initNativeNotifications } from '../../apps/companion-web/companion-ui/js/features/productization/native-notifications-controller.js';

class FakeTarget {
  constructor() {
    this.listeners = new Map();
    this.disabled = false;
    this.textContent = '';
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }

  removeEventListener(name, listener) {
    if (this.listeners.get(name) === listener) this.listeners.delete(name);
  }

  dispatch(name) {
    this.listeners.get(name)?.({ type: name });
  }
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('native notification UI enables and pauses realtime proactive delivery', async () => {
  const section = { hidden: true };
  const button = new FakeTarget();
  const status = { textContent: '' };
  const documentRef = {
    querySelector(selector) {
      return {
        '[data-hook="native-notification-section"]': section,
        '[data-hook="native-notification-button"]': button,
        '[data-hook="native-notification-status"]': status,
      }[selector] ?? null;
    },
  };
  const windowEvents = new FakeTarget();
  let state = {
    native: true,
    local: 'denied',
    delivery: 'periodic-local',
    realtime: { enabled: false, running: false, status: 'stopped' },
  };
  let enableCalls = 0;
  let disableCalls = 0;
  const windowRef = {
    __LUMINOUS_NATIVE__: true,
    LuminousNativeReady: Promise.resolve(),
    LuminousNative: {
      permissionState: async () => state,
      enableNotifications: async () => {
        enableCalls += 1;
        state = {
          ...state,
          local: 'granted',
          delivery: 'realtime-websocket',
          realtime: { enabled: true, running: true, status: 'connected' },
        };
        return state;
      },
      disableRealtime: async () => {
        disableCalls += 1;
        state = {
          ...state,
          delivery: 'periodic-local',
          realtime: { enabled: false, running: false, status: 'stopped' },
        };
        return state;
      },
    },
    addEventListener: (...args) => windowEvents.addEventListener(...args),
    removeEventListener: (...args) => windowEvents.removeEventListener(...args),
  };

  const controller = initNativeNotifications({ documentRef, windowRef });
  await settle();
  assert.equal(section.hidden, false);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, '开启 Android 通知');

  button.dispatch('click');
  await settle();
  assert.equal(enableCalls, 1);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, '暂停实时陪伴');
  assert.match(status.textContent, /实时连接已建立/);

  button.dispatch('click');
  await settle();
  assert.equal(disableCalls, 1);
  assert.equal(button.textContent, '开启实时陪伴');
  assert.match(status.textContent, /后台定期同步/);

  controller.destroy();
  assert.equal(windowEvents.listeners.has('luminous:native-notification-state'), false);
});
