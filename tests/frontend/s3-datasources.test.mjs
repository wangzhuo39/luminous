import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createApiLifeFlowDataSource,
} from '../../apps/companion-web/companion-ui/js/life-flow-datasource.js';
import {
  createFixtureLifeFlowDataSource,
} from '../../apps/companion-web/companion-ui/js/adapters/life-flow-fixture-adapter.js';
import { AppError } from '../../apps/companion-web/companion-ui/js/shared/errors.js';

const FIXED_NOW = () => new Date('2024-05-01T10:00:00Z');

test('API and fixture DataSources have the same frozen 32-method surface', () => {
  const apiDataSource = createApiLifeFlowDataSource();
  const fixtureDataSource = createFixtureLifeFlowDataSource();
  assert.equal(Object.keys(apiDataSource).length, 32);
  assert.deepEqual(Object.keys(apiDataSource), Object.keys(fixtureDataSource));
  assert.ok(Object.isFrozen(apiDataSource));
  assert.ok(Object.isFrozen(fixtureDataSource));
});

test('API DataSource adapts lists, writes, previews, and confirms without raw leakage', async () => {
  const rawInternal = { metadata: { secret: true }, user_scope: 'private', source: 'raw' };
  const fakeApi = new Proxy({}, {
    get: (_, method) => async (args) => {
      if (method === 'loadTasks') {
        return { items: [{ task_id: 'task-1', title: 'Safe task', ...rawInternal }] };
      }
      if (method === 'createTask') {
        return { task: { task_id: 'task-2', title: 'Created', ...rawInternal } };
      }
      if (method === 'previewAction') {
        return {
          preview_id: 'preview-1',
          action: args.proposal.action,
          payload: args.proposal.payload,
          confirmation_required: true,
          ...rawInternal,
        };
      }
      if (method === 'confirmAction') {
        return { task: { task_id: 'task-1', title: 'Safe task', ...rawInternal } };
      }
      throw new Error(`unexpected API method: ${String(method)}`);
    },
  });
  const dataSource = createApiLifeFlowDataSource({ api: fakeApi });

  const tasks = await dataSource.loadTasks({});
  assert.deepEqual(Object.keys(tasks[0]), [
    'key', 'title', 'description', 'status', 'dueAt', 'priority', 'steps',
  ]);
  assert.equal(tasks[0].key, 'task-1');
  assert.ok(Object.isFrozen(tasks));
  assert.equal((await dataSource.createTask({ input: { title: 'Created' } })).key, 'task-2');

  const preview = await dataSource.previewAction({
    proposal: { action: 'complete_task', payload: { task_id: 'task-1' } },
    lookup: { tasks },
  });
  assert.deepEqual(preview.summaryLines, ['完成任务：Safe task']);
  assert.ok(!preview.summaryLines.join('').includes('task-1'));
  const confirmed = await dataSource.confirmAction({ preview });
  assert.equal(confirmed.key, 'task-1');
  assert.equal(confirmed.metadata, undefined);
});

