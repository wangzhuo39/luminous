import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getState,
  initializeState,
} from '../../apps/companion-web/companion-ui/js/app-state.js';
import { initLifeFlow } from '../../apps/companion-web/companion-ui/js/features/life-flow/life-flow-controller.js';

const flush = () => new Promise((resolve) => setImmediate(resolve));

function setup() {
  initializeState(null);
  const methodNames = [
    'loadToday', 'loadTimeline', 'loadTasks', 'createTask', 'updateTask',
    'addTaskStep', 'updateTaskStep', 'transitionTask', 'archiveTask',
    'loadRoutines', 'createRoutine', 'updateRoutine', 'checkinRoutine', 'deactivateRoutine',
  ];
  const pending = Object.fromEntries(methodNames.map((name) => [name, []]));
  const dataSource = Object.fromEntries(methodNames.map((name) => [name, (params = {}) => (
    new Promise((resolve, reject) => {
      const call = { params, resolve, reject };
      pending[name].push(call);
      params.signal?.addEventListener(
        'abort',
        () => reject({ kind: 'cancelled', retryable: false }),
        { once: true },
      );
    })
  )]));
  const dom = { dialog: { open: true } };
  const eventTarget = new EventTarget();
  const announcements = [];
  let changes = 0;
  const controller = initLifeFlow(dom, {
    dataSource,
    eventTarget,
    announce: (message) => announcements.push(message),
    onStateChange: () => { changes += 1; },
    isOnline: () => true,
  });
  return { controller, pending, eventTarget, announcements, getChanges: () => changes };
}

const task = (overrides = {}) => ({
  key: 'task-safe-1',
  title: '整理桌面',
  description: '只整理眼前这一小块',
  status: 'open',
  dueAt: null,
  priority: 'normal',
  steps: [],
  ...overrides,
});

const routine = (overrides = {}) => ({
  key: 'routine-safe-1',
  title: '喝一杯水',
  schedule: 'daily',
  active: true,
  reminderPolicy: 'none',
  ...overrides,
});

test('resource lists load lazily, reject duplicate loads and keep exact query shapes', async (t) => {
  const { controller, pending } = setup();
  t.after(() => controller.destroy());

  controller.openTasks();
  controller.openTasks();
  assert.equal(pending.loadTasks.length, 1);
  assert.equal(pending.loadTasks[0].params.limit, 100);
  assert.equal(getState().lifeFlow.tasks.status, 'loading');
  pending.loadTasks[0].resolve([task()]);
  await flush();
  assert.equal(getState().lifeFlow.tasks.status, 'ready');
  assert.equal(getState().lifeFlow.tasks.items[0].title, '整理桌面');

  controller.openRoutines();
  assert.equal(pending.loadRoutines.length, 1);
  assert.equal(pending.loadRoutines[0].params.activeOnly, false);
  assert.equal(pending.loadRoutines[0].params.limit, 100);
  pending.loadRoutines[0].resolve([routine()]);
  await flush();
  assert.equal(getState().lifeFlow.routines.status, 'ready');
});

test('Task create maps the local draft to the API shape and blocks double submit', async (t) => {
  const { controller, pending } = setup();
  t.after(() => controller.destroy());
  controller.openTasks();
  pending.loadTasks[0].resolve([]);
  await flush();

  controller.handleTaskEvent({ type: 'CREATE' });
  controller.handleTaskEvent({ type: 'FIELD', field: 'title', value: '  给植物浇水  ' });
  controller.handleTaskEvent({ type: 'FIELD', field: 'description', value: '保留空白' });
  controller.handleTaskEvent({ type: 'FIELD', field: 'dueAt', value: '2026-07-27T09:30' });
  controller.handleTaskEvent({ type: 'FIELD', field: 'priority', value: 'high' });
  const first = controller.handleTaskEvent({ type: 'SUBMIT' });
  const duplicate = await controller.handleTaskEvent({ type: 'SUBMIT' });

  assert.equal(duplicate, false);
  assert.equal(pending.createTask.length, 1);
  const input = pending.createTask[0].params.input;
  assert.equal(input.title, '  给植物浇水  ');
  assert.equal(input.description, '保留空白');
  assert.equal(input.priority, 'high');
  assert.match(input.due_at, /^2026-07-27T/);
  assert.equal(Object.hasOwn(input, 'dueAt'), false);

  pending.createTask[0].resolve(task({ key: 'task-safe-2', title: '给植物浇水', priority: 'high' }));
  assert.equal(await first, true);
  assert.equal(getState().lifeFlow.view, 'task-detail');
  assert.equal(getState().lifeFlow.tasks.items.length, 1);
  assert.equal(pending.loadToday.length, 1);
});

