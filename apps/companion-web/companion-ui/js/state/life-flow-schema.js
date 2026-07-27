import {
  formatISOToLocalAllDay,
  formatISOToLocalTimed,
} from '../shared/time.js';

export const LIFE_FLOW_KINDS = new Set([
  'activity', 'calendar', 'reminder', 'task', 'routine', 'diary', 'outbox',
]);
export const LIFE_FLOW_STATUSES = new Set([
  'open', 'in_progress', 'blocked', 'completed', 'cancelled', 'archived',
  'planned', 'active', 'paused', 'expired', 'scheduled', 'due', 'snoozed',
  'draft', 'saved', 'deleted', 'pending', 'unknown',
]);
export const TODAY_LISTS = [
  'activeActivities', 'calendarEvents', 'dueTasks', 'routines',
  'overdueTasks', 'openTasks', 'completedTasks',
];
export const LIFE_FLOW_VIEWS = new Set([
  'today', 'timeline',
  'tasks', 'task-detail', 'task-create', 'task-edit',
  'routines', 'routine-detail', 'routine-create', 'routine-edit',
  'activities', 'activity-detail', 'activity-create',
  'diaries', 'diary-detail', 'diary-create', 'diary-edit',
  'reminders', 'reminder-detail', 'reminder-create', 'reminder-edit',
  'calendar-events', 'calendar-detail', 'calendar-create', 'calendar-edit',
]);
export const TASK_STATUSES = new Set([
  'open', 'in_progress', 'blocked', 'completed', 'cancelled', 'archived',
]);
export const TASK_PRIORITIES = new Set(['low', 'normal', 'high']);
export const STEP_STATUSES = new Set(['open', 'completed', 'cancelled']);
export const ROUTINE_SCHEDULES = new Set(['daily', 'weekly']);
export const ROUTINE_POLICIES = new Set(['none', 'remind']);
export const CHECKIN_STATUSES = new Set(['none', 'pending', 'completed', 'skipped', 'unknown']);
export const ACTIVITY_KINDS = new Set(['focus', 'checkin', 'planning', 'reflection']);
export const ACTIVITY_STATUSES = new Set([
  'planned', 'active', 'paused', 'completed', 'cancelled', 'expired',
]);
export const ACTIVITY_TRANSITIONS = Object.freeze({
  planned: new Set(['start', 'cancel']),
  active: new Set(['pause', 'complete', 'cancel']),
  paused: new Set(['resume', 'complete', 'cancel']),
});
export const DIARY_STATUSES = new Set(['draft', 'saved', 'deleted']);
export const REMINDER_STATUSES = new Set([
  'scheduled', 'due', 'snoozed', 'completed', 'cancelled', 'expired',
]);
export const REMINDER_RECURRENCES = new Set(['daily', 'weekly']);
export const REMINDER_TRANSITIONS = Object.freeze({
  scheduled: new Set(['complete', 'snooze', 'cancel']),
  due: new Set(['complete', 'snooze', 'cancel']),
  snoozed: new Set(['complete', 'snooze', 'cancel']),
});
export const CALENDAR_STATUSES = new Set(['active', 'deleted']);
export const RESOURCE_WRITE_KINDS = Object.freeze({
  tasks: new Set(['create', 'edit', 'transition', 'archive']),
  routines: new Set(['create', 'edit', 'checkin', 'deactivate']),
  activities: new Set(['create', 'transition']),
  diaries: new Set(['create', 'edit', 'draft', 'remove']),
  reminders: new Set(['create', 'edit', 'transition']),
  calendarEvents: new Set(['create', 'edit', 'remove']),
});

export function boundedString(value, maxLength) {
  if (typeof value !== 'string') return '';
  return Array.from(value).slice(0, maxLength).join('');
}

export function safeLifeFlowItem(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const key = boundedString(item.key, 256).trim();
  const title = boundedString(item.title, 160).trim();
  if (!key || !title) return null;
  const occurredAt = typeof item.occurredAt === 'string'
    && /(?:Z|[+-]\d{2}:\d{2})$/.test(item.occurredAt)
    && !Number.isNaN(new Date(item.occurredAt).getTime())
    ? item.occurredAt
    : null;
  return {
    key,
    kind: LIFE_FLOW_KINDS.has(item.kind) ? item.kind : 'unknown',
    title,
    status: LIFE_FLOW_STATUSES.has(item.status) ? item.status : 'unknown',
    occurredAt,
  };
}

export function safeLifeFlowList(items) {
  if (!Array.isArray(items)) return [];
  const result = [];
  for (const item of items) {
    const safeItem = safeLifeFlowItem(item);
    if (safeItem) result.push(safeItem);
  }
  return result;
}

