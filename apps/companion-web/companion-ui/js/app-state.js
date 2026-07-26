import {
  formatISOToLocalAllDay,
  formatISOToLocalTimed,
} from './shared/time.js';

const ACTIVE_SPACES = new Set(['today', 'outbox', 'memory', 'privacy']);
const VISUAL_TONES = new Set(['calm', 'warm', 'quiet', 'concerned', 'unknown']);
const ERROR_KINDS = new Set([
  'offline', 'timeout', 'validation', 'not-found', 'model-unavailable',
  'server', 'cancelled', 'unknown',
]);
const SAFE_ERROR_MESSAGES = {
  offline: '连接暂时远了一些。',
  timeout: '这次等待有些久。',
  validation: '这条内容暂时无法发送。',
  'not-found': '暂时找不到需要的内容。',
  'model-unavailable': '栖光暂时无法回应。',
  server: '连接暂时不稳定。',
  cancelled: '请求已取消。',
  unknown: '出现了暂时无法确认的问题。',
};

function initialReducedMotion() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function createTaskDraft() {
  return { title: '', description: '', dueAt: null, priority: 'normal' };
}

function createRoutineDraft() {
  return {
    title: '', schedule: 'daily', reminderPolicy: 'none', active: true,
  };
}

function createActivityDraft() {
  return { title: '', kind: 'focus' };
}

function createDiaryDraft() {
  return { date: null, title: '', body: '', status: 'saved' };
}

function createReminderDraft() {
  return { title: '', description: '', dueAt: '', recurrence: '' };
}

function createCalendarDraft() {
  return {
    title: '', allDay: false, startsAt: '', endsAt: '', startDate: '', endDate: '',
  };
}

function resourceDraft(resource) {
  if (resource === 'tasks') return createTaskDraft();
  if (resource === 'routines') return createRoutineDraft();
  if (resource === 'activities') return createActivityDraft();
  if (resource === 'diaries') return createDiaryDraft();
  if (resource === 'reminders') return createReminderDraft();
  return createCalendarDraft();
}

function createResourceState(resource) {
  return {
    status: 'unloaded',
    items: [],
    error: null,
    selectedIndex: null,
    editor: {
      mode: null,
      kind: null,
      draft: resourceDraft(resource),
      snapshot: null,
      status: 'idle',
      error: null,
    },
    action: {
      kind: null,
      transitionAction: null,
      status: 'idle',
      error: null,
      ...(resource === 'tasks' ? { confirmingArchive: false } : {}),
      ...(resource === 'routines' ? { confirmingDeactivate: false } : {}),
      ...(resource === 'diaries' ? { confirmingRemove: false } : {}),
      ...(resource === 'reminders' ? { confirmingCancel: false } : {}),
      ...(resource === 'calendarEvents' ? { confirmingRemove: false } : {}),
    },
    ...(resource === 'tasks' ? { stepDraft: '', stepWrites: [] } : {}),
  };
}

function createInitialState() {
  return {
    runtimeMode: 'fixture',
    appStatus: 'fixture',
    appError: null,
    activeSpace: null,
    lifeFlow: {
      view: 'today',
      today: { status: 'unloaded', data: null, error: null },
      timeline: { status: 'unloaded', items: [], error: null },
      tasks: createResourceState('tasks'),
      routines: createResourceState('routines'),
      activities: createResourceState('activities'),
      diaries: createResourceState('diaries'),
      reminders: createResourceState('reminders'),
      calendarEvents: createResourceState('calendarEvents'),
    },
    conversation: {
      draft: '',
      pendingDraft: '',
      pendingSubmissionId: null,
      chatStatus: 'idle',
      chatError: null,
    },
    presentation: {
      isKeyboardVisible: false,
      isReducedMotion: initialReducedMotion(),
    },
    viewModels: null,
  };
}

let state = createInitialState();
let messageCounter = 0;

function safeErrorDescriptor(error) {
  const kind = ERROR_KINDS.has(error?.kind) ? error.kind : 'unknown';
  return {
    kind,
    status: Number.isInteger(error?.status) ? error.status : null,
    message: SAFE_ERROR_MESSAGES[kind],
    retryable: typeof error?.retryable === 'boolean'
      ? error.retryable
      : !['validation', 'not-found', 'cancelled'].includes(kind),
  };
}

function safeScene(scene) {
  if (!scene || typeof scene !== 'object') {
    return null;
  }
  const caption = typeof scene.caption === 'string' ? scene.caption.trim().slice(0, 120) : '';
  const tone = VISUAL_TONES.has(scene.tone) ? scene.tone : 'unknown';
  return { caption, tone };
}

export function getState() {
  return JSON.parse(JSON.stringify(state));
}

export function initializeState(initialViewModels, options = {}) {
  const runtimeMode = options.runtimeMode === 'api' ? 'api' : 'fixture';
  state = createInitialState();
  state.runtimeMode = runtimeMode;
  state.appStatus = runtimeMode === 'api' ? 'loading' : 'fixture';
  state.conversation.draft = typeof options.initialDraft === 'string' ? options.initialDraft : '';
  state.viewModels = initialViewModels;
  messageCounter = 0;
}

