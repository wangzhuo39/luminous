import test from 'node:test';
import assert from 'node:assert/strict';

import {
  beginResourceLoad,
  beginResourceWrite,
  beginTaskStepWrite,
  completeResourceLoad,
  completeResourceWrite,
  completeRoutineCheckin,
  completeTaskStepWrite,
  failResourceLoad,
  failResourceWrite,
  failTaskStepWrite,
  getState,
  initializeState,
  openResourceEditor,
  resetResourceSubview,
  selectResourceItem,
  setResourceConfirmation,
  showLifeFlowView,
  updateResourceDraft,
  updateTaskStepDraft,
} from '../../apps/companion-web/companion-ui/js/app-state.js';

const task = (overrides = {}) => ({
  key: 'task-1',
  title: '安静完成一件事',
  description: '  保留空白\n第二行  ',
  status: 'open',
  dueAt: '2026-07-26T10:00:00+08:00',
  priority: 'normal',
  steps: [{ key: 'step-1', title: '第一步', status: 'open' }],
  ...overrides,
});

const routine = (overrides = {}) => ({
  key: 'routine-1',
  title: '喝一杯水',
  schedule: 'daily',
  active: true,
  reminderPolicy: 'none',
  ...overrides,
});

function reset() {
  initializeState(null);
}

function load(resource, items) {
  assert.equal(beginResourceLoad(resource), true);
  assert.equal(completeResourceLoad(resource, items), true);
}

test('resource slices initialize and reset independently from stable B3 state', () => {
  reset();
  let current = getState().lifeFlow;
  assert.equal(current.view, 'today');
  assert.deepEqual(current.tasks.items, []);
  assert.equal(current.tasks.status, 'unloaded');
  assert.deepEqual(current.tasks.editor.draft, {
    title: '', description: '', dueAt: null, priority: 'normal',
  });
  assert.deepEqual(current.routines.editor.draft, {
    title: '', schedule: 'daily', reminderPolicy: 'none', active: true,
  });
  load('tasks', [task()]);
  reset();
  current = getState().lifeFlow;
  assert.equal(current.tasks.status, 'unloaded');
  assert.equal(current.today.status, 'unloaded');
});

test('invalid resources, views, modes, fields and write kinds fail closed', () => {
  reset();
  assert.equal(showLifeFlowView('admin'), false);
  assert.equal(beginResourceLoad('unknown'), false);
  assert.equal(completeResourceLoad('tasks', []), false);
  assert.equal(failResourceLoad('routines', { kind: 'server' }), false);
  assert.equal(selectResourceItem('tasks', 'missing'), false);
  assert.equal(openResourceEditor('tasks', 'remove'), false);
  assert.equal(updateResourceDraft('tasks', 'priority', 'urgent'), false);
  assert.equal(updateResourceDraft('routines', 'schedule', 'monthly'), false);
  assert.equal(beginResourceWrite('tasks', 'delete'), null);
});

test('Task load keeps only strict safe fields and is mutation-isolated', () => {
  reset();
  const raw = task({
    raw: 'drop', private: { diagnosis: 'drop' }, metadata: { source: 'drop' },
    status: 'super_urgent', priority: 'urgent',
    dueAt: '2026-07-26T10:00:00',
    steps: [
      { key: 'step-1', title: '第一步', status: 'mystery', raw: 'drop' },
      { key: '', title: 'invalid', status: 'open' },
    ],
  });
  load('tasks', [raw, { title: 'no key' }]);
  const stored = getState().lifeFlow.tasks.items;
  assert.equal(stored.length, 1);
  assert.deepEqual(stored[0], {
    key: 'task-1',
    title: '安静完成一件事',
    description: '  保留空白\n第二行  ',
    status: 'unknown',
    dueAt: null,
    priority: 'normal',
    steps: [{ key: 'step-1', title: '第一步', status: 'unknown' }],
  });
  assert.doesNotMatch(JSON.stringify(getState()), /diagnosis|metadata|drop/);
  raw.title = '外部突变';
  assert.equal(getState().lifeFlow.tasks.items[0].title, '安静完成一件事');
});

test('Routine load validates enums and preserves only completed session checkin on refresh', () => {
  reset();
  load('routines', [routine()]);
  assert.equal(selectResourceItem('routines', 'routine-1'), true);
  assert.deepEqual(beginResourceWrite('routines', 'checkin'), {});
  assert.equal(beginResourceWrite('routines', 'checkin'), null);
  assert.equal(completeRoutineCheckin(), true);
  assert.equal(getState().lifeFlow.routines.items[0].checkinStatus, 'completed');

  assert.equal(beginResourceLoad('routines', true), true);
  assert.equal(completeResourceLoad('routines', [routine({
    schedule: 'monthly', reminderPolicy: 'always', raw: 'drop',
  })]), true);
  const stored = getState().lifeFlow.routines.items[0];
  assert.equal(stored.schedule, 'unknown');
  assert.equal(stored.reminderPolicy, 'unknown');
  assert.equal(stored.checkinStatus, 'completed');
  assert.doesNotMatch(JSON.stringify(stored), /raw|drop/);
});

