import test from 'node:test';
import assert from 'node:assert/strict';

import {
  beginResourceLoad,
  beginResourceWrite,
  completeResourceLoad,
  completeResourceWrite,
  failResourceWrite,
  getState,
  initializeState,
  openResourceEditor,
  selectResourceItem,
  updateResourceDraft,
} from '../../apps/companion-web/companion-ui/js/app-state.js';
import { initLifeFlow } from '../../apps/companion-web/companion-ui/js/features/life-flow/life-flow-controller.js';

const flush = () => new Promise((resolve) => setImmediate(resolve));

const activity = (overrides = {}) => ({
  key: 'activity-safe-1',
  kind: 'focus',
  title: '安静读一会儿',
  status: 'planned',
  startedAt: null,
  endedAt: null,
  summary: null,
  ...overrides,
});

test('Activity AppState whitelists fields and enforces the exact transition graph', () => {
  initializeState(null);
  assert.deepEqual(getState().lifeFlow.activities.editor.draft, { title: '', kind: 'focus' });
  assert.equal(beginResourceLoad('activities'), true);
  assert.equal(completeResourceLoad('activities', [activity({
    diagnosis: 'drop', metadata: { private: true },
  })]), true);
  assert.doesNotMatch(JSON.stringify(getState().lifeFlow.activities), /diagnosis|metadata|private/);
  assert.equal(selectResourceItem('activities', 'activity-safe-1'), true);
  assert.equal(openResourceEditor('activities', 'edit'), false);
  assert.equal(beginResourceWrite('activities', 'transition', 'pause'), null);
  assert.deepEqual(beginResourceWrite('activities', 'transition', 'start'), {});
  assert.equal(beginResourceWrite('activities', 'transition', 'cancel'), null);
  assert.equal(completeResourceWrite('activities', activity({ status: 'active' })), true);
  assert.equal(getState().lifeFlow.activities.items[0].status, 'active');

  assert.equal(beginResourceWrite('activities', 'transition', 'resume'), null);
  assert.deepEqual(beginResourceWrite('activities', 'transition', 'pause'), {});
  assert.equal(failResourceWrite('activities', { kind: 'server', private: 'drop' }), true);
  const state = getState().lifeFlow.activities;
  assert.equal(state.items[0].status, 'active');
  assert.equal(state.action.error.kind, 'server');
  assert.doesNotMatch(JSON.stringify(state.action), /private|drop/);
});

test('Activity create preserves its exact draft on failure and accepts only safe response data', () => {
  initializeState(null);
  assert.equal(beginResourceLoad('activities'), true);
  assert.equal(completeResourceLoad('activities', []), true);
  assert.equal(openResourceEditor('activities', 'create'), true);
  assert.equal(updateResourceDraft('activities', 'title', '  一起整理思路  '), true);
  assert.equal(updateResourceDraft('activities', 'kind', 'planning'), true);
  assert.equal(updateResourceDraft('activities', 'kind', 'exercise'), false);
  assert.deepEqual(beginResourceWrite('activities', 'create'), {
    title: '  一起整理思路  ', kind: 'planning',
  });
  assert.equal(updateResourceDraft('activities', 'title', '不能覆盖'), false);
  assert.equal(failResourceWrite('activities', { kind: 'offline' }), true);
  let editor = getState().lifeFlow.activities.editor;
  assert.deepEqual(editor.draft, { title: '  一起整理思路  ', kind: 'planning' });

  assert.ok(beginResourceWrite('activities', 'create'));
  assert.equal(completeResourceWrite('activities', activity({
    key: 'activity-safe-2', title: '一起整理思路', kind: 'planning', raw: 'drop',
  })), true);
  const current = getState().lifeFlow;
  assert.equal(current.view, 'activity-detail');
  assert.equal(current.activities.items.length, 1);
  assert.doesNotMatch(JSON.stringify(current.activities.items[0]), /raw|drop/);
});