export function safeTodayData(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const date = typeof data.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(data.date)
    ? data.date
    : null;
  const result = { date };
  for (const name of TODAY_LISTS) result[name] = safeLifeFlowList(data[name]);
  return result;
}

export function safeInstant(value) {
  if (
    typeof value !== 'string'
    || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    || Number.isNaN(new Date(value).getTime())
  ) return null;
  return value;
}

export function safeTaskStep(step) {
  if (!step || typeof step !== 'object' || Array.isArray(step)) return null;
  const key = boundedString(step.key, 256).trim();
  const title = boundedString(step.title, 160).trim();
  if (!key || !title) return null;
  return {
    key,
    title,
    status: STEP_STATUSES.has(step.status) ? step.status : 'unknown',
  };
}

export function safeTaskVM(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const key = boundedString(item.key, 256).trim();
  const title = boundedString(item.title, 160).trim();
  if (!key || !title) return null;
  return {
    key,
    title,
    description: typeof item.description === 'string'
      ? boundedString(item.description, 2000)
      : null,
    status: TASK_STATUSES.has(item.status) ? item.status : 'unknown',
    dueAt: safeInstant(item.dueAt),
    priority: TASK_PRIORITIES.has(item.priority) ? item.priority : 'normal',
    steps: Array.isArray(item.steps) ? item.steps.flatMap((step) => {
      const safeStep = safeTaskStep(step);
      return safeStep ? [safeStep] : [];
    }) : [],
  };
}

export function safeRoutineVM(item, previousStatus = 'none') {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const key = boundedString(item.key, 256).trim();
  const title = boundedString(item.title, 160).trim();
  if (!key || !title) return null;
  return {
    key,
    title,
    schedule: ROUTINE_SCHEDULES.has(item.schedule) ? item.schedule : 'unknown',
    active: typeof item.active === 'boolean' ? item.active : false,
    reminderPolicy: ROUTINE_POLICIES.has(item.reminderPolicy)
      ? item.reminderPolicy
      : 'unknown',
    checkinStatus: CHECKIN_STATUSES.has(previousStatus) ? previousStatus : 'none',
  };
}

export function safeActivityVM(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const key = boundedString(item.key, 256).trim();
  const title = boundedString(item.title, 160).trim();
  if (!key || !title) return null;
  return {
    key,
    kind: ACTIVITY_KINDS.has(item.kind) ? item.kind : 'unknown',
    title,
    status: ACTIVITY_STATUSES.has(item.status) ? item.status : 'unknown',
    startedAt: safeInstant(item.startedAt),
    endedAt: safeInstant(item.endedAt),
    summary: typeof item.summary === 'string'
      ? boundedString(item.summary, 2000)
      : null,
  };
}

export function safeDiaryVM(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const key = boundedString(item.key, 256).trim();
  const title = boundedString(item.title, 160).trim();
  if (!key || !title) return null;
  const date = typeof item.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.date)
    ? item.date
    : null;
  return {
    key,
    date,
    title,
    body: typeof item.body === 'string' ? boundedString(item.body, 20000) : '',
    status: DIARY_STATUSES.has(item.status) ? item.status : 'unknown',
    updatedAt: safeInstant(item.updatedAt),
  };
}

export function safeReminderVM(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const key = boundedString(item.key, 256).trim();
  const title = boundedString(item.title, 160).trim();
  const dueAt = safeInstant(item.dueAt);
  if (!key || !title || !dueAt) return null;
  return {
    key,
    title,
    description: typeof item.description === 'string'
      ? boundedString(item.description, 2000)
      : null,
    dueAt,
    timezoneName: boundedString(item.timezoneName, 128).trim() || 'UTC',
    recurrence: REMINDER_RECURRENCES.has(item.recurrence) ? item.recurrence : null,
    status: REMINDER_STATUSES.has(item.status) ? item.status : 'unknown',
  };
}

export function safeCalendarEventVM(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const key = boundedString(item.key, 256).trim();
  const title = boundedString(item.title, 160).trim();
  const startsAt = safeInstant(item.startsAt);
  if (!key || !title || !startsAt) return null;
  return {
    key,
    title,
    startsAt,
    endsAt: item.endsAt === null ? null : safeInstant(item.endsAt),
    allDay: item.allDay === true,
    timezoneName: boundedString(item.timezoneName, 128).trim() || 'UTC',
    status: CALENDAR_STATUSES.has(item.status) ? item.status : 'unknown',
  };
}

