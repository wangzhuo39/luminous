import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  clearRecoverableDraft,
  DRAFT_STORAGE_KEY,
  DRAFT_TTL_MS,
  loadRecoveredDraft,
  saveRecoverableDraft,
} from '../../apps/companion-web/companion-ui/js/features/productization/draft-recovery.js';
import {
  buildSpaceURL,
  initSpaceRouter,
  readSpaceFromURL,
} from '../../apps/companion-web/companion-ui/js/features/productization/space-router.js';
import { initPwaExperience } from '../../apps/companion-web/companion-ui/js/features/productization/pwa-controller.js';

class MemoryStorage {
  values = new Map();
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

class FakeButton extends EventTarget {
  hidden = true;
  disabled = false;
  dataset = {};
  click() { this.dispatchEvent(new Event('click')); }
}

function fakeWindow(href = 'https://luminous.test/?mode=fixture') {
  const target = new EventTarget();
  let url = new URL(href);
  const update = (value) => { url = new URL(value, url); };
  Object.defineProperties(target, {
    location: { get: () => ({ href: url.href, pathname: url.pathname, search: url.search, hash: url.hash, reload() {} }) },
    history: { value: {
      entries: [],
      pushState(_state, _title, value) { this.entries.push(['push', value]); update(value); },
      replaceState(_state, _title, value) { this.entries.push(['replace', value]); update(value); },
    } },
    matchMedia: { value: () => ({ matches: false }) },
  });
  return target;
}

test('session draft recovery is versioned, bounded, expiring, and clearable', () => {
  const storage = new MemoryStorage();
  assert.equal(loadRecoveredDraft(storage, 100), null);
  assert.equal(saveRecoverableDraft(storage, '还没有寄出的字', 100), true);
  assert.deepEqual(loadRecoveredDraft(storage, 101), { text: '还没有寄出的字', savedAt: 100 });
  assert.equal(loadRecoveredDraft(storage, 100 + DRAFT_TTL_MS + 1), null);
  storage.setItem(DRAFT_STORAGE_KEY, '{broken');
  assert.equal(loadRecoveredDraft(storage, 200), null);
  saveRecoverableDraft(storage, '重新写下', 201);
  clearRecoverableDraft(storage);
  assert.equal(storage.getItem(DRAFT_STORAGE_KEY), null);
});

test('space URLs preserve fixture mode and reject opaque or unknown resources', () => {
  const opened = buildSpaceURL('https://luminous.test/?mode=fixture', 'memory');
  assert.equal(opened.search, '?mode=fixture&space=memory');
  assert.equal(readSpaceFromURL(opened), 'memory');
  const closed = buildSpaceURL(opened, null);
  assert.equal(closed.search, '?mode=fixture');
  assert.equal(readSpaceFromURL('https://luminous.test/?space=memory-123'), null);
});

test('space router normalizes invalid URLs and follows popstate', () => {
  const windowRef = fakeWindow('https://luminous.test/?mode=fixture&space=unknown');
  const spaces = [];
  let renders = 0;
  const router = initSpaceRouter(windowRef, { setSpace: (space) => spaces.push(space), onStateChange: () => { renders += 1; } });
  assert.equal(router.applyInitial(), null);
  assert.equal(windowRef.location.search, '?mode=fixture');
  router.navigate('privacy');
  assert.equal(windowRef.location.search, '?mode=fixture&space=privacy');
  windowRef.dispatchEvent(new Event('popstate'));
  assert.equal(spaces.at(-1), 'privacy');
  assert.equal(renders, 1);
  router.destroy();
});

test('PWA install appears only after browser eligibility and update waits for consent', async () => {
  const windowRef = fakeWindow();
  const serviceWorker = new EventTarget();
  serviceWorker.controller = {};
  const messages = [];
  const waiting = { postMessage: (message) => messages.push(message) };
  const registration = new EventTarget();
  registration.waiting = waiting;
  registration.installing = null;
  serviceWorker.register = async () => registration;
  const navigatorRef = { serviceWorker, standalone: false };
  const dom = {
    body: { dataset: {} },
    installSection: { hidden: true }, installButton: new FakeButton(),
    updateButton: new FakeButton(), updateText: { textContent: '' },
  };
  let reloads = 0;
  const controller = initPwaExperience(dom, { windowRef, navigatorRef, reload: () => { reloads += 1; } });
  await controller.ready;
  controller.render();
  assert.equal(dom.installSection.hidden, true);
  assert.equal(dom.updateButton.hidden, false);
  windowRef.dispatchEvent(new Event('offline'));
  controller.render();
  assert.equal(dom.body.dataset.network, 'offline');

  let prompts = 0;
  const available = new Event('beforeinstallprompt', { cancelable: true });
  available.prompt = async () => { prompts += 1; };
  available.userChoice = Promise.resolve({ outcome: 'accepted' });
  windowRef.dispatchEvent(available);
  controller.render();
  assert.equal(dom.installSection.hidden, false);
  dom.installButton.click();
  await Promise.resolve();
  assert.equal(prompts, 1);

  dom.updateButton.click();
  assert.deepEqual(messages, [{ type: 'SKIP_WAITING' }]);
  serviceWorker.dispatchEvent(new Event('controllerchange'));
  assert.equal(reloads, 1);
  controller.destroy();
});

test('native Android runtime does not register a PWA service worker', async () => {
  const windowRef = fakeWindow('https://localhost/');
  windowRef.__LUMINOUS_NATIVE__ = true;
  const serviceWorker = new EventTarget();
  let registrations = 0;
  serviceWorker.register = async () => { registrations += 1; return {}; };

  const controller = initPwaExperience({}, {
    windowRef,
    navigatorRef: { serviceWorker, standalone: false, onLine: true },
  });
  await controller.ready;

  assert.equal(registrations, 0);
  controller.destroy();
});