export function beginInitialLoad() {
  if (state.runtimeMode !== 'api') return false;
  state.appStatus = 'loading';
  state.appError = null;
  return true;
}

export function completeInitialLoad(scene) {
  if (state.runtimeMode !== 'api' || !state.viewModels) return false;
  const nextScene = safeScene(scene);
  if (!nextScene) return false;
  state.viewModels.scene = nextScene;
  state.appStatus = 'ready';
  state.appError = null;
  return true;
}

export function hydrateConversationHistory(messages) {
  if (!state.viewModels?.conversation || !Array.isArray(messages)) return false;
  state.viewModels.conversation.messages = messages.flatMap((item) => {
    if (!item || (item.role !== 'user' && item.role !== 'assistant')) return [];
    const text = typeof item.text === 'string' ? item.text.trim().slice(0, 8_000) : '';
    return text ? [{
      id: typeof item.id === 'string' && item.id.trim() ? item.id.trim() : `history-${messageCounter++}`,
      role: item.role,
      text,
    }] : [];
  }).slice(-10);
  return true;
}

export function failInitialLoad(error) {
  if (state.runtimeMode !== 'api') return false;
  const descriptor = safeErrorDescriptor(error);
  state.appStatus = descriptor.retryable ? 'offline' : 'error';
  state.appError = descriptor;
  return true;
}

export function updateDraft(newDraft) {
  if (state.conversation.chatStatus === 'submitting') return false;
  state.conversation.draft = typeof newDraft === 'string' ? newDraft : '';
  if (state.conversation.chatStatus === 'error') {
    state.conversation.chatStatus = 'idle';
    state.conversation.chatError = null;
  }
  return true;
}

export function beginChatSubmission() {
  const draft = state.conversation.draft;
  const message = draft.trim();
  const canSend = state.runtimeMode === 'fixture' || state.appStatus === 'ready';
  if (!message || !state.viewModels || !canSend || state.conversation.chatStatus === 'submitting') {
    return null;
  }

  messageCounter += 1;
  const submissionId = `submission-${messageCounter}`;
  const history = (state.viewModels.conversation.messages ?? []).flatMap((item) => {
    if (!item || (item.role !== 'user' && item.role !== 'assistant') || typeof item.text !== 'string') return [];
    const content = item.text.trim();
    return content ? [{ role: item.role, content }] : [];
  }).slice(-10);

  state.conversation.pendingDraft = draft;
  state.conversation.pendingSubmissionId = submissionId;
  state.conversation.chatStatus = 'submitting';
  state.conversation.chatError = null;

  return Object.freeze({
    submissionId,
    draft,
    message,
    history,
    userMessageId: `api-user-${messageCounter}`,
    assistantMessageId: `api-assistant-${messageCounter}`,
  });
}

export function completeChatSubmission(payload, result) {
  if (
    state.conversation.chatStatus !== 'submitting'
    || !payload
    || payload.submissionId !== state.conversation.pendingSubmissionId
    || !state.viewModels
  ) return false;

  const assistant = result?.assistantMessage;
  const assistantText = typeof assistant?.text === 'string' ? assistant.text.trim() : '';
  if (!assistantText || assistant?.role !== 'assistant') return false;

  const nextMessages = [
    ...(state.viewModels.conversation.messages ?? []),
    { id: payload.userMessageId, role: 'user', text: payload.message },
    {
      id: typeof assistant.id === 'string' && assistant.id.trim()
        ? assistant.id.trim()
        : payload.assistantMessageId,
      role: 'assistant',
      text: assistantText,
    },
  ];
  state.viewModels.conversation.messages = nextMessages.slice(-10);

  const nextScene = safeScene(result.scene);
  if (nextScene) state.viewModels.scene = nextScene;

  state.conversation.draft = '';
  state.conversation.pendingDraft = '';
  state.conversation.pendingSubmissionId = null;
  state.conversation.chatStatus = 'idle';
  state.conversation.chatError = null;
  return true;
}

export function submitLocalConversation(userText) {
  if (state.runtimeMode !== 'fixture' || state.conversation.chatStatus === 'submitting') {
    return false;
  }
  state.conversation.draft = typeof userText === 'string' ? userText : '';
  const payload = beginChatSubmission();
  const fixtureConversation = state.viewModels?.conversation;
  if (!payload || !fixtureConversation?.localReply) {
    return false;
  }
  const completed = completeChatSubmission(payload, {
    assistantMessage: {
      id: `${fixtureConversation.localReply.idPrefix}-${messageCounter}`,
      role: 'assistant',
      text: fixtureConversation.localReply.text,
    },
    scene: fixtureConversation.sceneAfterLocalSend,
  });
  if (completed) {
    state.viewModels.conversation.messages = state.viewModels.conversation.messages.slice(-5);
  }
  return completed;
}

