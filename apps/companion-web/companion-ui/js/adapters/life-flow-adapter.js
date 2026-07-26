import { isISOInstant, parseLocalAllDayToISO } from '../shared/time.js';
import {
  isPlainObject,
  normalizeBoundedText,
  normalizeEnum,
  normalizeOpaqueKey,
} from '../shared/validation.js';

const INVALID_RESPONSE = 'invalid life-flow response';
const TIMELINE_KINDS = new Set([
  'activity', 'calendar', 'reminder', 'task', 'routine', 'diary', 'outbox',
]);
const TASK_STATUSES = new Set([
  'open', 'in_progress', 'blocked', 'completed', 'cancelled', 'archived',
]);
const TASK_PRIORITIES = new Set(['low', 'normal', 'high']);
const STEP_STATUSES = new Set(['open', 'completed', 'cancelled']);
const ROUTINE_SCHEDULES = new Set(['daily', 'weekly']);
const ROUTINE_POLICIES = new Set(['none', 'remind']);
const CHECKIN_STATUSES = new Set(['pending', 'completed', 'skipped']);
const ACTIVITY_KINDS = new Set(['focus', 'checkin', 'planning', 'reflection']);
const ACTIVITY_STATUSES = new Set([
  'planned', 'active', 'paused', 'completed', 'cancelled', 'expired',
]);
const DIARY_STATUSES = new Set(['draft', 'saved', 'deleted']);

function invalidResponse() { throw new TypeError(INVALID_RESPONSE); }
function instant(value) { return isISOInstant(value) ? value : null; }
function localDate(value) { return parseLocalAllDayToISO(value) ? value : null; }
function key(value) { return normalizeOpaqueKey(value); }
function title(value) {
  return normalizeBoundedText(value, 160, { required: true });
}
function field(raw, snakeName, camelName) {
  return raw[snakeName] ?? raw[camelName];
}
function mapItems(value, mapper) {
  if (!Array.isArray(value)) return Object.freeze([]);
  const result = [];
  for (const item of value) {
    if (!isPlainObject(item)) continue;
    const mapped = mapper(item);
    if (mapped) result.push(mapped);
  }
  return Object.freeze(result);
}
function wrappedItem(raw, names) {
  if (!isPlainObject(raw)) invalidResponse();
  for (const name of names) {
    if (isPlainObject(raw[name])) return raw[name];
  }
  return invalidResponse();
}
function wrappedList(raw) {
  if (!isPlainObject(raw) || !Array.isArray(raw.items)) invalidResponse();
  return raw.items;
}

function adaptTodayItem(raw, keyName, kind, timeName) {
  const itemKey = key(raw[keyName]);
  const itemTitle = title(raw.title);
  if (!itemKey || !itemTitle) return null;
  return Object.freeze({
    key: itemKey,
    kind,
    title: itemTitle,
    status: normalizeBoundedText(raw.status, 40) || 'unknown',
    occurredAt: timeName ? instant(raw[timeName]) : null,
  });
}

/** Adapts the aggregate Today response to finite summary items. */
export function adaptTodayResponse(raw) {
  if (!isPlainObject(raw)) invalidResponse();
  return Object.freeze({
    date: localDate(raw.date),
    activeActivities: mapItems(field(raw, 'active_activities', 'activeActivities'),
      (item) => adaptTodayItem(item, 'session_id', 'activity', 'started_at')),
    calendarEvents: mapItems(field(raw, 'calendar_events', 'calendarEvents'),
      (item) => adaptTodayItem(item, 'event_id', 'calendar', 'starts_at')),
    dueTasks: mapItems(field(raw, 'due_tasks', 'dueTasks'),
      (item) => adaptTodayItem(item, 'task_id', 'task', 'due_at')),
    routines: mapItems(raw.routines,
      (item) => adaptTodayItem(item, 'routine_id', 'routine', null)),
    overdueTasks: mapItems(field(raw, 'overdue_tasks', 'overdueTasks'),
      (item) => adaptTodayItem(item, 'task_id', 'task', 'due_at')),
    openTasks: mapItems(field(raw, 'open_tasks', 'openTasks'),
      (item) => adaptTodayItem(item, 'task_id', 'task', 'due_at')),
    completedTasks: mapItems(field(raw, 'completed_tasks', 'completedTasks'),
      (item) => adaptTodayItem(item, 'task_id', 'task', 'due_at')),
  });
}

/** Adapts timeline items while rejecting navigation and source identifiers. */
export function adaptTimelineResponse(raw) {
  return Object.freeze({
    items: mapItems(wrappedList(raw), (item) => {
      const itemKey = key(item.item_id);
      const itemTitle = title(item.title);
      if (!itemKey || !itemTitle) return null;
      return Object.freeze({
        key: itemKey,
        title: itemTitle,
        kind: normalizeEnum(item.kind, TIMELINE_KINDS),
        occurredAt: instant(item.occurred_at),
      });
    }),
  });
}

