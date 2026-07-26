import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  adaptTodayResponse, adaptTimelineResponse, adaptTaskResponse,
  adaptTaskListResponse, adaptTaskStepResponse, adaptRoutineResponse,
  adaptRoutineListResponse, adaptRoutineCheckinResponse, adaptActivityResponse,
  adaptActivityListResponse, adaptDiaryEntryResponse,
} from '../../apps/companion-web/companion-ui/js/adapters/life-flow-adapter.js';
import {
  adaptReminderResponse, adaptReminderListResponse, adaptCalendarEventResponse,
  adaptCalendarEventListResponse, adaptActionPreviewResponse, adaptConfirmedActionResponse,
} from '../../apps/companion-web/companion-ui/js/adapters/scheduling-action-adapter.js';

const VALID_TIME = '2023-10-10T10:00:00Z';
const VALID_DATE = '2023-10-10';

const makeRaw = (wrapper, data) => ({ [wrapper]: data, metadata: { internal: true } });
const makeList = (items) => ({ items, metadata: { internal: true } });

const throwsLifeFlow = (fn) => assert.throws(
  fn, (error) => error instanceof TypeError && error.message === 'invalid life-flow response',
);
const throwsScheduling = (fn) => assert.throws(
  fn, (error) => error instanceof TypeError && error.message === 'invalid scheduling response',
);
const throwsUnavailable = (fn) => assert.throws(
  fn, (error) => error instanceof TypeError && error.message === 'action target unavailable',
);

describe('Life Flow Adapter', () => {
  it('reads Today snake_case fields and strips internal fields', () => {
    const raw = {
      date: VALID_DATE,
      active_activities: [{
        session_id: 'a1', title: 'Act', started_at: VALID_TIME, user_scope: 'private',
      }],
      calendar_events: [{
        event_id: 'c1', title: 'Cal', starts_at: VALID_TIME, metadata: {},
      }],
      due_tasks: [{
        task_id: 't1', title: 'Task', due_at: VALID_TIME, source_ref: 'ext',
      }],
      routines: [{ routine_id: 'r1', title: 'Rout', metadata: {} }],
      overdue_tasks: [{ task_id: 't2', title: 'Task2', due_at: VALID_TIME }],
      open_tasks: [],
      completed_tasks: [],
      internal_state: 'hidden',
    };

    const result = adaptTodayResponse(raw);
    assert.ok(Object.isFrozen(result));
    assert.ok(Object.isFrozen(result.activeActivities));
    assert.equal(result.date, VALID_DATE);
    assert.equal(result.activeActivities[0].key, 'a1');
    assert.equal(result.activeActivities[0].kind, 'activity');
    assert.equal(result.activeActivities[0].user_scope, undefined);
    assert.equal(result.calendarEvents[0].key, 'c1');
    assert.equal(result.calendarEvents[0].metadata, undefined);
    assert.equal(result.dueTasks[0].key, 't1');
    assert.equal(result.dueTasks[0].source_ref, undefined);
    assert.equal(result.routines[0].key, 'r1');
    assert.equal(result.overdueTasks[0].key, 't2');
    assert.equal(result.openTasks.length, 0);
    assert.equal(result.internal_state, undefined);
  });

  it('reads timeline items and skips invalid entries', () => {
    const result = adaptTimelineResponse(makeList([
      { item_id: 'i1', title: 'T1', kind: 'task', occurred_at: VALID_TIME },
      { item_id: 'i2' },
    ]));
    assert.equal(result.items.length, 1);
    assert.equal(result.items[0].key, 'i1');
    assert.equal(result.items[0].kind, 'task');
  });

  it('wraps and freezes task responses and lists', () => {
    const rawTask = {
      task_id: 't1', title: 'T', status: 'open', due_at: VALID_TIME, priority: 'high', steps: [],
    };
    const result = adaptTaskResponse(makeRaw('task', rawTask));
    assert.ok(Object.isFrozen(result));
    assert.equal(result.key, 't1');
    assert.equal(result.priority, 'high');

    const listResult = adaptTaskListResponse(makeList([rawTask, {}]));
    assert.equal(listResult.items.length, 1);
    assert.equal(listResult.items[0].key, 't1');
  });

  it('wraps task steps', () => {
    const result = adaptTaskStepResponse(makeRaw('step', {
      step_id: 's1', title: 'S', position: 1, status: 'open',
    }));
    assert.equal(result.key, 's1');
  });

  it('wraps routine responses and lists', () => {
    const rawRoutine = {
      routine_id: 'r1', title: 'R', schedule: 'daily', active: true, reminder_policy: 'remind',
    };
    const result = adaptRoutineResponse(makeRaw('routine', rawRoutine));
    assert.equal(result.key, 'r1');
    assert.equal(result.reminderPolicy, 'remind');
    assert.equal(result.active, true);
    assert.equal(adaptRoutineListResponse(makeList([rawRoutine])).items.length, 1);
  });

  it('handles the checkin wrapper', () => {
    const result = adaptRoutineCheckinResponse(makeRaw('checkin', {
      checkin_id: 'c1', period_key: 'p1', status: 'completed',
    }));
    assert.equal(result.key, 'c1');
    assert.equal(result.periodKey, 'p1');
  });

  it('wraps activity responses and lists', () => {
    const rawActivity = {
      session_id: 'a1', title: 'A', kind: 'focus', status: 'active', started_at: VALID_TIME,
    };
    const result = adaptActivityResponse(makeRaw('activity', rawActivity));
    assert.equal(result.key, 'a1');
    assert.equal(result.kind, 'focus');
    assert.equal(adaptActivityListResponse(makeList([rawActivity])).items.length, 1);
  });

  it('handles both diary wrappers and preserves body whitespace', () => {
    const first = adaptDiaryEntryResponse(makeRaw('diary_entry', {
      entry_id: 'd1', title: 'D', body: '  \n Hello \n  ',
    }));
    assert.equal(first.key, 'd1');
    assert.equal(first.body, '  \n Hello \n  ');
    assert.equal(adaptDiaryEntryResponse(makeRaw('entry', {
      entry_id: 'd2', title: 'D2',
    })).key, 'd2');
  });

  it('rejects invalid life-flow wrappers', () => {
    throwsLifeFlow(() => adaptTaskResponse({}));
    throwsLifeFlow(() => adaptTaskListResponse({ items: 'not-an-array' }));
    throwsLifeFlow(() => adaptRoutineCheckinResponse(makeRaw('checkin', {
      checkin_id: 'c1',
    })));
  });
});

