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
  setResourceConfirmation,
  updateResourceDraft,
} from '../../apps/companion-web/companion-ui/js/app-state.js';
import { initLifeFlow } from '../../apps/companion-web/companion-ui/js/features/life-flow/life-flow-controller.js';

const flush = () => new Promise((resolve) => setImmediate(resolve));

const reminder = (overrides = {}) => ({
  key: 'reminder-safe-1',
  title: '看看窗外的光',
  description: '离开屏幕一会儿',
  dueAt: '2026-07-26T09:00:00Z',
  timezoneName: 'Asia/Shanghai',
  recurrence: null,
  status: 'scheduled',
  ...overrides,
});

const calendarEvent = (overrides = {}) => ({
  key: 'calendar-safe-1',
  title: '安静的会面',
  startsAt: '2026-07-26T02:00:00Z',
  endsAt: '2026-07-26T03:00:00Z',
  allDay: false,
  timezoneName: 'Asia/Shanghai',
  status: 'active',
  ...overrides,
});

function load(resource, items) {
  assert.equal(beginResourceLoad(resource), true);
  assert.equal(completeResourceLoad(resource, items), true);
}

test('Reminder AppState sorts active and terminal data while preserving only safe fields', () => {
  initializeState(null);
  load('reminders', [
    reminder({ key: 'later', dueAt: '2026-07-27T09:00:00Z', metadata: { private: true } }),
    reminder({ key: 'done', dueAt: '2026-07-25T09:00:00Z', status: 'completed' }),
    reminder({ key: 'first', dueAt: '2026-07-26T08:00:00Z', diagnosis: 'drop' }),
  ]);
  const items = getState().lifeFlow.reminders.items;
  assert.deepEqual(items.map((item) => item.key), ['done', 'first', 'later']);
  assert.doesNotMatch(JSON.stringify(items), /metadata|private|diagnosis/);
  assert.equal(selectResourceItem('reminders', 'done'), true);
  assert.equal(openResourceEditor('reminders', 'edit'), false);
  assert.equal(selectResourceItem('reminders', 'first'), true);
  assert.equal(openResourceEditor('reminders', 'edit'), true);
  assert.match(getState().lifeFlow.reminders.editor.draft.dueAt, /^2026-07-26T/);
});

test('Reminder transitions are gated, keep cancelled terminal items, and restore editor drafts', () => {
  initializeState(null);
  load('reminders', [reminder()]);
  selectResourceItem('reminders', 'reminder-safe-1');
  assert.equal(beginResourceWrite('reminders', 'transition', 'cancel'), null);
  assert.equal(setResourceConfirmation('reminders', 'cancel', true), true);
  assert.deepEqual(beginResourceWrite('reminders', 'transition', 'cancel'), {});
  assert.equal(completeResourceWrite('reminders', reminder({ status: 'cancelled' })), true);
  assert.equal(getState().lifeFlow.reminders.items[0].status, 'cancelled');
  assert.equal(getState().lifeFlow.reminders.items.length, 1);

  initializeState(null);
  load('reminders', []);
  openResourceEditor('reminders', 'create');
  updateResourceDraft('reminders', 'title', '  保留空白  ');
  updateResourceDraft('reminders', 'dueAt', '2026-07-28T09:30');
  assert.ok(beginResourceWrite('reminders', 'create'));
  assert.equal(failResourceWrite('reminders', { kind: 'offline' }), true);
  assert.equal(getState().lifeFlow.reminders.editor.draft.title, '  保留空白  ');
  assert.equal(getState().lifeFlow.reminders.editor.draft.dueAt, '2026-07-28T09:30');
});

test('Calendar AppState filters deleted, sorts all-day first at equal starts, and removes conservatively', () => {
  initializeState(null);
  load('calendarEvents', [
    calendarEvent({ key: 'timed' }),
    calendarEvent({ key: 'all-day', allDay: true, endsAt: null }),
    calendarEvent({ key: 'deleted', status: 'deleted' }),
  ]);
  assert.deepEqual(getState().lifeFlow.calendarEvents.items.map((item) => item.key), [
    'all-day', 'timed',
  ]);
  selectResourceItem('calendarEvents', 'timed');
  assert.equal(beginResourceWrite('calendarEvents', 'remove'), null);
  setResourceConfirmation('calendarEvents', 'remove', true);
  assert.deepEqual(beginResourceWrite('calendarEvents', 'remove'), {});
  assert.equal(completeResourceWrite('calendarEvents', calendarEvent({ key: 'timed' })), false);
  assert.equal(getState().lifeFlow.calendarEvents.items.length, 2);
  failResourceWrite('calendarEvents', { kind: 'server' });
  assert.deepEqual(beginResourceWrite('calendarEvents', 'remove'), {});
  assert.equal(completeResourceWrite('calendarEvents', calendarEvent({
    key: 'timed', status: 'deleted',
  })), true);
  assert.equal(getState().lifeFlow.view, 'calendar-events');
  assert.deepEqual(getState().lifeFlow.calendarEvents.items.map((item) => item.key), ['all-day']);
});