export function failChatSubmission(error) {
  if (state.conversation.chatStatus !== 'submitting') return false;
  const descriptor = safeErrorDescriptor(error);
  state.conversation.draft = state.conversation.pendingDraft;
  state.conversation.pendingDraft = '';
  state.conversation.pendingSubmissionId = null;

  if (descriptor.kind === 'cancelled') {
    state.conversation.chatStatus = 'idle';
    state.conversation.chatError = null;
    return true;
  }

  state.conversation.chatStatus = 'error';
  state.conversation.chatError = descriptor;
  return true;
}

const LIFE_FLOW_KINDS = new Set([
  'activity', 'calendar', 'reminder', 'task', 'routine', 'diary', 'outbox',
]);
const LIFE_FLOW_STATUSES = new Set([
  'open', 'in_progress', 'blocked', 'completed', 'cancelled', 'archived',
  'planned', 'active', 'paused', 'expired', 'scheduled', 'due', 'snoozed',
  'draft', 'saved', 'deleted', 'pending', 'unknown',
]);
const TODAY_LISTS = [
  'activeActivities', 'calendarEvents', 'dueTasks', 'routines',
  'overdueTasks', 'openTasks', 'completedTasks',
];
const LIFE_FLOW_VIEWS = new Set([
  'today', 'timeline',
  'tasks', 'task-detail', 'task-create', 'task-edit',
  'routines', 'routine-detail', 'routine-create', 'routine-edit',
  'activities', 'activity-detail', 'activity-create',
  'diaries', 'diary-detail', 'diary-create', 'diary-edit',
  'reminders', 'reminder-detail', 'reminder-create', 'reminder-edit',
  'calendar-events', 'calendar-detail', 'calendar-create', 'calendar-edit',
]);
const TASK_STATUSES = new Set([
  'open', 'in_progress', 'blocked', 'completed', 'cancelled', 'archived',
]);
const TASK_PRIORITIES = new Set(['low', 'normal', 'high']);
const STEP_STATUSES = new Set(['open', 'completed', 'cancelled']);
const ROUTINE_SCHEDULES = new Set(['daily', 'weekly']);
const ROUTINE_POLICIES = new Set(['none', 'remind']);
const CHECKIN_STATUSES = new Set(['none', 'pending', 'completed', 'skipped', 'unknown']);
const ACTIVITY_KINDS = new Set(['focus', 'checkin', 'planning', 'reflection']);
const ACTIVITY_STATUSES = new Set([
  'planned', 'active', 'paused', 'completed', 'cancelled', 'expired',
]);
const ACTIVITY_TRANSITIONS = Object.freeze({
  planned: new Set(['start', 'cancel']),
  active: new Set(['pause', 'complete', 'cancel']),
  paused: new Set(['resume', 'complete', 'cancel']),
});
const DIARY_STATUSES = new Set(['draft', 'saved', 'deleted']);
const REMINDER_STATUSES = new Set([
  'scheduled', 'due', 'snoozed', 'completed', 'cancelled', 'expired',
]);
const REMINDER_RECURRENCES = new Set(['daily', 'weekly']);
const REMINDER_TRANSITIONS = Object.freeze({
  scheduled: new Set(['complete', 'snooze', 'cancel']),
  due: new Set(['complete', 'snooze', 'cancel']),
  snoozed: new Set(['complete', 'snooze', 'cancel']),
});
const CALENDAR_STATUSES = new Set(['active', 'deleted']);
const RESOURCE_WRITE_KINDS = Object.freeze({
  tasks: new Set(['create', 'edit', 'transition', 'archive']),
  routines: new Set(['create', 'edit', 'checkin', 'deactivate']),
  activities: new Set(['create', 'transition']),
  diaries: new Set(['create', 'edit', 'draft', 'remove']),
  reminders: new Set(['create', 'edit', 'transition']),
  calendarEvents: new Set(['create', 'edit', 'remove']),
});

function boundedString(value, maxLength) {
  if (typeof value !== 'string') return '';
  return Array.from(value).slice(0, maxLength).join('');
}