test('editor pending blocks changes and failure restores exact Task draft', () => {
  reset();
  load('tasks', [task()]);
  assert.equal(selectResourceItem('tasks', 'task-1'), true);
  assert.equal(openResourceEditor('tasks', 'edit'), true);
  const exact = '  很长的说明\n\t保持原样  ';
  assert.equal(updateResourceDraft('tasks', 'description', exact), true);
  const snapshot = beginResourceWrite('tasks', 'edit');
  assert.equal(snapshot.description, exact);
  assert.equal(updateResourceDraft('tasks', 'description', '不能覆盖'), false);
  assert.equal(beginResourceWrite('tasks', 'edit'), null);
  assert.equal(failResourceWrite('tasks', {
    kind: 'server', detail: 'raw server detail', retryable: true,
  }), true);
  let editor = getState().lifeFlow.tasks.editor;
  assert.equal(editor.draft.description, exact);
  assert.equal(editor.error.message, '连接暂时不稳定。');
  assert.doesNotMatch(JSON.stringify(editor), /raw server detail/);

  assert.ok(beginResourceWrite('tasks', 'edit'));
  assert.equal(failResourceWrite('tasks', { kind: 'cancelled' }), true);
  editor = getState().lifeFlow.tasks.editor;
  assert.equal(editor.status, 'idle');
  assert.equal(editor.error, null);
});

test('create appends safely while invalid or mismatched writes cannot fake success', () => {
  reset();
  load('tasks', [task()]);
  assert.equal(openResourceEditor('tasks', 'create'), true);
  updateResourceDraft('tasks', 'title', '新任务');
  assert.ok(beginResourceWrite('tasks', 'create'));
  assert.equal(completeResourceWrite('tasks', task({ key: 'task-2', title: '新任务' })), true);
  assert.equal(getState().lifeFlow.tasks.items.length, 2);
  assert.equal(getState().lifeFlow.view, 'task-detail');

  assert.equal(openResourceEditor('tasks', 'edit'), true);
  assert.ok(beginResourceWrite('tasks', 'edit'));
  assert.equal(completeResourceWrite('tasks', { key: 'task-2', title: '' }), false);
  assert.equal(getState().lifeFlow.tasks.editor.status, 'pending');
  assert.equal(failResourceWrite('tasks', { kind: 'server' }), true);

  assert.ok(beginResourceWrite('tasks', 'edit'));
  assert.equal(completeResourceWrite('tasks', task({ key: 'different' })), false);
  assert.equal(getState().lifeFlow.tasks.items[1].key, 'task-2');
});

test('archive and deactivate require the matching inline confirmation', () => {
  reset();
  load('tasks', [task()]);
  selectResourceItem('tasks', 'task-1');
  assert.equal(beginResourceWrite('tasks', 'archive'), null);
  assert.equal(setResourceConfirmation('tasks', 'deactivate', true), false);
  assert.equal(setResourceConfirmation('tasks', 'archive', true), true);
  assert.deepEqual(beginResourceWrite('tasks', 'archive'), {});

  reset();
  load('routines', [routine()]);
  selectResourceItem('routines', 'routine-1');
  assert.equal(beginResourceWrite('routines', 'deactivate'), null);
  assert.equal(setResourceConfirmation('routines', 'deactivate', true), true);
  assert.deepEqual(beginResourceWrite('routines', 'deactivate'), {});
});

test('Step add and toggle are locally gated and reject mismatched results', () => {
  reset();
  load('tasks', [task()]);
  selectResourceItem('tasks', 'task-1');
  assert.equal(updateTaskStepDraft('  新步骤  '), true);
  assert.deepEqual(beginTaskStepWrite(-1, 'add'), { title: '  新步骤  ' });
  assert.equal(beginTaskStepWrite(-1, 'add'), null);
  assert.equal(completeTaskStepWrite(-1, {
    key: 'step-2', title: '新步骤', status: 'open', raw: 'drop',
  }), true);
  assert.equal(getState().lifeFlow.tasks.items[0].steps.length, 2);
  assert.equal(getState().lifeFlow.tasks.stepDraft, '');

  assert.deepEqual(beginTaskStepWrite(0, 'toggle'), { status: 'completed' });
  assert.equal(completeTaskStepWrite(0, {
    key: 'wrong-step', title: '第一步', status: 'completed',
  }), false);
  assert.equal(failTaskStepWrite(0, { kind: 'offline', private: 'drop' }), true);
  const write = getState().lifeFlow.tasks.stepWrites.find(({ index }) => index === 0);
  assert.equal(write.status, 'error');
  assert.equal(write.error.kind, 'offline');
  assert.doesNotMatch(JSON.stringify(write), /private|drop/);
});

test('Routine checkin requires an active selection and pending checkin operation', () => {
  reset();
  assert.equal(completeRoutineCheckin(), false);
  load('routines', [routine({ active: false })]);
  selectResourceItem('routines', 'routine-1');
  assert.equal(beginResourceWrite('routines', 'checkin'), null);
  assert.equal(completeRoutineCheckin(), false);
});

test('reset clears transient state while preserving loaded resource caches', () => {
  reset();
  load('tasks', [task()]);
  selectResourceItem('tasks', 'task-1');
  openResourceEditor('tasks', 'edit');
  updateResourceDraft('tasks', 'title', '未保存草稿');
  assert.equal(resetResourceSubview('tasks'), true);
  const current = getState().lifeFlow;
  assert.equal(current.view, 'today');
  assert.equal(current.tasks.status, 'ready');
  assert.equal(current.tasks.items.length, 1);
  assert.equal(current.tasks.selectedIndex, null);
  assert.equal(current.tasks.editor.draft.title, '');
  assert.equal(resetResourceSubview('invalid'), false);
});
