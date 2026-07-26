import { isISOInstant, parseLocalAllDayToISO } from '../shared/time.js';
import {
  isPlainObject,
  normalizeBoundedText,
  normalizeEnum,
  normalizeOpaqueKey,
} from '../shared/validation.js';
import {
  adaptActivityResponse,
  adaptDiaryEntryResponse,
  adaptRoutineCheckinResponse,
  adaptTaskResponse,
} from './life-flow-adapter.js';

const INVALID_RESPONSE = 'invalid scheduling response';
const REMINDER_STATUSES = new Set([
  'scheduled', 'due', 'snoozed', 'completed', 'cancelled', 'expired',
]);
const REMINDER_RECURRENCES = new Set(['daily', 'weekly']);
const CALENDAR_STATUSES = new Set(['active', 'deleted']);
const SUPPORTED_ACTIONS = new Set([
  'create_task', 'complete_task', 'start_focus_session', 'checkin_routine', 'draft_diary',
]);
const TASK_PRIORITIES = new Set(['low', 'normal', 'high']);

function invalidResponse() { throw new TypeError(INVALID_RESPONSE); }
function targetUnavailable() { throw new TypeError('action target unavailable'); }
function key(value) { return normalizeOpaqueKey(value); }
function instant(value) { return isISOInstant(value) ? value : null; }
function title(value) {
  return normalizeBoundedText(value, 160, { required: true });
}
function field(raw, snakeName, camelName) {
  return raw[snakeName] ?? raw[camelName];
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
function mapItems(value, mapper) {
  const result = [];
  for (const item of value) {
    if (!isPlainObject(item)) continue;
    const mapped = mapper(item);
    if (mapped) result.push(mapped);
  }
  return Object.freeze(result);
}

function adaptReminder(raw) {
  const reminderKey = key(field(raw, 'reminder_id', 'reminderId'));
  const reminderTitle = title(raw.title);
  const dueAt = instant(field(raw, 'due_at', 'dueAt'));
  if (!reminderKey || !reminderTitle || !dueAt) return null;

  const recurrence = raw.recurrence
    ? normalizeEnum(raw.recurrence, REMINDER_RECURRENCES)
    : null;
  return Object.freeze({
    key: reminderKey,
    title: reminderTitle,
    description: normalizeBoundedText(raw.description, 2000) || null,
    dueAt,
    timezoneName: normalizeBoundedText(
      field(raw, 'timezone_name', 'timezoneName'), 80,
    ) || 'UTC',
    recurrence: recurrence === 'unknown' ? null : recurrence,
    status: normalizeEnum(raw.status, REMINDER_STATUSES),
  });
}

export function adaptReminderResponse(raw) {
  const reminder = adaptReminder(wrappedItem(raw, ['reminder']));
  if (!reminder) invalidResponse();
  return reminder;
}

export function adaptReminderListResponse(raw) {
  return Object.freeze({ items: mapItems(wrappedList(raw), adaptReminder) });
}

function adaptCalendarEvent(raw) {
  const eventKey = key(field(raw, 'event_id', 'eventId'));
  const eventTitle = title(raw.title);
  const startsAt = instant(field(raw, 'starts_at', 'startsAt'));
  if (!eventKey || !eventTitle || !startsAt) return null;

  const rawEndsAt = field(raw, 'ends_at', 'endsAt');
  const endsAt = rawEndsAt ? instant(rawEndsAt) : null;
  if (rawEndsAt && !endsAt) return null;

  return Object.freeze({
    key: eventKey,
    title: eventTitle,
    startsAt,
    endsAt,
    allDay: typeof field(raw, 'all_day', 'allDay') === 'boolean'
      ? field(raw, 'all_day', 'allDay')
      : false,
    timezoneName: normalizeBoundedText(
      field(raw, 'timezone_name', 'timezoneName'), 80,
    ) || 'UTC',
    status: normalizeEnum(raw.status, CALENDAR_STATUSES),
  });
}

export function adaptCalendarEventResponse(raw) {
  const calendarEvent = adaptCalendarEvent(wrappedItem(raw, ['calendar_event']));
  if (!calendarEvent) invalidResponse();
  return calendarEvent;
}

export function adaptCalendarEventListResponse(raw) {
  return Object.freeze({ items: mapItems(wrappedList(raw), adaptCalendarEvent) });
}

export function adaptActionPreviewResponse(raw, lookups = {}) {
  if (!isPlainObject(raw)) invalidResponse();
  const previewKey = key(field(raw, 'preview_id', 'previewId'));
  const action = normalizeEnum(raw.action, SUPPORTED_ACTIONS);
  const payload = raw.payload;
  if (
    !previewKey
    || action === 'unknown'
    || !isPlainObject(payload)
    || field(raw, 'confirmation_required', 'confirmationRequired') !== true
  ) invalidResponse();

  let requestSnapshot;
  const summaryLines = [];

  if (action === 'create_task') {
    const taskTitle = title(payload.title);
    if (!taskTitle) invalidResponse();
    const priority = normalizeEnum(payload.priority, TASK_PRIORITIES);
    const dueAtRaw = field(payload, 'due_at', 'dueAt');
    const dueAt = dueAtRaw ? instant(dueAtRaw) : null;
    if (dueAtRaw && !dueAt) invalidResponse();

    const snapshot = { title: taskTitle };
    if (priority !== 'unknown') snapshot.priority = priority;
    if (dueAt) snapshot.due_at = dueAt;
    requestSnapshot = Object.freeze(snapshot);
    summaryLines.push(`创建任务：${taskTitle}`);
    if (priority === 'low') summaryLines.push('优先级：低');
    if (priority === 'normal') summaryLines.push('优先级：普通');
    if (priority === 'high') summaryLines.push('优先级：高');
    if (dueAt) summaryLines.push(`截止时间：${dueAt}`);
  } else if (action === 'complete_task') {
    const taskKey = key(field(payload, 'task_id', 'taskId'));
    if (!taskKey) invalidResponse();
    const task = (Array.isArray(lookups.tasks) ? lookups.tasks : [])
      .find((candidate) => candidate?.key === taskKey);
    const taskTitle = title(task?.title);
    if (!taskTitle) targetUnavailable();
    requestSnapshot = Object.freeze({ task_id: taskKey });
    summaryLines.push(`完成任务：${taskTitle}`);
  } else if (action === 'start_focus_session') {
    const focusTitle = title(payload.title);
    if (!focusTitle) invalidResponse();
    requestSnapshot = Object.freeze({ title: focusTitle });
    summaryLines.push(`开始专注：${focusTitle}`);
  } else if (action === 'checkin_routine') {
    const routineKey = key(field(payload, 'routine_id', 'routineId'));
    if (!routineKey) invalidResponse();
    const routine = (Array.isArray(lookups.routines) ? lookups.routines : [])
      .find((candidate) => candidate?.key === routineKey);
    const routineTitle = title(routine?.title);
    if (!routineTitle) targetUnavailable();
    const note = normalizeBoundedText(
      payload.note, 1000, { preserveOuterWhitespace: true },
    );
    const snapshot = { routine_id: routineKey };
    if (note) snapshot.note = note;
    requestSnapshot = Object.freeze(snapshot);
    summaryLines.push(`照看习惯：${routineTitle}`);
    if (note) summaryLines.push(note);
  } else {
    const rawDate = payload.date;
    if (!rawDate) {
      requestSnapshot = Object.freeze({});
      summaryLines.push('为今天生成一份可编辑日记草稿');
    } else {
      if (typeof rawDate !== 'string' || !parseLocalAllDayToISO(rawDate)) invalidResponse();
      requestSnapshot = Object.freeze({ date: rawDate });
      summaryLines.push(`为 ${rawDate} 生成一份可编辑日记草稿`);
    }
  }

  return Object.freeze({
    previewKey,
    action,
    requestSnapshot,
    summaryLines: Object.freeze(summaryLines),
  });
}

export function adaptConfirmedActionResponse(raw, action) {
  if (action === 'create_task' || action === 'complete_task') return adaptTaskResponse(raw);
  if (action === 'start_focus_session') return adaptActivityResponse(raw);
  if (action === 'checkin_routine') return adaptRoutineCheckinResponse(raw);
  if (action === 'draft_diary') return adaptDiaryEntryResponse(raw);
  return invalidResponse();
}
