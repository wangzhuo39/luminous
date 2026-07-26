import test from 'node:test';
import assert from 'node:assert/strict';

import { getState, initializeState } from '../../apps/companion-web/companion-ui/js/app-state.js';
import { initCoreRuntime } from '../../apps/companion-web/companion-ui/js/core-runtime.js';

function fixture() {
  return {
    scene: { caption: 'fixture scene', tone: 'calm' },
    conversation: { messages: [], localReply: null },
    today: { date: '', summaryItems: [] },
    outbox: { unreadCount: 0, arrivals: [] },
    memoryPrivacy: { memoryPrompt: '', privacyCaption: '', boundaryStatus: '' },
  };
}

function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

function dependencies(fetchImpl) {
  return {
    fetchImpl,
    isOnline: () => true,
    setTimer: () => 1,
    clearTimer: () => {},
  };
}

test('fixture runtime never calls the API', async () => {
  initializeState(fixture(), { runtimeMode: 'fixture' });
  let calls = 0;
  const runtime = initCoreRuntime({
    mode: 'fixture',
    announce() {},
    onStateChange() {},
    eventTarget: new EventTarget(),
    dependencies: dependencies(async () => { calls += 1; }),
  });
  assert.equal(await runtime.retryStateLoad(), false);
  assert.equal(calls, 0);
  assert.equal(getState().appStatus, 'fixture');
  runtime.destroy();
});

test('API runtime exposes only adapted scene state after initial load', async () => {
  initializeState(fixture(), { runtimeMode: 'api' });
  const announcements = [];
  const runtime = initCoreRuntime({
    mode: 'api',
    announce: (message) => announcements.push(message),
    onStateChange() {},
    eventTarget: new EventTarget(),
    dependencies: dependencies(async () => response({
      state: { mood: 'warm', private_diagnosis: 'must-not-leak' },
      memory: { raw: 'must-not-leak' },
    })),
  });
  await new Promise((resolve) => setImmediate(resolve));
  const current = getState();
  assert.equal(current.appStatus, 'ready');
  assert.deepEqual(current.viewModels.scene, { caption: '我在，光线也暖了一些。', tone: 'warm' });
  assert.doesNotMatch(JSON.stringify(current), /private_diagnosis|must-not-leak|memory.*raw/);
  assert.deepEqual(announcements, ['正在靠近栖光。', '栖光已经在这里。']);
  runtime.destroy();
});

test('retry ignores a superseded request even if it resolves later', async () => {
  initializeState(fixture(), { runtimeMode: 'api' });
  const pending = [];
  const runtime = initCoreRuntime({
    mode: 'api',
    announce() {},
    onStateChange() {},
    eventTarget: new EventTarget(),
    dependencies: dependencies((path, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
      pending.push({ resolve, reject });
    })),
  });
  assert.equal(pending.length, 1);
  const retry = runtime.retryStateLoad();
  assert.equal(pending.length, 2);
  pending[1].resolve(response({ state: { mood: 'quiet' } }));
  assert.equal(await retry, true);
  assert.deepEqual(getState().viewModels.scene, { caption: '我在这里，陪你慢一点。', tone: 'quiet' });
  pending[0].resolve(response({ state: { mood: 'warm' } }));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(getState().viewModels.scene.tone, 'quiet');
  runtime.destroy();
});

test('offline transition aborts loading and keeps the fixture scene intact', async () => {
  initializeState(fixture(), { runtimeMode: 'api' });
  const events = new EventTarget();
  const runtime = initCoreRuntime({
    mode: 'api',
    announce() {},
    onStateChange() {},
    eventTarget: events,
    dependencies: dependencies((path, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
    })),
  });
  events.dispatchEvent(new Event('offline'));
  await new Promise((resolve) => setImmediate(resolve));
  const current = getState();
  assert.equal(current.appStatus, 'offline');
  assert.deepEqual(current.viewModels.scene, { caption: 'fixture scene', tone: 'calm' });
  runtime.destroy();
});
