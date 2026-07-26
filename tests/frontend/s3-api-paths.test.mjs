import test from 'node:test';
import assert from 'node:assert/strict';
import { createLifeFlowApi } from '../../apps/companion-web/companion-ui/js/services/life-flow-api.js';

function spyApi() {
  const calls = [];
  const api = createLifeFlowApi({
    request: async (path, options) => {
      calls.push({ path, options });
      return { raw: true };
    },
  });
  return { api, calls };
}

async function assertCall(method, input, expected) {
  const { api, calls } = spyApi();
  assert.deepEqual(await api[method](input), { raw: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, expected.path);
  assert.equal(calls[0].options.method, expected.method);
  assert.deepEqual(calls[0].options.body, expected.body);
  if ('signal' in expected) assert.equal(calls[0].options.signal, expected.signal);
}

const readCases = [
  ['loadToday', { date: '2024-01-01' }, '/api/today?date=2024-01-01'],
  ['loadTimeline', { from: '2024-01-01', to: '2024-01-02', kind: 'task', limit: 10 },
    '/api/timeline?from=2024-01-01&to=2024-01-02&kind=task&limit=10'],
  ['loadTasks', { status: 'open', limit: 5 }, '/api/tasks?status=open&limit=5'],
  ['loadRoutines', { activeOnly: false, limit: 8 }, '/api/routines?active_only=false&limit=8'],
  ['loadActivities', { status: 'active', limit: 6 }, '/api/activities?status=active&limit=6'],
  ['loadDiaryEntries', { date: '2024-01-01', limit: 7 },
    '/api/diary-entries?date=2024-01-01&limit=7'],
  ['loadReminders', { status: 'due', limit: 9 }, '/api/reminders?status=due&limit=9'],
  ['loadCalendarEvents', { limit: 4 }, '/api/calendar-events?limit=4'],
];

for (const [method, input, path] of readCases) {
  test(`${method} emits the exact read path and query`, async () => {
    await assertCall(method, input, { path });
  });
}

test('read methods omit empty query values', async () => {
  await assertCall('loadTimeline', { from: '', to: undefined, kind: null }, {
    path: '/api/timeline',
  });
  await assertCall('loadTasks', {}, { path: '/api/tasks' });
});

const writeCases = [
  ['createTask', { input: { title: 'T' } }, '/api/tasks', 'POST', { title: 'T' }],
  ['updateTask', { key: 'a/b ', changes: { title: 'U' } },
    '/api/tasks/a%2Fb%20', 'PATCH', { title: 'U' }],
  ['addTaskStep', { taskKey: 'a/b', input: { title: 'S' } },
    '/api/tasks/a%2Fb/steps', 'POST', { title: 'S' }],
  ['updateTaskStep', { taskKey: 'task', stepKey: 'step / 1', changes: { status: 'completed' } },
    '/api/tasks/task/steps/step%20%2F%201', 'PATCH', { status: 'completed' }],
  ['transitionTask', { key: 'task', action: 'block', input: { note: 'later' } },
    '/api/tasks/task/block', 'POST', { note: 'later' }],
  ['archiveTask', { key: 'task' }, '/api/tasks/task', 'DELETE', undefined],
  ['createRoutine', { input: { title: 'R' } }, '/api/routines', 'POST', { title: 'R' }],
  ['updateRoutine', { key: 'routine', changes: { active: true } },
    '/api/routines/routine', 'PATCH', { active: true }],
  ['checkinRoutine', { key: 'routine', input: { note: 'done' } },
    '/api/routines/routine/checkins', 'POST', { note: 'done' }],
  ['deactivateRoutine', { key: 'routine' }, '/api/routines/routine', 'DELETE', undefined],
  ['createActivity', { input: { title: 'Focus' } },
    '/api/activities', 'POST', { title: 'Focus' }],
  ['transitionActivity', { key: 'activity', action: 'pause' },
    '/api/activities/activity/pause', 'POST', {}],
  ['createDiaryEntry', { input: { body: 'D' } },
    '/api/diary-entries', 'POST', { body: 'D' }],
  ['draftDiaryEntry', { date: '2024-01-01' },
    '/api/diary-entries/draft', 'POST', { date: '2024-01-01' }],
  ['updateDiaryEntry', { key: 'diary', changes: { body: 'U' } },
    '/api/diary-entries/diary', 'PATCH', { body: 'U' }],
  ['removeDiaryEntry', { key: 'diary' },
    '/api/diary-entries/diary', 'DELETE', undefined],
  ['createReminder', { input: { title: 'M' } },
    '/api/reminders', 'POST', { title: 'M' }],
  ['updateReminder', { key: 'reminder', changes: { title: 'N' } },
    '/api/reminders/reminder', 'PATCH', { title: 'N' }],
  ['transitionReminder', { key: 'reminder', action: 'complete' },
    '/api/reminders/reminder/complete', 'POST', {}],
  ['transitionReminder', { key: 'reminder', action: 'cancel' },
    '/api/reminders/reminder/cancel', 'POST', {}],
  ['transitionReminder', {
    key: 'reminder', action: 'snooze', input: { due_at: '2024-01-01T08:00:00Z' },
  }, '/api/reminders/reminder/snooze', 'POST', { due_at: '2024-01-01T08:00:00Z' }],
  ['createCalendarEvent', { input: { title: 'C' } },
    '/api/calendar-events', 'POST', { title: 'C' }],
  ['updateCalendarEvent', { key: 'calendar', changes: { title: 'D' } },
    '/api/calendar-events/calendar', 'PATCH', { title: 'D' }],
  ['removeCalendarEvent', { key: 'calendar' },
    '/api/calendar-events/calendar', 'DELETE', undefined],
];

for (const [method, input, path, httpMethod, body] of writeCases) {
  test(`${method} emits exact path, method, and body`, async () => {
    await assertCall(method, input, { path, method: httpMethod, body });
  });
}

test('request signals retain object identity', async () => {
  const signal = { testSignal: true };
  await assertCall('createCalendarEvent', { input: { title: 'C' }, signal }, {
    path: '/api/calendar-events', method: 'POST', body: { title: 'C' }, signal,
  });
});

test('action preview ignores lookup and confirm sends only the strict server payload', async () => {
  const proposal = { action: 'complete_task', payload: { task_id: 'task' } };
  await assertCall('previewAction', { proposal, lookup: { tasks: ['must-not-leak'] } }, {
    path: '/api/actions/preview', method: 'POST', body: proposal,
  });
  await assertCall('confirmAction', {
    preview: {
      previewKey: 'hidden-preview',
      action: 'complete_task',
      requestSnapshot: { task_id: 'task' },
      summaryLines: ['visible summary'],
    },
  }, {
    path: '/api/actions/confirm',
    method: 'POST',
    body: { action: 'complete_task', payload: { task_id: 'task' }, confirmed: true },
  });
});

function assertValidation(run) {
  assert.throws(run, (error) => error?.name === 'AppError' && error.kind === 'validation');
}

test('invalid keys, actions, snooze, proposal, and preview fail before request', () => {
  const { api, calls } = spyApi();
  assertValidation(() => api.updateTask({ key: ' ', changes: {} }));
  assertValidation(() => api.transitionTask({ key: 'task', action: 'delete' }));
  assertValidation(() => api.transitionActivity({ key: 'activity', action: 'delete' }));
  assertValidation(() => api.transitionReminder({ key: 'reminder', action: 'delete' }));
  assertValidation(() => api.transitionReminder({
    key: 'reminder', action: 'snooze', input: {},
  }));
  assertValidation(() => api.previewAction({ proposal: null }));
  assertValidation(() => api.confirmAction({ preview: { action: 'create_task' } }));
  assert.equal(calls.length, 0);
});

test('the transport surface exposes no nonexistent activity delete or calendar single read', () => {
  const { api } = spyApi();
  assert.equal(api.deleteActivity, undefined);
  assert.equal(api.removeActivity, undefined);
  assert.equal(api.getCalendarEvent, undefined);
  assert.ok(Object.isFrozen(api));
});