describe('Scheduling Action Adapter', () => {
  it('maps safe reminder fields and unknown recurrence', () => {
    const rawReminder = {
      reminder_id: 'r1', title: 'R', due_at: VALID_TIME, recurrence: 'unknown_enum',
      status: 'due', secret_id: 'x', metadata: {}, reminder_ids: ['hidden'],
    };
    const result = adaptReminderResponse(makeRaw('reminder', rawReminder));
    assert.ok(Object.isFrozen(result));
    assert.equal(result.key, 'r1');
    assert.equal(result.recurrence, null);
    assert.equal(result.secret_id, undefined);
    assert.equal(result.metadata, undefined);
    assert.equal(result.reminder_ids, undefined);
    assert.equal(result.timezoneName, 'UTC');
    assert.equal(adaptReminderListResponse(makeList([
      rawReminder, { reminder_id: 'r2' },
    ])).items.length, 1);
  });

  it('maps safe calendar fields and skips invalid entries', () => {
    const rawCalendar = {
      event_id: 'c1', title: 'C', starts_at: VALID_TIME, all_day: true,
      status: 'active', metadata: {}, reminder_ids: ['hidden'],
    };
    const result = adaptCalendarEventResponse(makeRaw('calendar_event', rawCalendar));
    assert.ok(Object.isFrozen(result));
    assert.equal(result.key, 'c1');
    assert.equal(result.allDay, true);
    assert.equal(result.metadata, undefined);
    assert.equal(result.reminder_ids, undefined);
    assert.equal(adaptCalendarEventListResponse(makeList([
      rawCalendar, { event_id: 'c2' },
    ])).items.length, 1);
  });

  it('rejects invalid scheduling timestamps', () => {
    throwsScheduling(() => adaptCalendarEventResponse(makeRaw('calendar_event', {
      event_id: 'c1', title: 'C', starts_at: '2023-10-10T10:00:00',
    })));
  });

  it('adapts and freezes all five action previews', () => {
    const create = adaptActionPreviewResponse({
      preview_id: 'p1', action: 'create_task', confirmation_required: true,
      payload: { title: 'T1', priority: 'high', due_at: VALID_TIME },
    });
    assert.ok(Object.isFrozen(create));
    assert.ok(Object.isFrozen(create.requestSnapshot));
    assert.ok(Object.isFrozen(create.summaryLines));
    assert.deepEqual(create.requestSnapshot, {
      title: 'T1', priority: 'high', due_at: VALID_TIME,
    });
    assert.ok(create.summaryLines.includes('创建任务：T1'));

    const complete = adaptActionPreviewResponse({
      preview_id: 'p2', action: 'complete_task', confirmation_required: true,
      payload: { task_id: 't1' },
    }, { tasks: [{ key: 't1', title: 'Task One' }] });
    assert.equal(complete.requestSnapshot.task_id, 't1');
    assert.ok(!complete.summaryLines.some((line) => line.includes('t1')));
    assert.ok(complete.summaryLines.includes('完成任务：Task One'));

    const focus = adaptActionPreviewResponse({
      preview_id: 'p3', action: 'start_focus_session', confirmation_required: true,
      payload: { title: 'Focus' },
    });
    assert.equal(focus.requestSnapshot.title, 'Focus');
    assert.ok(focus.summaryLines.includes('开始专注：Focus'));

    const checkin = adaptActionPreviewResponse({
      preview_id: 'p4', action: 'checkin_routine', confirmation_required: true,
      payload: { routine_id: 'r1', note: '  Done  ' },
    }, { routines: [{ key: 'r1', title: 'Routine One' }] });
    assert.equal(checkin.requestSnapshot.routine_id, 'r1');
    assert.equal(checkin.requestSnapshot.note, '  Done  ');
    assert.ok(!checkin.summaryLines.some((line) => line.includes('r1')));

    const diary = adaptActionPreviewResponse({
      preview_id: 'p5', action: 'draft_diary', confirmation_required: true,
      payload: { date: VALID_DATE },
    });
    assert.equal(diary.requestSnapshot.date, VALID_DATE);
    assert.ok(diary.summaryLines.includes(`为 ${VALID_DATE} 生成一份可编辑日记草稿`));
  });

  it('requires display lookups for hidden action targets', () => {
    throwsUnavailable(() => adaptActionPreviewResponse({
      preview_id: 'px', action: 'complete_task', confirmation_required: true,
      payload: { task_id: 't1' },
    }, { tasks: [] }));
    throwsUnavailable(() => adaptActionPreviewResponse({
      preview_id: 'py', action: 'checkin_routine', confirmation_required: true,
      payload: { routine_id: 'r1' },
    }));
  });

  it('rejects invalid previews, unknown actions, and invalid timestamps', () => {
    throwsScheduling(() => adaptActionPreviewResponse({
      preview_id: 'p1', action: 'unknown_action', payload: {},
    }));
    throwsScheduling(() => adaptActionPreviewResponse({
      preview_id: 'p1', action: 'create_task', payload: {},
    }));
    throwsScheduling(() => adaptActionPreviewResponse({
      preview_id: 'p1', action: 'create_task', confirmation_required: true,
      payload: { title: 'T', due_at: 'bad-time' },
    }));
  });

  it('dispatches all confirmed actions and rejects unknown actions', () => {
    const rawTask = makeRaw('task', { task_id: 't1', title: 'T' });
    assert.equal(adaptConfirmedActionResponse(rawTask, 'create_task').key, 't1');
    assert.equal(adaptConfirmedActionResponse(rawTask, 'complete_task').key, 't1');
    assert.equal(adaptConfirmedActionResponse(makeRaw('activity', {
      session_id: 'a1', title: 'A',
    }), 'start_focus_session').key, 'a1');
    assert.equal(adaptConfirmedActionResponse(makeRaw('checkin', {
      checkin_id: 'c1', period_key: 'p1',
    }), 'checkin_routine').key, 'c1');
    assert.equal(adaptConfirmedActionResponse(makeRaw('diary_entry', {
      entry_id: 'd1', title: 'D',
    }), 'draft_diary').key, 'd1');
    throwsScheduling(() => adaptConfirmedActionResponse(rawTask, 'unknown_action'));
  });
});