function adaptTaskStep(raw) {
  const stepKey = key(field(raw, 'step_id', 'stepId'));
  const stepTitle = title(raw.title);
  if (!stepKey || !stepTitle) return null;
  const position = Number(raw.position);
  return Object.freeze({
    key: stepKey,
    title: stepTitle,
    position: Number.isInteger(position) && position >= 0 ? position : 0,
    status: normalizeEnum(raw.status, STEP_STATUSES),
    completedAt: instant(field(raw, 'completed_at', 'completedAt')),
  });
}

function adaptTask(raw) {
  const taskKey = key(field(raw, 'task_id', 'taskId'));
  const taskTitle = title(raw.title);
  if (!taskKey || !taskTitle) return null;
  return Object.freeze({
    key: taskKey,
    title: taskTitle,
    description: normalizeBoundedText(raw.description, 2000) || null,
    status: normalizeEnum(raw.status, TASK_STATUSES),
    dueAt: instant(field(raw, 'due_at', 'dueAt')),
    priority: normalizeEnum(raw.priority, TASK_PRIORITIES),
    steps: mapItems(raw.steps, adaptTaskStep),
  });
}

export function adaptTaskResponse(raw) {
  const task = adaptTask(wrappedItem(raw, ['task']));
  if (!task) invalidResponse();
  return task;
}
export function adaptTaskListResponse(raw) {
  return Object.freeze({ items: mapItems(wrappedList(raw), adaptTask) });
}
export function adaptTaskStepResponse(raw) {
  const step = adaptTaskStep(wrappedItem(raw, ['step']));
  if (!step) invalidResponse();
  return step;
}

function adaptRoutine(raw) {
  const routineKey = key(field(raw, 'routine_id', 'routineId'));
  const routineTitle = title(raw.title);
  if (!routineKey || !routineTitle) return null;
  return Object.freeze({
    key: routineKey,
    title: routineTitle,
    schedule: normalizeEnum(raw.schedule, ROUTINE_SCHEDULES),
    active: typeof raw.active === 'boolean' ? raw.active : false,
    reminderPolicy: normalizeEnum(
      field(raw, 'reminder_policy', 'reminderPolicy'), ROUTINE_POLICIES,
    ),
  });
}

export function adaptRoutineResponse(raw) {
  const routine = adaptRoutine(wrappedItem(raw, ['routine']));
  if (!routine) invalidResponse();
  return routine;
}
export function adaptRoutineListResponse(raw) {
  return Object.freeze({ items: mapItems(wrappedList(raw), adaptRoutine) });
}
export function adaptRoutineCheckinResponse(raw) {
  const checkin = wrappedItem(raw, ['checkin']);
  const checkinKey = key(field(checkin, 'checkin_id', 'checkinId'));
  const periodKey = key(field(checkin, 'period_key', 'periodKey'));
  if (!checkinKey || !periodKey) invalidResponse();
  return Object.freeze({
    key: checkinKey,
    periodKey,
    status: normalizeEnum(checkin.status, CHECKIN_STATUSES),
    note: normalizeBoundedText(checkin.note, 2000) || null,
    occurredAt: instant(field(checkin, 'occurred_at', 'occurredAt')),
  });
}

function adaptActivity(raw) {
  const activityKey = key(field(raw, 'session_id', 'sessionId'));
  const activityTitle = title(raw.title);
  if (!activityKey || !activityTitle) return null;
  return Object.freeze({
    key: activityKey,
    kind: normalizeEnum(raw.kind, ACTIVITY_KINDS),
    title: activityTitle,
    status: normalizeEnum(raw.status, ACTIVITY_STATUSES),
    startedAt: instant(field(raw, 'started_at', 'startedAt')),
    endedAt: instant(field(raw, 'ended_at', 'endedAt')),
    summary: normalizeBoundedText(raw.summary, 2000) || null,
  });
}

export function adaptActivityResponse(raw) {
  const activity = adaptActivity(wrappedItem(raw, ['activity']));
  if (!activity) invalidResponse();
  return activity;
}
export function adaptActivityListResponse(raw) {
  return Object.freeze({ items: mapItems(wrappedList(raw), adaptActivity) });
}

function adaptDiaryEntry(raw) {
  const entryKey = key(field(raw, 'entry_id', 'entryId'));
  const entryTitle = title(raw.title);
  if (!entryKey || !entryTitle) return null;
  return Object.freeze({
    key: entryKey,
    date: localDate(raw.date),
    title: entryTitle,
    body: normalizeBoundedText(raw.body, 20000, { preserveOuterWhitespace: true }),
    status: normalizeEnum(raw.status, DIARY_STATUSES),
    updatedAt: instant(field(raw, 'updated_at', 'updatedAt')),
  });
}

export function adaptDiaryEntryResponse(raw) {
  const entry = adaptDiaryEntry(wrappedItem(raw, ['diary_entry', 'entry']));
  if (!entry) invalidResponse();
  return entry;
}
export function adaptDiaryEntryListResponse(raw) {
  return Object.freeze({ items: mapItems(wrappedList(raw), adaptDiaryEntry) });
}
