import test from 'node:test';
import assert from 'node:assert/strict';
import {
  foldTodayCategories,
  getActivityActions,
  getCalendarActions,
  getDiaryActions,
  getReminderActions,
  getRoutineActions,
  getTaskActions,
} from '../../apps/companion-web/companion-ui/js/features/life-flow/life-flow-state.js';
import {
  ALLOWED_ACTIONS,
  isAllowedAction,
  transitionActionState,
} from '../../apps/companion-web/companion-ui/js/features/action-proposal/action-state.js';

const item = (key) => ({ key, title: `Title ${key}` });

test('five non-empty Today categories expose four and fold completed', () => {
  const result = foldTodayCategories({
    activeActivities: [item('a1')],
    calendarEvents: [item('c1')],
    dueTasks: [item('i1')],
    overdueTasks: [item('co1')],
    completedTasks: [item('done1')],
  });
  assert.deepEqual(result.visibleCategories.map(({ name }) => name), [
    'activeActivities', 'calendarEvents', 'intentions', 'carriedOver',
  ]);
  assert.equal(result.foldedCompleted.items[0].key, 'done1');
});

test('four or fewer non-empty Today categories are all visible', () => {
  const result = foldTodayCategories({
    activeActivities: [item('a1')], completedTasks: [item('done1')],
  });
  assert.deepEqual(result.visibleCategories.map(({ name }) => name), [
    'activeActivities', 'completedTasks',
  ]);
  assert.equal(result.foldedCompleted, null);
});

test('Today merges stably, deduplicates by key and rejects invalid keys', () => {
  const result = foldTodayCategories({
    dueTasks: [item('task-1'), { key: '  ' }, null],
    routines: [item('task-1'), item('routine-1')],
    overdueTasks: [item('overdue-1')],
    openTasks: [item('overdue-1'), { noKey: true }, { key: 123 }],
  });
  const intentions = result.visibleCategories.find(({ name }) => name === 'intentions');
  const carried = result.visibleCategories.find(({ name }) => name === 'carriedOver');
  assert.deepEqual(intentions.items.map(({ key }) => key), ['task-1', 'routine-1']);
  assert.deepEqual(carried.items.map(({ key }) => key), ['overdue-1']);
});

test('Today limits visible items and preserves all folded completed items', () => {
  const many = ['1', '2', '3', '4', '5'].map(item);
  const result = foldTodayCategories({
    activeActivities: [item('a')], calendarEvents: [item('c')],
    dueTasks: [item('i')], overdueTasks: [item('o')], completedTasks: many,
  });
  assert.equal(result.foldedCompleted.items.length, 5);
  assert.equal(result.foldedCompleted.hiddenCount, 5);
  const completedOnly = foldTodayCategories({ completedTasks: many });
  assert.equal(completedOnly.visibleCategories[0].items.length, 3);
  assert.equal(completedOnly.visibleCategories[0].hiddenCount, 2);
});

test('Today output is frozen without mutating or freezing input items', () => {
  const sourceItem = item('a');
  const source = { activeActivities: [sourceItem] };
  const before = structuredClone(source);
  const result = foldTodayCategories(source);
  assert.deepEqual(source, before);
  assert.equal(Object.isFrozen(result), true);
  assert.equal(Object.isFrozen(result.visibleCategories), true);
  assert.equal(Object.isFrozen(result.visibleCategories[0]), true);
  assert.equal(Object.isFrozen(result.visibleCategories[0].items), true);
  assert.equal(Object.isFrozen(sourceItem), false);
});

test('Task actions match all supported and terminal states', () => {
  assert.deepEqual(getTaskActions('open'), ['start', 'block', 'complete', 'cancel', 'archive']);
  assert.deepEqual(getTaskActions('in_progress'), ['block', 'complete', 'cancel', 'archive']);
  assert.deepEqual(getTaskActions('blocked'), ['start', 'complete', 'cancel', 'archive']);
  assert.deepEqual(getTaskActions('completed'), ['archive']);
  assert.deepEqual(getTaskActions('cancelled'), ['archive']);
  assert.deepEqual(getTaskActions('archived'), []);
  assert.deepEqual(getTaskActions('unknown'), []);
});

