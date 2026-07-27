export const ACTIVE_SPACES = new Set(['today', 'outbox', 'memory', 'privacy']);
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

export function createTaskDraft() {
  return { title: '', description: '', dueAt: null, priority: 'normal' };
}

export function createRoutineDraft() {
  return {
    title: '', schedule: 'daily', reminderPolicy: 'none', active: true,
  };
}

export function createActivityDraft() {
  return { title: '', kind: 'focus' };
}

export function createDiaryDraft() {
  return { date: null, title: '', body: '', status: 'saved' };
}

export function createReminderDraft() {
  return { title: '', description: '', dueAt: '', recurrence: '' };
}

export function createCalendarDraft() {
  return {
    title: '', allDay: false, startsAt: '', endsAt: '', startDate: '', endDate: '',
  };
}

export function resourceDraft(resource) {
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

export function createInitialState() {
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

export const appStore = {
  state: createInitialState(),
  messageCounter: 0,
};

export function safeErrorDescriptor(error) {
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

export function safeScene(scene) {
  if (!scene || typeof scene !== 'object') {
    return null;
  }
  const caption = typeof scene.caption === 'string' ? scene.caption.trim().slice(0, 120) : '';
  const tone = VISUAL_TONES.has(scene.tone) ? scene.tone : 'unknown';
  return { caption, tone };
}

export function getState() {
  return JSON.parse(JSON.stringify(appStore.state));
}