test('Activity terminal, expired and unknown states are read-only', () => {
  initializeState(null);
  assert.equal(beginResourceLoad('activities'), true);
  assert.equal(completeResourceLoad('activities', [
    activity({ key: 'activity-completed', status: 'completed' }),
    activity({ key: 'activity-cancelled', status: 'cancelled' }),
    activity({ key: 'activity-expired', status: 'expired' }),
    activity({ key: 'activity-unknown', status: 'invented', kind: 'invented' }),
  ]), true);
  for (const [key, expectedStatus] of [
    ['activity-completed', 'completed'],
    ['activity-cancelled', 'cancelled'],
    ['activity-expired', 'expired'],
    ['activity-unknown', 'unknown'],
  ]) {
    assert.equal(selectResourceItem('activities', key), true);
    assert.equal(getState().lifeFlow.activities.items.find((item) => item.key === key).status, expectedStatus);
    for (const action of ['start', 'pause', 'resume', 'complete', 'cancel']) {
      assert.equal(beginResourceWrite('activities', 'transition', action), null);
    }
  }
  const unknown = getState().lifeFlow.activities.items.at(-1);
  assert.equal(unknown.kind, 'unknown');
});

function setupController() {
  initializeState(null);
  const methodNames = [
    'loadToday', 'loadTimeline', 'loadTasks', 'createTask', 'updateTask',
    'addTaskStep', 'updateTaskStep', 'transitionTask', 'archiveTask',
    'loadRoutines', 'createRoutine', 'updateRoutine', 'checkinRoutine', 'deactivateRoutine',
    'loadActivities', 'createActivity', 'transitionActivity',
  ];
  const pending = Object.fromEntries(methodNames.map((name) => [name, []]));
  const dataSource = Object.fromEntries(methodNames.map((name) => [name, (params = {}) => (
    new Promise((resolve, reject) => {
      pending[name].push({ params, resolve, reject });
      params.signal?.addEventListener(
        'abort', () => reject({ kind: 'cancelled', retryable: false }), { once: true },
      );
    })
  )]));
  const controller = initLifeFlow({ dialog: { open: true } }, {
    dataSource,
    eventTarget: new EventTarget(),
    announce: () => {},
    onStateChange: () => {},
    isOnline: () => true,
  });
  return { controller, pending };
}

test('Activity controller uses exact list/create/transition requests and blocks illegal actions', async (t) => {
  const { controller, pending } = setupController();
  t.after(() => controller.destroy());

  controller.openActivities();
  controller.openActivities();
  assert.equal(pending.loadActivities.length, 1);
  assert.equal(pending.loadActivities[0].params.limit, 100);
  assert.equal(Object.hasOwn(pending.loadActivities[0].params, 'status'), false);
  pending.loadActivities[0].resolve([]);
  await flush();

  controller.handleActivityEvent({ type: 'CREATE' });
  controller.handleActivityEvent({ type: 'FIELD', field: 'title', value: '  一起梳理明天  ' });
  controller.handleActivityEvent({ type: 'FIELD', field: 'kind', value: 'planning' });
  const creating = controller.handleActivityEvent({ type: 'SUBMIT' });
  assert.deepEqual(pending.createActivity[0].params.input, {
    title: '  一起梳理明天  ', kind: 'planning',
  });
  assert.equal(await controller.handleActivityEvent({ type: 'SUBMIT' }), false);
  pending.createActivity[0].resolve(activity({
    key: 'activity-safe-2', title: '一起梳理明天', kind: 'planning',
  }));
  assert.equal(await creating, true);

  assert.equal(await controller.handleActivityEvent({ type: 'TRANSITION', action: 'pause' }), false);
  assert.equal(pending.transitionActivity.length, 0);
  const starting = controller.handleActivityEvent({ type: 'TRANSITION', action: 'start' });
  assert.deepEqual(
    { ...pending.transitionActivity[0].params, signal: undefined },
    { key: 'activity-safe-2', action: 'start', input: {}, signal: undefined },
  );
  pending.transitionActivity[0].resolve(activity({
    key: 'activity-safe-2', title: '一起梳理明天', kind: 'planning', status: 'active',
  }));
  assert.equal(await starting, true);
  assert.equal(getState().lifeFlow.activities.items[0].status, 'active');
  assert.equal(pending.loadToday.length, 1);
});