test('Activity actions match all mutable and terminal states', () => {
  assert.deepEqual(getActivityActions('planned'), ['start', 'cancel']);
  assert.deepEqual(getActivityActions('active'), ['pause', 'complete', 'cancel']);
  assert.deepEqual(getActivityActions('paused'), ['resume', 'complete', 'cancel']);
  ['completed', 'cancelled', 'expired', 'unknown'].forEach((status) => {
    assert.deepEqual(getActivityActions(status), []);
  });
});

test('Reminder actions are available only to active reminder states', () => {
  const actions = ['complete', 'snooze', 'cancel', 'edit'];
  ['scheduled', 'due', 'snoozed'].forEach((status) => {
    assert.deepEqual(getReminderActions(status), actions);
  });
  ['completed', 'cancelled', 'expired', 'unknown'].forEach((status) => {
    assert.deepEqual(getReminderActions(status), []);
  });
});

test('Routine, Diary and Calendar actions are strict and newly frozen', () => {
  assert.deepEqual(getRoutineActions(true), ['edit', 'checkin', 'deactivate']);
  assert.deepEqual(getRoutineActions(false), ['edit']);
  assert.deepEqual(getRoutineActions('true'), []);
  assert.deepEqual(getDiaryActions('draft'), ['edit', 'remove']);
  assert.deepEqual(getDiaryActions('deleted'), []);
  assert.deepEqual(getCalendarActions('active'), ['edit', 'remove']);
  assert.deepEqual(getCalendarActions('deleted'), []);
  const first = getDiaryActions('saved');
  const second = getDiaryActions('saved');
  assert.notEqual(first, second);
  assert.equal(Object.isFrozen(first), true);
});

test('allowed companion actions are ordered, frozen and queried without a mutable Set', () => {
  assert.deepEqual(ALLOWED_ACTIONS, [
    'create_task', 'complete_task', 'start_focus_session', 'checkin_routine', 'draft_diary',
  ]);
  assert.equal(Object.isFrozen(ALLOWED_ACTIONS), true);
  assert.equal(ALLOWED_ACTIONS.add, undefined);
  assert.equal(isAllowedAction('create_task'), true);
  assert.equal(isAllowedAction('delete_everything'), false);
  assert.equal(isAllowedAction(null), false);
});

test('action proposal follows the complete preview and confirm success path', () => {
  let state = transitionActionState('proposal', 'PREVIEW');
  state = transitionActionState(state, 'READY');
  state = transitionActionState(state, 'CONFIRM');
  state = transitionActionState(state, 'SUCCESS');
  assert.equal(state, 'success');
});

test('preview and confirm errors have distinct recovery paths', () => {
  assert.equal(transitionActionState('previewing', 'ERROR'), 'preview_error');
  assert.equal(transitionActionState('preview_error', 'RETRY'), 'previewing');
  assert.equal(transitionActionState('preview_error', 'CANCEL'), 'cancelled');
  assert.equal(transitionActionState('confirming', 'ERROR'), 'confirm_error');
  assert.equal(transitionActionState('confirm_error', 'RETRY'), 'confirming');
  assert.equal(transitionActionState('confirm_error', 'DISMISS'), 'cancelled');
});

test('confirming, terminal and unknown action transitions fail closed', () => {
  assert.equal(transitionActionState('confirming', 'CANCEL'), null);
  assert.equal(transitionActionState('success', 'ANY'), null);
  assert.equal(transitionActionState('cancelled', 'PREVIEW'), null);
  assert.equal(transitionActionState('proposal', 'NOT_EXIST'), null);
  assert.equal(transitionActionState('unknown', 'PREVIEW'), null);
});
