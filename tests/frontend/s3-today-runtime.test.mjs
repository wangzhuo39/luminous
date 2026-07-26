import test from 'node:test';
import assert from 'node:assert/strict';

import { getState, initializeState } from '../../apps/companion-web/companion-ui/js/app-state.js';
import { initLifeFlow } from '../../apps/companion-web/companion-ui/js/features/life-flow/life-flow-controller.js';

const flush = () => new Promise((resolve) => setImmediate(resolve));

function setup() {
  initializeState(null);
  const dom = {
    portal: new EventTarget(),
    refresh: new EventTarget(),
    todayRetry: new EventTarget(),
    timelineReveal: new EventTarget(),
    timelineBack: new EventTarget(),
    timelineRetry: new EventTarget(),
    dialog: { open: true },
  };
  const pending = { today: [], timeline: [] };
  const controlledRequest = (queue, signal) => new Promise((resolve, reject) => {
    queue.push({ resolve, reject, signal });
    signal.addEventListener('abort', () => reject({ kind: 'cancelled' }), { once: true });
  });
  const dataSource = {
    loadToday: ({ signal }) => controlledRequest(pending.today, signal),
    loadTimeline: ({ signal }) => controlledRequest(pending.timeline, signal),
  };
  let online = true;
  const eventTarget = new EventTarget();
  const announcements = [];
  let changes = 0;
  const controller = initLifeFlow(dom, {
    dataSource,
    announce: (message) => announcements.push(message),
    onStateChange: () => { changes += 1; },
    eventTarget,
    isOnline: () => online,
  });
  return {
    dom,
    pending,
    controller,
    eventTarget,
    announcements,
    getChanges: () => changes,
    setOnline: (value) => { online = value; },
  };
}

test('AppState starts unloaded and stores only isolated Today whitelist data', async (t) => {
  const { dom, pending, controller } = setup();
  t.after(() => controller.destroy());
  const initialLifeFlow = getState().lifeFlow;
  assert.equal(initialLifeFlow.view, 'today');
  assert.deepEqual(initialLifeFlow.today, { status: 'unloaded', data: null, error: null });
  assert.deepEqual(initialLifeFlow.timeline, { status: 'unloaded', items: [], error: null });

  dom.portal.dispatchEvent(new Event('click'));
  const raw = {
    date: '2026-07-25',
    raw: 'drop-me',
    private: { diagnosis: 'drop-me' },
    activeActivities: [{
      key: 'activity-1', kind: 'activity', title: '静静休息', status: 'active',
      occurredAt: '2026-07-25T15:00:00+08:00', description: 'drop-me',
    }],
  };
  pending.today[0].resolve(raw);
  await flush();

  const stored = getState().lifeFlow.today;
  assert.equal(stored.status, 'ready');
  assert.deepEqual(stored.data.activeActivities[0], {
    key: 'activity-1', kind: 'activity', title: '静静休息', status: 'active',
    occurredAt: '2026-07-25T15:00:00+08:00',
  });
  assert.doesNotMatch(JSON.stringify(stored), /drop-me|diagnosis|description|private/);
  raw.activeActivities[0].title = '外部突变';
  assert.equal(getState().lifeFlow.today.data.activeActivities[0].title, '静静休息');
  assert.equal(getState().lifeFlow.timeline.status, 'unloaded');
});

test('refresh keeps cached Today data when a retryable request fails', async (t) => {
  const { dom, pending, controller } = setup();
  t.after(() => controller.destroy());
  dom.portal.dispatchEvent(new Event('click'));
  pending.today[0].resolve({ date: '2026-07-25' });
  await flush();

  dom.refresh.dispatchEvent(new Event('click'));
  let current = getState().lifeFlow.today;
  assert.equal(current.status, 'refreshing');
  assert.equal(current.data.date, '2026-07-25');
  pending.today[1].reject({ kind: 'server' });
  await flush();

  current = getState().lifeFlow.today;
  assert.equal(current.status, 'error');
  assert.equal(current.error.kind, 'server');
  assert.equal(current.error.retryable, true);
  assert.equal(current.data.date, '2026-07-25');
});

test('controller lazily loads Today once and loads Timeline only after explicit reveal', async (t) => {
  const { dom, pending, controller } = setup();
  t.after(() => controller.destroy());
  assert.equal(pending.today.length, 0);
  assert.equal(pending.timeline.length, 0);

  dom.portal.dispatchEvent(new Event('click'));
  assert.equal(pending.today.length, 1);
  pending.today[0].resolve({ date: '2026-07-25' });
  await flush();
  dom.portal.dispatchEvent(new Event('click'));
  assert.equal(pending.today.length, 1);

  dom.timelineReveal.dispatchEvent(new Event('click'));
  assert.equal(getState().lifeFlow.view, 'timeline');
  assert.equal(pending.timeline.length, 1);
  pending.timeline[0].resolve([{
    key: 'timeline-1', kind: 'task', title: '已经完成', status: 'completed',
    occurredAt: '2026-07-25T10:00:00+08:00', source_id: 'drop-me',
  }]);
  await flush();
  assert.equal(getState().lifeFlow.timeline.status, 'ready');
  assert.doesNotMatch(JSON.stringify(getState().lifeFlow.timeline), /source_id|drop-me/);

  dom.timelineBack.dispatchEvent(new Event('click'));
  assert.equal(getState().lifeFlow.view, 'today');
  assert.equal(pending.today.length, 1);
  dom.timelineReveal.dispatchEvent(new Event('click'));
  assert.equal(pending.timeline.length, 1);
});

test('operation gate rejects duplicate refresh while the current request is pending', async (t) => {
  const { dom, pending, controller } = setup();
  t.after(() => controller.destroy());
  dom.portal.dispatchEvent(new Event('click'));
  dom.refresh.dispatchEvent(new Event('click'));
  dom.refresh.dispatchEvent(new Event('click'));
  assert.equal(pending.today.length, 1);
  pending.today[0].resolve({ date: '2026-07-25' });
  await flush();
  assert.equal(getState().lifeFlow.today.status, 'ready');
});

test('offline aborts pending visible load and online recovery requires an open dialog', async (t) => {
  const { dom, pending, controller, eventTarget, setOnline } = setup();
  t.after(() => controller.destroy());
  dom.portal.dispatchEvent(new Event('click'));
  setOnline(false);
  eventTarget.dispatchEvent(new Event('offline'));
  assert.equal(pending.today[0].signal.aborted, true);
  await flush();
  let current = getState().lifeFlow.today;
  assert.equal(current.status, 'error');
  assert.equal(current.error.kind, 'offline');
  assert.equal(current.error.retryable, true);

  setOnline(true);
  dom.dialog.open = false;
  eventTarget.dispatchEvent(new Event('online'));
  assert.equal(pending.today.length, 1);
  dom.dialog.open = true;
  eventTarget.dispatchEvent(new Event('online'));
  assert.equal(pending.today.length, 2);
});

test('destroy removes listeners, aborts work and ignores late completion', async () => {
  const { dom, pending, controller } = setup();
  dom.portal.dispatchEvent(new Event('click'));
  controller.destroy();
  assert.equal(pending.today[0].signal.aborted, true);
  pending.today[0].resolve({ date: '2026-07-25' });
  await flush();
  assert.equal(getState().lifeFlow.today.data, null);
  dom.portal.dispatchEvent(new Event('click'));
  assert.equal(pending.today.length, 1);
});