test('invalid Task draft never reaches DataSource and restores its exact snapshot', async (t) => {
  const { controller, pending } = setup();
  t.after(() => controller.destroy());
  controller.openTasks();
  pending.loadTasks[0].resolve([]);
  await flush();
  controller.handleTaskEvent({ type: 'CREATE' });
  controller.handleTaskEvent({ type: 'FIELD', field: 'title', value: '   ' });
  controller.handleTaskEvent({ type: 'FIELD', field: 'description', value: '  原样保留  ' });

  assert.equal(await controller.handleTaskEvent({ type: 'SUBMIT' }), false);
  assert.equal(pending.createTask.length, 0);
  const editor = getState().lifeFlow.tasks.editor;
  assert.equal(editor.status, 'error');
  assert.equal(editor.error.kind, 'validation');
  assert.equal(editor.draft.title, '   ');
  assert.equal(editor.draft.description, '  原样保留  ');
});

test('Task transitions, archive confirmation and step writes use only selected safe keys', async (t) => {
  const { controller, pending } = setup();
  t.after(() => controller.destroy());
  const initialStep = {
    key: 'step-safe-1', title: '收起杯子', position: 0, status: 'open', completedAt: null,
  };
  controller.openTasks();
  pending.loadTasks[0].resolve([task({
    steps: [initialStep],
  })]);
  await flush();
  controller.handleTaskEvent({ type: 'SELECT', index: 0 });

  const transition = controller.handleTaskEvent({ type: 'TRANSITION', action: 'start' });
  assert.equal(pending.transitionTask.length, 1);
  assert.deepEqual(
    { ...pending.transitionTask[0].params, signal: undefined },
    { key: 'task-safe-1', action: 'start', input: {}, signal: undefined },
  );
  pending.transitionTask[0].resolve(task({ status: 'in_progress', steps: [initialStep] }));
  assert.equal(await transition, true);

  controller.handleTaskEvent({ type: 'STEP_FIELD', value: '擦一擦桌角' });
  const add = controller.handleTaskEvent({ type: 'STEP_ADD' });
  assert.equal(pending.addTaskStep.length, 1);
  assert.equal(pending.addTaskStep[0].params.taskKey, 'task-safe-1');
  assert.deepEqual(pending.addTaskStep[0].params.input, { title: '擦一擦桌角' });
  pending.addTaskStep[0].resolve({
    key: 'step-safe-2', title: '擦一擦桌角', position: 1, status: 'open', completedAt: null,
  });
  assert.equal(await add, true);

  const toggle = controller.handleTaskEvent({ type: 'STEP_TOGGLE', index: 0 });
  assert.equal(pending.updateTaskStep[0].params.stepKey, 'step-safe-1');
  assert.deepEqual(pending.updateTaskStep[0].params.changes, { status: 'completed' });
  pending.updateTaskStep[0].resolve({
    key: 'step-safe-1', title: '收起杯子', position: 0,
    status: 'completed', completedAt: '2026-07-26T10:00:00Z',
  });
  assert.equal(await toggle, true);

  assert.equal(await controller.handleTaskEvent({ type: 'ARCHIVE_CONFIRM' }), false);
  controller.handleTaskEvent({ type: 'ARCHIVE_INTENT' });
  const archive = controller.handleTaskEvent({ type: 'ARCHIVE_CONFIRM' });
  assert.equal(pending.archiveTask.length, 1);
  assert.equal(await controller.handleTaskEvent({ type: 'ARCHIVE_CONFIRM' }), false);
  pending.archiveTask[0].resolve(task({ status: 'archived' }));
  assert.equal(await archive, true);
  assert.equal(getState().lifeFlow.tasks.items[0].status, 'archived');
});