function safeLifeFlowItem(item) {
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

function safeLifeFlowList(items) {
  if (!Array.isArray(items)) return [];
  const result = [];
  for (const item of items) {
    const safeItem = safeLifeFlowItem(item);
    if (safeItem) result.push(safeItem);
  }
  return result;
}

function safeTodayData(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const date = typeof data.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(data.date)
    ? data.date
    : null;
  const result = { date };
  for (const name of TODAY_LISTS) result[name] = safeLifeFlowList(data[name]);
  return result;
}

function safeInstant(value) {
  if (
    typeof value !== 'string'
    || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    || Number.isNaN(new Date(value).getTime())
  ) return null;
  return value;
}

function safeTaskStep(step) {
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

function safeTaskVM(item) {
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

function safeRoutineVM(item, previousStatus = 'none') {
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

function safeActivityVM(item) {
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

function safeDiaryVM(item) {
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

function safeReminderVM(item) {
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

function safeCalendarEventVM(item) {
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

function resourceState(resource) {
  return resource === 'tasks' || resource === 'routines'
    || resource === 'activities' || resource === 'diaries'
    || resource === 'reminders' || resource === 'calendarEvents'
    ? state.lifeFlow[resource]
    : null;
}

function resourceDetailView(resource) {
  if (resource === 'tasks') return 'task-detail';
  if (resource === 'routines') return 'routine-detail';
  if (resource === 'activities') return 'activity-detail';
  if (resource === 'diaries') return 'diary-detail';
  if (resource === 'reminders') return 'reminder-detail';
  return 'calendar-detail';
}

function resourceEditorView(resource, mode) {
  const singular = resource === 'tasks' ? 'task'
    : resource === 'routines' ? 'routine'
      : resource === 'activities' ? 'activity' : 'diary';
  if (resource === 'reminders') return `reminder-${mode}`;
  if (resource === 'calendarEvents') return `calendar-${mode}`;
  return `${singular}-${mode}`;
}

function selectedResourceItem(resource) {
  const domain = resourceState(resource);
  return domain && Number.isInteger(domain.selectedIndex)
    ? domain.items[domain.selectedIndex] ?? null
    : null;
}

export function showLifeFlowView(view) {
  if (!LIFE_FLOW_VIEWS.has(view) || state.lifeFlow.view === view) return false;
  state.lifeFlow.view = view;
  return true;
}

export function showTodayView() { return showLifeFlowView('today'); }
export function showTimelineView() { return showLifeFlowView('timeline'); }

export function beginResourceLoad(resource, refresh = false) {
  const domain = resourceState(resource);
  if (!domain || domain.status === 'loading' || domain.status === 'refreshing') return false;
  domain.status = refresh && domain.items.length > 0 ? 'refreshing' : 'loading';
  domain.error = null;
  return true;
}

export function completeResourceLoad(resource, items) {
  const domain = resourceState(resource);
  if (
    !domain
    || (domain.status !== 'loading' && domain.status !== 'refreshing')
    || !Array.isArray(items)
  ) return false;
  const previousCheckins = resource === 'routines'
    ? new Map(domain.items.map((item) => [item.key, item.checkinStatus]))
    : null;
  domain.items = items.flatMap((item) => {
    const safeItem = resource === 'tasks'
      ? safeTaskVM(item)
      : resource === 'routines' ? safeRoutineVM(
        item,
        previousCheckins.get(item?.key) === 'completed' ? 'completed' : 'none',
      ) : resource === 'activities' ? safeActivityVM(item)
        : resource === 'diaries' ? safeDiaryVM(item)
          : resource === 'reminders' ? safeReminderVM(item) : safeCalendarEventVM(item);
    return safeItem ? [safeItem] : [];
  });
  if (resource === 'diaries') {
    domain.items = domain.items
      .filter((item) => item.status !== 'deleted')
      .map((item, index) => ({ item, index }))
      .sort((left, right) => {
        if (left.item.date && right.item.date && left.item.date !== right.item.date) {
          return right.item.date.localeCompare(left.item.date);
        }
        if (left.item.date && !right.item.date) return -1;
        if (!left.item.date && right.item.date) return 1;
        return left.index - right.index;
      })
      .map(({ item }) => item);
  }
  if (resource === 'reminders') {
    domain.items = domain.items
      .map((item, index) => ({ item, index }))
      .sort((left, right) => new Date(left.item.dueAt).getTime()
        - new Date(right.item.dueAt).getTime()
        || left.index - right.index)
      .map(({ item }) => item);
  }
  if (resource === 'calendarEvents') {
    domain.items = domain.items
      .filter((item) => item.status !== 'deleted')
      .map((item, index) => ({ item, index }))
      .sort((left, right) => new Date(left.item.startsAt).getTime()
        - new Date(right.item.startsAt).getTime()
        || Number(right.item.allDay) - Number(left.item.allDay)
        || left.index - right.index)
      .map(({ item }) => item);
  }
  domain.status = 'ready';
  domain.error = null;
  domain.selectedIndex = null;
  return true;
}

export function failResourceLoad(resource, error) {
  const domain = resourceState(resource);
  if (!domain || (domain.status !== 'loading' && domain.status !== 'refreshing')) return false;
  domain.status = 'error';
  domain.error = safeErrorDescriptor(error);
  return true;
}

export function selectResourceItem(resource, key) {
  const domain = resourceState(resource);
  if (!domain || typeof key !== 'string' || !key) return false;
  const index = domain.items.findIndex((item) => item.key === key);
  if (index < 0) return false;
  domain.selectedIndex = index;
  domain.editor.mode = null;
  state.lifeFlow.view = resourceDetailView(resource);
  return true;
}

export function openResourceEditor(resource, mode) {
  const domain = resourceState(resource);
  if (!domain || (mode !== 'create' && mode !== 'edit')) return false;
  if (resource === 'activities' && mode !== 'create') return false;
  const selected = selectedResourceItem(resource);
  if (mode === 'edit' && !selected) return false;
  if (resource === 'diaries' && mode === 'edit'
    && !['draft', 'saved'].includes(selected.status)) return false;
  if (resource === 'reminders' && mode === 'edit'
    && !['scheduled', 'due', 'snoozed'].includes(selected.status)) return false;
  if (resource === 'calendarEvents' && mode === 'edit' && selected.status !== 'active') {
    return false;
  }
  domain.editor.mode = mode;
  domain.editor.kind = null;
  domain.editor.status = 'idle';
  domain.editor.error = null;
  domain.editor.snapshot = null;
  if (resource === 'tasks') {
    domain.editor.draft = mode === 'edit' ? {
      title: selected.title,
      description: selected.description ?? '',
      dueAt: selected.dueAt,
      priority: selected.priority,
    } : createTaskDraft();
  } else if (resource === 'routines') {
    domain.editor.draft = mode === 'edit' ? {
      title: selected.title,
      schedule: selected.schedule === 'unknown' ? 'daily' : selected.schedule,
      reminderPolicy: selected.reminderPolicy === 'unknown'
        ? 'none'
        : selected.reminderPolicy,
      active: selected.active,
    } : createRoutineDraft();
  } else if (resource === 'activities') domain.editor.draft = createActivityDraft();
  else if (resource === 'diaries') domain.editor.draft = mode === 'edit' ? {
    date: selected.date,
    title: selected.title,
    body: selected.body,
    status: selected.status,
  } : createDiaryDraft();
  else if (resource === 'reminders') domain.editor.draft = mode === 'edit' ? {
    title: selected.title,
    description: selected.description ?? '',
    dueAt: formatISOToLocalTimed(selected.dueAt) ?? '',
    recurrence: selected.recurrence ?? '',
  } : createReminderDraft();
  else domain.editor.draft = mode === 'edit' ? {
    title: selected.title,
    allDay: selected.allDay,
    startsAt: selected.allDay ? '' : formatISOToLocalTimed(selected.startsAt) ?? '',
    endsAt: selected.allDay ? '' : formatISOToLocalTimed(selected.endsAt) ?? '',
    startDate: selected.allDay ? formatISOToLocalAllDay(selected.startsAt) ?? '' : '',
    endDate: selected.allDay ? formatISOToLocalAllDay(selected.endsAt) ?? '' : '',
  } : createCalendarDraft();
  state.lifeFlow.view = resourceEditorView(resource, mode);
  return true;
}

export function updateResourceDraft(resource, field, value) {
  const domain = resourceState(resource);
  if (!domain || domain.editor.status === 'pending') return false;
  if (resource === 'tasks') {
    if ((field === 'title' || field === 'description') && typeof value === 'string') {
      domain.editor.draft[field] = value;
      return true;
    }
    if (field === 'dueAt' && (value === null || typeof value === 'string')) {
      domain.editor.draft.dueAt = value;
      return true;
    }
    if (field === 'priority' && TASK_PRIORITIES.has(value)) {
      domain.editor.draft.priority = value;
      return true;
    }
    return false;
  }
  if (resource === 'activities') {
    if (field === 'title' && typeof value === 'string') domain.editor.draft.title = value;
    else if (field === 'kind' && ACTIVITY_KINDS.has(value)) domain.editor.draft.kind = value;
    else return false;
    return true;
  }
  if (resource === 'diaries') {
    if ((field === 'title' || field === 'body') && typeof value === 'string') {
      domain.editor.draft[field] = value;
      return true;
    }
    return false;
  }
  if (resource === 'reminders') {
    if ((field === 'title' || field === 'description' || field === 'dueAt')
      && typeof value === 'string') domain.editor.draft[field] = value;
    else if (field === 'recurrence'
      && (value === '' || REMINDER_RECURRENCES.has(value))) {
      domain.editor.draft.recurrence = value;
    } else return false;
    return true;
  }
  if (resource === 'calendarEvents') {
    if (['title', 'startsAt', 'endsAt', 'startDate', 'endDate'].includes(field)
      && typeof value === 'string') domain.editor.draft[field] = value;
    else if (field === 'allDay' && typeof value === 'boolean') {
      domain.editor.draft.allDay = value;
    } else return false;
    return true;
  }
  if (field === 'title' && typeof value === 'string') domain.editor.draft.title = value;
  else if (field === 'schedule' && ROUTINE_SCHEDULES.has(value)) domain.editor.draft.schedule = value;
  else if (field === 'reminderPolicy' && ROUTINE_POLICIES.has(value)) {
    domain.editor.draft.reminderPolicy = value;
  } else if (field === 'active' && typeof value === 'boolean') domain.editor.draft.active = value;
  else return false;
  return true;
}

export function beginResourceWrite(resource, kind, action = null) {
  const domain = resourceState(resource);
  if (!domain || !RESOURCE_WRITE_KINDS[resource].has(kind)) return null;
  const isEditor = kind === 'create' || kind === 'edit';
  const target = isEditor ? domain.editor : domain.action;
  const selected = selectedResourceItem(resource);
  if (
    target.status === 'pending'
    || domain.editor.status === 'pending'
    || domain.action.status === 'pending'
    || (isEditor && domain.editor.mode !== kind)
    || (!isEditor && kind !== 'draft' && !selected)
    || (kind === 'archive' && !domain.action.confirmingArchive)
    || (kind === 'deactivate' && (!domain.action.confirmingDeactivate || !selected.active))
    || (kind === 'checkin' && (!selected.active || selected.checkinStatus === 'completed'))
    || (resource === 'activities' && kind === 'transition'
      && !ACTIVITY_TRANSITIONS[selected?.status]?.has(action))
    || (resource === 'reminders' && kind === 'transition'
      && (!REMINDER_TRANSITIONS[selected?.status]?.has(action)
        || (action === 'cancel' && !domain.action.confirmingCancel)))
    || (resource === 'diaries' && kind === 'remove'
      && (!domain.action.confirmingRemove || !['draft', 'saved'].includes(selected?.status)))
    || (resource === 'calendarEvents' && kind === 'remove'
      && (!domain.action.confirmingRemove || selected?.status !== 'active'))
  ) return null;
  target.kind = kind;
  if (resource === 'activities' || resource === 'reminders') target.transitionAction = action;
  target.status = 'pending';
  target.error = null;
  if (isEditor) {
    domain.editor.snapshot = { ...domain.editor.draft };
    return Object.freeze({ ...domain.editor.snapshot });
  }
  return Object.freeze({});
}

export function completeResourceWrite(resource, item) {
  const domain = resourceState(resource);
  if (!domain) return false;
  const target = domain.editor.status === 'pending'
    ? domain.editor
    : domain.action.status === 'pending' ? domain.action : null;
  if (!target) return false;
  const previous = domain.items.find((candidate) => candidate.key === item?.key);
  const safeItem = resource === 'tasks'
    ? safeTaskVM(item)
    : resource === 'routines'
      ? safeRoutineVM(item, previous?.checkinStatus)
      : resource === 'activities' ? safeActivityVM(item)
        : resource === 'diaries' ? safeDiaryVM(item)
          : resource === 'reminders' ? safeReminderVM(item) : safeCalendarEventVM(item);
  if (!safeItem) return false;
  if (resource === 'diaries' && target.kind === 'remove') {
    const selected = selectedResourceItem(resource);
    if (!selected || selected.key !== safeItem.key || safeItem.status !== 'deleted') return false;
    domain.items.splice(domain.selectedIndex, 1);
    domain.selectedIndex = null;
    target.kind = null;
    target.status = 'idle';
    target.error = null;
    domain.action.confirmingRemove = false;
    state.lifeFlow.view = 'diaries';
    return true;
  }
  if (resource === 'calendarEvents' && target.kind === 'remove') {
    const selected = selectedResourceItem(resource);
    if (!selected || selected.key !== safeItem.key || safeItem.status !== 'deleted') return false;
    domain.items.splice(domain.selectedIndex, 1);
    domain.selectedIndex = null;
    target.kind = null;
    target.status = 'idle';
    target.error = null;
    domain.action.confirmingRemove = false;
    state.lifeFlow.view = 'calendar-events';
    return true;
  }
  if (resource === 'diaries' && target.kind === 'draft') {
    if (safeItem.status !== 'draft') return false;
    const index = domain.items.findIndex((candidate) => candidate.key === safeItem.key);
    if (index >= 0) domain.items[index] = safeItem;
    else domain.items.unshift(safeItem);
    domain.selectedIndex = index >= 0 ? index : 0;
    target.kind = null;
    target.status = 'idle';
    target.error = null;
    domain.editor.mode = 'edit';
    domain.editor.draft = {
      date: safeItem.date, title: safeItem.title, body: safeItem.body, status: safeItem.status,
    };
    domain.editor.snapshot = null;
    state.lifeFlow.view = 'diary-edit';
    return true;
  }
  if (resource === 'diaries'
    && (target.kind === 'create' || target.kind === 'edit')
    && safeItem.status !== 'saved') return false;
  if (target.kind === 'create') {
    if (resource === 'diaries') {
      domain.items.unshift(safeItem);
      domain.selectedIndex = 0;
    } else {
      domain.items.push(safeItem);
      domain.selectedIndex = domain.items.length - 1;
    }
  } else {
    const selected = selectedResourceItem(resource);
    if (!selected || selected.key !== safeItem.key) return false;
    domain.items[domain.selectedIndex] = safeItem;
  }
  target.kind = null;
  if (resource === 'activities' || resource === 'reminders') target.transitionAction = null;
  target.status = 'idle';
  target.error = null;
  domain.editor.mode = null;
  domain.editor.snapshot = null;
  if (resource === 'tasks') domain.action.confirmingArchive = false;
  else if (resource === 'routines') domain.action.confirmingDeactivate = false;
  else if (resource === 'diaries') domain.action.confirmingRemove = false;
  else if (resource === 'reminders') domain.action.confirmingCancel = false;
  else if (resource === 'calendarEvents') domain.action.confirmingRemove = false;
  state.lifeFlow.view = resourceDetailView(resource);
  return true;
}

export function failResourceWrite(resource, error) {
  const domain = resourceState(resource);
  if (!domain) return false;
  const target = domain.editor.status === 'pending'
    ? domain.editor
    : domain.action.status === 'pending' ? domain.action : null;
  if (!target) return false;
  const descriptor = safeErrorDescriptor(error);
  if (target === domain.editor && domain.editor.snapshot) {
    domain.editor.draft = { ...domain.editor.snapshot };
    domain.editor.snapshot = null;
  }
  if (resource === 'activities' || resource === 'reminders') target.transitionAction = null;
  if (descriptor.kind === 'cancelled') {
    target.kind = null;
    target.status = 'idle';
    target.error = null;
  } else {
    target.status = 'error';
    target.error = descriptor;
  }
  return true;
}

export function setResourceConfirmation(resource, kind, enabled) {
  const domain = resourceState(resource);
  if (!domain || domain.action.status === 'pending' || typeof enabled !== 'boolean') return false;
  if (resource === 'tasks' && kind === 'archive') {
    domain.action.confirmingArchive = enabled;
    return true;
  }
  if (resource === 'routines' && kind === 'deactivate') {
    domain.action.confirmingDeactivate = enabled;
    return true;
  }
  if (resource === 'diaries' && kind === 'remove') {
    domain.action.confirmingRemove = enabled;
    return true;
  }
  if (resource === 'reminders' && kind === 'cancel') {
    domain.action.confirmingCancel = enabled;
    return true;
  }
  if (resource === 'calendarEvents' && kind === 'remove') {
    domain.action.confirmingRemove = enabled;
    return true;
  }
  return false;
}

function taskStepWrite(index) {
  return state.lifeFlow.tasks.stepWrites.find((entry) => entry.index === index) ?? null;
}

export function updateTaskStepDraft(value) {
  if (typeof value !== 'string' || taskStepWrite(-1)?.status === 'pending') return false;
  state.lifeFlow.tasks.stepDraft = value;
  return true;
}

export function beginTaskStepWrite(index, kind) {
  const tasks = state.lifeFlow.tasks;
  const selected = selectedResourceItem('tasks');
  if (
    !selected
    || tasks.editor.status === 'pending'
    || tasks.action.status === 'pending'
    || (kind !== 'add' && kind !== 'toggle')
    || (kind === 'add' && index !== -1)
    || (kind === 'toggle' && (!Number.isInteger(index) || index < 0 || !selected.steps[index]))
    || taskStepWrite(index)?.status === 'pending'
  ) return null;
  const current = kind === 'toggle' ? selected.steps[index] : null;
  if (current && current.status !== 'open' && current.status !== 'completed') return null;
  const entry = taskStepWrite(index) ?? { index, kind, status: 'idle', error: null };
  if (!taskStepWrite(index)) tasks.stepWrites.push(entry);
  entry.kind = kind;
  entry.status = 'pending';
  entry.error = null;
  return Object.freeze(kind === 'add'
    ? { title: tasks.stepDraft }
    : { status: current.status === 'completed' ? 'open' : 'completed' });
}

export function completeTaskStepWrite(index, step) {
  const entry = taskStepWrite(index);
  const selected = selectedResourceItem('tasks');
  const safeStep = safeTaskStep(step);
  if (!entry || entry.status !== 'pending' || !selected || !safeStep) return false;
  if (entry.kind === 'add' && index === -1) {
    selected.steps.push(safeStep);
    state.lifeFlow.tasks.stepDraft = '';
  } else if (
    entry.kind === 'toggle'
    && selected.steps[index]
    && selected.steps[index].key === safeStep.key
  ) selected.steps[index] = safeStep;
  else return false;
  entry.kind = null;
  entry.status = 'idle';
  entry.error = null;
  return true;
}

export function failTaskStepWrite(index, error) {
  const entry = taskStepWrite(index);
  if (!entry || entry.status !== 'pending') return false;
  const descriptor = safeErrorDescriptor(error);
  entry.kind = descriptor.kind === 'cancelled' ? null : entry.kind;
  entry.status = descriptor.kind === 'cancelled' ? 'idle' : 'error';
  entry.error = descriptor.kind === 'cancelled' ? null : descriptor;
  return true;
}

export function completeRoutineCheckin() {
  const routines = state.lifeFlow.routines;
  const selected = selectedResourceItem('routines');
  if (
    !selected
    || routines.action.status !== 'pending'
    || routines.action.kind !== 'checkin'
  ) return false;
  selected.checkinStatus = 'completed';
  routines.action.kind = null;
  routines.action.status = 'idle';
  routines.action.error = null;
  return true;
}

/** Applies only the safe result returned by a confirmed Action Preview. */
export function commitConfirmedActionResult(action, requestSnapshot, item) {
  if (!requestSnapshot || typeof requestSnapshot !== 'object') return false;
  if (action === 'create_task') {
    const safeItem = safeTaskVM(item);
    if (!safeItem) return false;
    const tasks = state.lifeFlow.tasks;
    if (tasks.status === 'ready') {
      const index = tasks.items.findIndex((candidate) => candidate.key === safeItem.key);
      if (index >= 0) tasks.items[index] = safeItem;
      else tasks.items.push(safeItem);
    }
    return true;
  }
  if (action === 'complete_task') {
    const safeItem = safeTaskVM(item);
    if (!safeItem || safeItem.key !== requestSnapshot.task_id) return false;
    const tasks = state.lifeFlow.tasks;
    const index = tasks.items.findIndex((candidate) => candidate.key === safeItem.key);
    if (index >= 0) tasks.items[index] = safeItem;
    return true;
  }
  if (action === 'start_focus_session') {
    const safeItem = safeActivityVM(item);
    if (!safeItem) return false;
    const activities = state.lifeFlow.activities;
    if (activities.status === 'ready') {
      const index = activities.items.findIndex((candidate) => candidate.key === safeItem.key);
      if (index >= 0) activities.items[index] = safeItem;
      else activities.items.push(safeItem);
    }
    return true;
  }
  if (action === 'checkin_routine') {
    if (!item || typeof item !== 'object' || item.status !== 'completed') return false;
    const routines = state.lifeFlow.routines;
    const index = routines.items.findIndex((candidate) => (
      candidate.key === requestSnapshot.routine_id
    ));
    if (index < 0) return false;
    routines.items[index].checkinStatus = 'completed';
    return true;
  }
  if (action === 'draft_diary') {
    const safeItem = safeDiaryVM(item);
    if (!safeItem || safeItem.status !== 'draft') return false;
    const diaries = state.lifeFlow.diaries;
    const existing = diaries.items.findIndex((candidate) => candidate.key === safeItem.key);
    if (existing >= 0) diaries.items[existing] = safeItem;
    else diaries.items.unshift(safeItem);
    diaries.status = 'ready';
    diaries.selectedIndex = existing >= 0 ? existing : 0;
    diaries.editor.mode = 'edit';
    diaries.editor.kind = null;
    diaries.editor.draft = {
      date: safeItem.date,
      title: safeItem.title,
      body: safeItem.body,
      status: safeItem.status,
    };
    diaries.editor.snapshot = null;
    diaries.editor.status = 'idle';
    diaries.editor.error = null;
    state.lifeFlow.view = 'diary-edit';
    state.activeSpace = 'today';
    return true;
  }
  return false;
}

function clearResourceTransient(resource) {
  const domain = resourceState(resource);
  if (!domain) return;
  domain.selectedIndex = null;
  domain.editor.mode = null;
  domain.editor.kind = null;
  domain.editor.snapshot = null;
  domain.editor.status = 'idle';
  domain.editor.error = null;
  domain.editor.draft = resourceDraft(resource);
  domain.action.kind = null;
  domain.action.transitionAction = null;
  domain.action.status = 'idle';
  domain.action.error = null;
  if (resource === 'tasks') {
    domain.action.confirmingArchive = false;
    domain.stepDraft = '';
    domain.stepWrites = [];
  } else if (resource === 'routines') domain.action.confirmingDeactivate = false;
  else if (resource === 'diaries') domain.action.confirmingRemove = false;
  else if (resource === 'reminders') domain.action.confirmingCancel = false;
  else if (resource === 'calendarEvents') domain.action.confirmingRemove = false;
}

export function resetResourceSubview(resource) {
  if (resource !== undefined && !resourceState(resource)) return false;
  if (resource) clearResourceTransient(resource);
  else {
    clearResourceTransient('tasks');
    clearResourceTransient('routines');
    clearResourceTransient('activities');
    clearResourceTransient('diaries');
    clearResourceTransient('reminders');
    clearResourceTransient('calendarEvents');
  }
  state.lifeFlow.view = 'today';
  return true;
}

export function beginTodayLoad(refresh = false) {
  const today = state.lifeFlow.today;
  if (today.status === 'loading' || today.status === 'refreshing') return false;
  today.status = refresh && today.data ? 'refreshing' : 'loading';
  today.error = null;
  return true;
}

export function completeTodayLoad(data) {
  const today = state.lifeFlow.today;
  if (today.status !== 'loading' && today.status !== 'refreshing') return false;
  const safeData = safeTodayData(data);
  if (!safeData) return false;
  today.data = safeData;
  today.status = 'ready';
  today.error = null;
  return true;
}

export function failTodayLoad(error) {
  const today = state.lifeFlow.today;
  if (today.status !== 'loading' && today.status !== 'refreshing') return false;
  today.status = 'error';
  today.error = safeErrorDescriptor(error);
  return true;
}

export function beginTimelineLoad() {
  const timeline = state.lifeFlow.timeline;
  if (timeline.status === 'loading') return false;
  timeline.status = 'loading';
  timeline.error = null;
  return true;
}

export function completeTimelineLoad(items) {
  const timeline = state.lifeFlow.timeline;
  if (timeline.status !== 'loading' || !Array.isArray(items)) return false;
  timeline.items = safeLifeFlowList(items);
  timeline.status = 'ready';
  timeline.error = null;
  return true;
}

export function failTimelineLoad(error) {
  const timeline = state.lifeFlow.timeline;
  if (timeline.status !== 'loading') return false;
  timeline.status = 'error';
  timeline.error = safeErrorDescriptor(error);
  return true;
}

export function setActiveSpace(space) {
  state.activeSpace = ACTIVE_SPACES.has(space) ? space : null;
}

export function setPresentationState(key, value) {
  if (Object.hasOwn(state.presentation, key) && typeof value === 'boolean') {
    state.presentation[key] = value;
  }
}