function setupController() {
  initializeState(null);
  const methodNames = [
    'loadToday', 'loadTimeline', 'loadTasks', 'createTask', 'updateTask',
    'addTaskStep', 'updateTaskStep', 'transitionTask', 'archiveTask',
    'loadRoutines', 'createRoutine', 'updateRoutine', 'checkinRoutine', 'deactivateRoutine',
    'loadActivities', 'createActivity', 'transitionActivity',
    'loadDiaryEntries', 'createDiaryEntry', 'draftDiaryEntry', 'updateDiaryEntry',
    'removeDiaryEntry', 'loadReminders', 'createReminder', 'updateReminder',
    'transitionReminder', 'loadCalendarEvents', 'createCalendarEvent',
    'updateCalendarEvent', 'removeCalendarEvent',
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

test('Reminder controller sends exact POST, snooze and cancel shapes', async (t) => {
  const { controller, pending } = setupController();
  t.after(() => controller.destroy());
  controller.openReminders();
  assert.equal(pending.loadReminders.length, 1);
  assert.deepEqual(
    { ...pending.loadReminders[0].params, signal: undefined },
    { limit: 100, signal: undefined },
  );
  pending.loadReminders[0].resolve([]);
  await flush();

  controller.handleReminderEvent({ type: 'CREATE' });
  controller.handleReminderEvent({ type: 'FIELD', field: 'title', value: '喝一杯水' });
  controller.handleReminderEvent({ type: 'FIELD', field: 'description', value: '慢一点' });
  controller.handleReminderEvent({ type: 'FIELD', field: 'dueAt', value: '2026-07-28T09:30' });
  controller.handleReminderEvent({ type: 'FIELD', field: 'recurrence', value: 'daily' });
  const creating = controller.handleReminderEvent({ type: 'SUBMIT' });
  const input = pending.createReminder[0].params.input;
  assert.deepEqual(Object.keys(input).sort(), [
    'description', 'due_at', 'recurrence', 'timezone_name', 'title',
  ]);
  assert.equal(input.title, '喝一杯水');
  assert.equal(input.recurrence, 'daily');
  assert.match(input.due_at, /Z$/);
  assert.equal(typeof input.timezone_name, 'string');
  pending.createReminder[0].resolve(reminder({ title: '喝一杯水', recurrence: 'daily' }));
  assert.equal(await creating, true);

  const snoozing = controller.handleReminderEvent({ type: 'SNOOZE', dueAt: '2026-07-28T10:45' });
  assert.equal(pending.transitionReminder[0].params.action, 'snooze');
  assert.deepEqual(Object.keys(pending.transitionReminder[0].params.input), ['due_at']);
  assert.match(pending.transitionReminder[0].params.input.due_at, /Z$/);
  pending.transitionReminder[0].resolve(reminder({
    title: '喝一杯水', recurrence: 'daily', status: 'snoozed',
    dueAt: pending.transitionReminder[0].params.input.due_at,
  }));
  assert.equal(await snoozing, true);

  assert.equal(await controller.handleReminderEvent({ type: 'CANCEL_CONFIRM' }), false);
  controller.handleReminderEvent({ type: 'CANCEL_INTENT' });
  const cancelling = controller.handleReminderEvent({ type: 'CANCEL_CONFIRM' });
  assert.equal(pending.transitionReminder[1].params.action, 'cancel');
  assert.deepEqual(pending.transitionReminder[1].params.input, {});
  pending.transitionReminder[1].resolve(reminder({
    title: '喝一杯水', recurrence: 'daily', status: 'cancelled',
  }));
  assert.equal(await cancelling, true);
  assert.equal(getState().lifeFlow.reminders.items[0].status, 'cancelled');
});

test('Calendar controller validates ranges, creates all-day values and removes only after deleted', async (t) => {
  const { controller, pending } = setupController();
  t.after(() => controller.destroy());
  controller.openCalendar();
  pending.loadCalendarEvents[0].resolve([]);
  await flush();

  controller.handleCalendarEvent({ type: 'CREATE' });
  controller.handleCalendarEvent({ type: 'FIELD', field: 'title', value: '休息日' });
  controller.handleCalendarEvent({ type: 'FIELD', field: 'allDay', value: true });
  controller.handleCalendarEvent({ type: 'FIELD', field: 'startDate', value: '2026-07-30' });
  controller.handleCalendarEvent({ type: 'FIELD', field: 'endDate', value: '2026-07-29' });
  assert.equal(await controller.handleCalendarEvent({ type: 'SUBMIT' }), false);
  assert.equal(pending.createCalendarEvent.length, 0);

  controller.handleCalendarEvent({ type: 'FIELD', field: 'endDate', value: '2026-07-31' });
  const creating = controller.handleCalendarEvent({ type: 'SUBMIT' });
  const input = pending.createCalendarEvent[0].params.input;
  assert.deepEqual(Object.keys(input).sort(), [
    'all_day', 'ends_at', 'starts_at', 'timezone_name', 'title',
  ]);
  assert.equal(input.all_day, true);
  assert.match(input.starts_at, /T.*Z$/);
  assert.match(input.ends_at, /T.*Z$/);
  assert.equal(Object.hasOwn(input, 'description'), false);
  pending.createCalendarEvent[0].resolve(calendarEvent({
    title: '休息日', startsAt: input.starts_at, endsAt: input.ends_at, allDay: true,
  }));
  assert.equal(await creating, true);

  controller.handleCalendarEvent({ type: 'REMOVE_INTENT' });
  const removing = controller.handleCalendarEvent({ type: 'REMOVE_CONFIRM' });
  assert.equal(pending.removeCalendarEvent[0].params.key, 'calendar-safe-1');
  assert.equal(getState().lifeFlow.calendarEvents.items.length, 1);
  pending.removeCalendarEvent[0].resolve(calendarEvent({
    title: '休息日', startsAt: input.starts_at, endsAt: input.ends_at,
    allDay: true, status: 'deleted',
  }));
  assert.equal(await removing, true);
  assert.deepEqual(getState().lifeFlow.calendarEvents.items, []);
});