test('fixture is seed-isolated and performs no network requests', async () => {
  const seed = { tasks: [{ task_id: 'seed-1', title: 'Seed', status: 'open' }] };
  const snapshot = JSON.parse(JSON.stringify(seed));
  const dataSource = createFixtureLifeFlowDataSource({ seed, now: FIXED_NOW });
  const originalFetch = globalThis.fetch;
  let fetchCount = 0;
  globalThis.fetch = () => {
    fetchCount += 1;
    throw new Error('fixture must not fetch');
  };
  try {
    await dataSource.createTask({ input: { title: 'Local' } });
    await dataSource.loadTasks({});
    await dataSource.loadToday({});
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(fetchCount, 0);
  assert.deepEqual(seed, snapshot);
});

test('fixture supports conservative CRUD for every life-flow resource', async () => {
  const dataSource = createFixtureLifeFlowDataSource({
    now: FIXED_NOW,
    seed: {
      timeline: [{
        item_id: 'timeline-1', title: 'Earlier', kind: 'task',
        occurred_at: '2024-05-01T08:00:00Z', metadata: { hidden: true },
      }],
    },
  });

  const task = await dataSource.createTask({
    input: { title: 'Task', due_at: '2024-05-01T12:00:00Z' },
  });
  const step = await dataSource.addTaskStep({ taskKey: task.key, input: { title: 'Step' } });
  assert.equal((await dataSource.updateTaskStep({
    taskKey: task.key, stepKey: step.key, changes: { status: 'completed' },
  })).status, 'completed');
  assert.equal((await dataSource.transitionTask({
    key: task.key, action: 'complete',
  })).status, 'completed');

  const routine = await dataSource.createRoutine({ input: { title: 'Routine' } });
  const checkin = await dataSource.checkinRoutine({
    key: routine.key, input: { note: 'Done' },
  });
  assert.equal(checkin.status, 'completed');
  assert.equal((await dataSource.deactivateRoutine({ key: routine.key })).active, false);

  const activity = await dataSource.createActivity({ input: { title: 'Focus' } });
  const active = await dataSource.transitionActivity({ key: activity.key, action: 'start' });
  const completed = await dataSource.transitionActivity({ key: activity.key, action: 'complete' });
  assert.ok(active.startedAt);
  assert.ok(completed.endedAt);

  const diary = await dataSource.draftDiaryEntry({ date: '2024-05-01' });
  assert.equal((await dataSource.draftDiaryEntry({ date: '2024-05-01' })).key, diary.key);
  assert.equal((await dataSource.updateDiaryEntry({
    key: diary.key, changes: { body: 'Edited' },
  })).body, 'Edited');

  const reminder = await dataSource.createReminder({
    input: { title: 'Reminder', due_at: '2024-05-01T12:00:00Z' },
  });
  assert.equal((await dataSource.transitionReminder({
    key: reminder.key,
    action: 'snooze',
    input: { due_at: '2024-05-01T13:00:00Z' },
  })).status, 'snoozed');
  assert.equal((await dataSource.transitionReminder({
    key: reminder.key, action: 'cancel',
  })).status, 'cancelled');

  const calendar = await dataSource.createCalendarEvent({
    input: { title: 'Calendar', starts_at: '2024-05-01T10:00:00Z' },
  });
  assert.equal((await dataSource.removeCalendarEvent({ key: calendar.key })).status, 'deleted');
  assert.equal((await dataSource.loadCalendarEvents({})).length, 0);

  const today = await dataSource.loadToday({ date: '2024-05-01' });
  assert.ok(Object.isFrozen(today));
  assert.ok(Array.isArray(today.completedTasks));
  const timeline = await dataSource.loadTimeline({
    from: '2024-05-01', to: '2024-05-01', kind: 'task', limit: 10,
  });
  assert.equal(timeline.length, 1);
  assert.equal(timeline[0].metadata, undefined);

  const archived = await dataSource.archiveTask({ key: task.key });
  assert.equal(archived.status, 'archived');
  assert.equal(archived.task_id, undefined);
  assert.ok(Object.isFrozen(archived));
});

test('fixture previews and confirms all five gated companion actions', async () => {
  const dataSource = createFixtureLifeFlowDataSource({ now: FIXED_NOW });
  const task = await dataSource.createTask({ input: { title: 'Target task' } });
  const routine = await dataSource.createRoutine({ input: { title: 'Target routine' } });
  const proposals = [
    { action: 'create_task', payload: { title: 'New task' } },
    { action: 'complete_task', payload: { task_id: task.key } },
    { action: 'start_focus_session', payload: { title: 'Focus' } },
    { action: 'checkin_routine', payload: { routine_id: routine.key } },
    { action: 'draft_diary', payload: { date: '2024-05-01' } },
  ];

  for (const proposal of proposals) {
    const preview = await dataSource.previewAction({
      proposal,
      lookup: { tasks: [task], routines: [routine] },
    });
    const summary = preview.summaryLines.join('\n');
    assert.ok(preview.previewKey);
    assert.ok(summary);
    assert.ok(!summary.includes(task.key));
    assert.ok(!summary.includes(routine.key));
    const result = await dataSource.confirmAction({ preview });
    assert.ok(result.key);
    assert.ok(Object.isFrozen(result));
  }
});

test('fixture rejects not-found keys and invalid transitions without false success', async () => {
  const dataSource = createFixtureLifeFlowDataSource({ now: FIXED_NOW });
  const task = await dataSource.createTask({ input: { title: 'Task' } });
  const reminder = await dataSource.createReminder({
    input: { title: 'Reminder', due_at: '2024-05-01T12:00:00Z' },
  });
  await assert.rejects(
    dataSource.updateTask({ key: 'missing', changes: {} }),
    (error) => error instanceof AppError && error.kind === 'not-found',
  );
  await assert.rejects(
    dataSource.transitionTask({ key: task.key, action: 'delete' }),
    (error) => error instanceof AppError && error.kind === 'validation',
  );
  await assert.rejects(
    dataSource.transitionReminder({ key: reminder.key, action: 'snooze', input: {} }),
    (error) => error instanceof AppError && error.kind === 'validation',
  );
});