test('Routine create, check-in and deactivate preserve contract names and confirmation gates', async (t) => {
  const { controller, pending } = setup();
  t.after(() => controller.destroy());
  controller.openRoutines();
  pending.loadRoutines[0].resolve([routine()]);
  await flush();

  controller.handleRoutineEvent({ type: 'CREATE' });
  controller.handleRoutineEvent({ type: 'FIELD', field: 'title', value: '晚间伸展' });
  controller.handleRoutineEvent({ type: 'FIELD', field: 'schedule', value: 'weekly' });
  controller.handleRoutineEvent({ type: 'FIELD', field: 'reminderPolicy', value: 'remind' });
  const create = controller.handleRoutineEvent({ type: 'SUBMIT' });
  assert.deepEqual(
    { ...pending.createRoutine[0].params.input },
    { title: '晚间伸展', schedule: 'weekly', reminder_policy: 'remind', active: true },
  );
  pending.createRoutine[0].resolve(routine({ key: 'routine-safe-2', title: '晚间伸展' }));
  assert.equal(await create, true);

  const checkin = controller.handleRoutineEvent({ type: 'CHECKIN' });
  assert.equal(pending.checkinRoutine.length, 1);
  assert.equal(pending.checkinRoutine[0].params.key, 'routine-safe-2');
  assert.deepEqual(pending.checkinRoutine[0].params.input, {});
  assert.equal(Object.hasOwn(pending.checkinRoutine[0].params, 'date'), false);
  assert.equal(await controller.handleRoutineEvent({ type: 'CHECKIN' }), false);
  pending.checkinRoutine[0].resolve({ key: 'checkin-safe-1', periodKey: '2026-07-26' });
  assert.equal(await checkin, true);
  assert.equal(getState().lifeFlow.routines.items[1].checkinStatus, 'completed');
  assert.equal(await controller.handleRoutineEvent({ type: 'CHECKIN' }), false);

  assert.equal(await controller.handleRoutineEvent({ type: 'DEACTIVATE_CONFIRM' }), false);
  controller.handleRoutineEvent({ type: 'DEACTIVATE_INTENT' });
  const deactivate = controller.handleRoutineEvent({ type: 'DEACTIVATE_CONFIRM' });
  assert.equal(pending.deactivateRoutine[0].params.key, 'routine-safe-2');
  pending.deactivateRoutine[0].resolve(routine({
    key: 'routine-safe-2', title: '晚间伸展', active: false,
  }));
  assert.equal(await deactivate, true);
  assert.equal(getState().lifeFlow.routines.items[1].active, false);
});

test('offline aborts an editor write and restores the exact pending draft', async (t) => {
  const { controller, pending, eventTarget } = setup();
  t.after(() => controller.destroy());
  controller.openTasks();
  pending.loadTasks[0].resolve([]);
  await flush();
  controller.handleTaskEvent({ type: 'CREATE' });
  controller.handleTaskEvent({ type: 'FIELD', field: 'title', value: '  不丢空白  ' });
  const submit = controller.handleTaskEvent({ type: 'SUBMIT' });
  assert.equal(getState().lifeFlow.tasks.editor.status, 'pending');

  eventTarget.dispatchEvent(new Event('offline'));
  await flush();
  assert.equal(await submit, false);
  assert.equal(pending.createTask[0].params.signal.aborted, true);
  const editor = getState().lifeFlow.tasks.editor;
  assert.equal(editor.status, 'error');
  assert.equal(editor.error.kind, 'offline');
  assert.equal(editor.draft.title, '  不丢空白  ');
});
