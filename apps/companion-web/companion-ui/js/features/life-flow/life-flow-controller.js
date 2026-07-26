import {
  beginResourceLoad,
  beginResourceWrite,
  beginTaskStepWrite,
  beginTimelineLoad,
  beginTodayLoad,
  completeResourceLoad,
  completeResourceWrite,
  completeRoutineCheckin,
  completeTaskStepWrite,
  completeTimelineLoad,
  completeTodayLoad,
  failResourceLoad,
  failResourceWrite,
  failTaskStepWrite,
  failTimelineLoad,
  failTodayLoad,
  getState,
  openResourceEditor,
  resetResourceSubview,
  selectResourceItem,
  setResourceConfirmation,
  showLifeFlowView,
  showTimelineView,
  showTodayView,
  updateResourceDraft,
  updateTaskStepDraft,
} from '../../app-state.js';
import { createOperationGate } from '../../shared/operation.js';
import {
  getBrowserTimeZone,
  isISOInstant,
  isValidTimeRange,
  parseLocalAllDayToISO,
  parseLocalTimedToISO,
} from '../../shared/time.js';

const RESOURCE_VIEWS = Object.freeze({
  tasks: new Set(['tasks', 'task-detail', 'task-create', 'task-edit']),
  routines: new Set(['routines', 'routine-detail', 'routine-create', 'routine-edit']),
  activities: new Set(['activities', 'activity-detail', 'activity-create']),
  diaries: new Set(['diaries', 'diary-detail', 'diary-create', 'diary-edit']),
  reminders: new Set(['reminders', 'reminder-detail', 'reminder-create', 'reminder-edit']),
  calendarEvents: new Set([
    'calendar-events', 'calendar-detail', 'calendar-create', 'calendar-edit',
  ]),
});

function resourceForView(view) {
  if (RESOURCE_VIEWS.tasks.has(view)) return 'tasks';
  if (RESOURCE_VIEWS.routines.has(view)) return 'routines';
  if (RESOURCE_VIEWS.activities.has(view)) return 'activities';
  if (RESOURCE_VIEWS.diaries.has(view)) return 'diaries';
  if (RESOURCE_VIEWS.reminders.has(view)) return 'reminders';
  if (RESOURCE_VIEWS.calendarEvents.has(view)) return 'calendarEvents';
  return null;
}

function validationError() {
  return { kind: 'validation', retryable: false };
}

function taskInput(draft) {
  if (typeof draft?.title !== 'string' || draft.title.trim() === '') throw validationError();
  let dueAt = null;
  if (typeof draft.dueAt === 'string' && draft.dueAt !== '') {
    dueAt = isISOInstant(draft.dueAt) ? draft.dueAt : parseLocalTimedToISO(draft.dueAt);
    if (!dueAt) throw validationError();
  }
  return Object.freeze({
    title: draft.title,
    description: typeof draft.description === 'string' ? draft.description : '',
    due_at: dueAt,
    priority: draft.priority,
  });
}

function routineInput(draft) {
  if (typeof draft?.title !== 'string' || draft.title.trim() === '') throw validationError();
  return Object.freeze({
    title: draft.title,
    schedule: draft.schedule,
    reminder_policy: draft.reminderPolicy,
    active: draft.active === true,
  });
}

function activityInput(draft) {
  if (typeof draft?.title !== 'string' || draft.title.trim() === '') throw validationError();
  if (!['focus', 'checkin', 'planning', 'reflection'].includes(draft.kind)) {
    throw validationError();
  }
  return Object.freeze({ title: draft.title, kind: draft.kind });
}

function fallbackLocalDate() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `${String(date.getFullYear()).padStart(4, '0')}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function diaryInput(draft, localDate) {
  if (typeof draft?.title !== 'string' || draft.title.trim() === '') throw validationError();
  if (typeof draft?.body !== 'string' || draft.body.trim() === '') throw validationError();
  const date = typeof draft.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(draft.date)
    ? draft.date
    : localDate;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw validationError();
  return Object.freeze({
    date,
    title: draft.title,
    body: draft.body,
    status: 'saved',
  });
}

function reminderInput(draft) {
  if (typeof draft?.title !== 'string' || draft.title.trim() === '') throw validationError();
  const dueAt = isISOInstant(draft.dueAt)
    ? draft.dueAt
    : parseLocalTimedToISO(draft.dueAt);
  if (!dueAt) throw validationError();
  if (draft.recurrence && !['daily', 'weekly'].includes(draft.recurrence)) {
    throw validationError();
  }
  return Object.freeze({
    title: draft.title,
    description: typeof draft.description === 'string' ? draft.description : '',
    due_at: dueAt,
    timezone_name: getBrowserTimeZone(),
    recurrence: draft.recurrence || null,
  });
}

function calendarInput(draft) {
  if (typeof draft?.title !== 'string' || draft.title.trim() === '') throw validationError();
  const allDay = draft.allDay === true;
  const startValue = allDay ? draft.startDate : draft.startsAt;
  const endValue = allDay ? draft.endDate : draft.endsAt;
  const startsAt = allDay
    ? parseLocalAllDayToISO(startValue)
    : isISOInstant(startValue) ? startValue : parseLocalTimedToISO(startValue);
  const endsAt = !endValue ? null : allDay
    ? parseLocalAllDayToISO(endValue)
    : isISOInstant(endValue) ? endValue : parseLocalTimedToISO(endValue);
  if (!startsAt || (endValue && !endsAt) || !isValidTimeRange(startsAt, endsAt)) {
    throw validationError();
  }
  return Object.freeze({
    title: draft.title,
    starts_at: startsAt,
    ends_at: endsAt,
    all_day: allDay,
    timezone_name: getBrowserTimeZone(),
  });
}

function changedReminderFields(current, input) {
  if (!current) return input;
  const fields = {};
  if (input.title !== current.title) fields.title = input.title;
  if (input.description !== (current.description ?? '')) fields.description = input.description;
  if (input.due_at !== current.dueAt) fields.due_at = input.due_at;
  if (input.timezone_name !== current.timezoneName) fields.timezone_name = input.timezone_name;
  if (input.recurrence !== current.recurrence) fields.recurrence = input.recurrence;
  return Object.freeze(fields);
}

function changedCalendarFields(current, input) {
  if (!current) return input;
  const fields = {};
  if (input.title !== current.title) fields.title = input.title;
  if (input.starts_at !== current.startsAt) fields.starts_at = input.starts_at;
  if (input.ends_at !== current.endsAt) fields.ends_at = input.ends_at;
  if (input.all_day !== current.allDay) fields.all_day = input.all_day;
  if (input.timezone_name !== current.timezoneName) fields.timezone_name = input.timezone_name;
  return Object.freeze(fields);
}

function resourceListView(resource) {
  return resource === 'calendarEvents' ? 'calendar-events' : resource;
}

function resourceSingular(resource) {
  if (resource === 'tasks') return 'task';
  if (resource === 'routines') return 'routine';
  if (resource === 'activities') return 'activity';
  if (resource === 'diaries') return 'diary';
  if (resource === 'reminders') return 'reminder';
  return 'calendar';
}

function resourceLabel(resource) {
  if (resource === 'tasks') return '任务';
  if (resource === 'routines') return '日常';
  if (resource === 'activities') return '活动';
  if (resource === 'diaries') return '日记';
  if (resource === 'reminders') return '提醒';
  return '日历刻度';
}

export function initLifeFlow(dom, {
  dataSource,
  announce,
  onStateChange,
  eventTarget = window,
  isOnline = () => navigator.onLine,
  localDate = fallbackLocalDate,
}) {
  const todayGate = createOperationGate('today-load');
  const timelineGate = createOperationGate('timeline-load');
  const resources = [
    'tasks', 'routines', 'activities', 'diaries', 'reminders', 'calendarEvents',
  ];
  const resourceLoads = Object.fromEntries(resources.map((resource) => [resource, {
    gate: createOperationGate(`${resource}-load`), operation: null,
  }]));
  const resourceWrites = Object.fromEntries(resources.map((resource) => [resource, {
    gate: createOperationGate(`${resource}-write`), operation: null,
  }]));
  const stepOperations = new Map();
  let todayOperation = null;
  let timelineOperation = null;
  let destroyed = false;

  function visibleErrorMessage(screen, fallback) {
    const domain = getState().lifeFlow?.[screen];
    return domain?.error?.message || fallback;
  }

  async function runLoad({
    gate, getOperation, setOperation, begin, complete, fail, request, screen, refresh = false,
  }) {
    if (destroyed) return false;
    const token = gate.begin();
    if (!token) return false;
    const controller = new AbortController();
    setOperation({ token, controller });
    if (!begin(refresh)) {
      gate.cancel(token);
      setOperation(null);
      return false;
    }
    onStateChange();

    try {
      const result = await request(controller.signal);
      if (destroyed || !gate.isCurrent(token)) return false;
      gate.finish(token);
      if (!complete(result)) {
        fail({ kind: 'server', retryable: true });
        onStateChange();
        return false;
      }
      if (getState().lifeFlow?.view === screen) {
        announce(screen === 'today' ? '今日光影已经展开。' : '时间线已经展开。');
      }
      onStateChange();
      return true;
    } catch (error) {
      if (destroyed || !gate.isCurrent(token)) return false;
      gate.finish(token);
      if (error?.kind === 'cancelled') return false;
      if (!fail(error)) return false;
      if (getState().lifeFlow?.view === screen) {
        announce(visibleErrorMessage(
          screen,
          screen === 'today' ? '今日暂时没有展开。' : '时间线暂时没有展开。',
        ));
      }
      onStateChange();
      return false;
    } finally {
      if (getOperation()?.token === token) setOperation(null);
    }
  }

  function loadToday(refresh) {
    const status = getState().lifeFlow?.today?.status;
    if (!refresh && (status === 'ready' || status === 'refreshing')) {
      return Promise.resolve(true);
    }
    return runLoad({
      gate: todayGate,
      getOperation: () => todayOperation,
      setOperation: (value) => { todayOperation = value; },
      begin: beginTodayLoad,
      complete: completeTodayLoad,
      fail: failTodayLoad,
      request: (signal) => dataSource.loadToday({ signal }),
      screen: 'today',
      refresh,
    });
  }

  function loadTimeline(refresh = false) {
    const status = getState().lifeFlow?.timeline?.status;
    if (!refresh && status === 'ready') return Promise.resolve(true);
    return runLoad({
      gate: timelineGate,
      getOperation: () => timelineOperation,
      setOperation: (value) => { timelineOperation = value; },
      begin: beginTimelineLoad,
      complete: completeTimelineLoad,
      fail: failTimelineLoad,
      request: (signal) => dataSource.loadTimeline({ limit: 100, signal }),
      screen: 'timeline',
    });
  }

  async function loadResource(resource, refresh = false) {
    if (destroyed || !resourceLoads[resource] || resourceWrites[resource].gate.isPending()) {
      return false;
    }
    const status = getState().lifeFlow?.[resource]?.status;
    if (!refresh && status === 'ready') return true;
    const slot = resourceLoads[resource];
    const token = slot.gate.begin();
    if (!token) return false;
    const controller = new AbortController();
    slot.operation = { token, controller };
    if (!beginResourceLoad(resource, refresh)) {
      slot.gate.cancel(token);
      slot.operation = null;
      return false;
    }
    onStateChange();
    try {
      const resolvedItems = resource === 'tasks'
        ? await dataSource.loadTasks({ limit: 100, signal: controller.signal })
        : resource === 'routines'
          ? await dataSource.loadRoutines({
            activeOnly: false, limit: 100, signal: controller.signal,
          })
          : resource === 'activities'
            ? await dataSource.loadActivities({ limit: 100, signal: controller.signal })
            : resource === 'diaries'
              ? await dataSource.loadDiaryEntries({ limit: 100, signal: controller.signal })
              : resource === 'reminders'
                ? await dataSource.loadReminders({ limit: 100, signal: controller.signal })
                : await dataSource.loadCalendarEvents({ limit: 100, signal: controller.signal });
      if (destroyed || !slot.gate.isCurrent(token)) return false;
      slot.gate.finish(token);
      if (!completeResourceLoad(resource, resolvedItems)) {
        failResourceLoad(resource, { kind: 'server', retryable: true });
        onStateChange();
        return false;
      }
      if (resourceForView(getState().lifeFlow.view) === resource) {
        announce(`${resourceLabel(resource)}已经展开。`);
      }
      onStateChange();
      return true;
    } catch (error) {
      if (destroyed || !slot.gate.isCurrent(token)) return false;
      slot.gate.finish(token);
      if (error?.kind === 'cancelled') return false;
      if (failResourceLoad(resource, error)) {
        announce(`${resourceLabel(resource)}暂时没有展开。`);
        onStateChange();
      }
      return false;
    } finally {
      if (slot.operation?.token === token) slot.operation = null;
    }
  }

  function refreshTodayAfterWrite() {
    void loadToday(true);
  }

  async function runResourceWrite(
    resource, kind, request, complete = completeResourceWrite, transitionAction = null,
  ) {
    if (destroyed || !resourceWrites[resource] || resourceLoads[resource].gate.isPending()) {
      return false;
    }
    const slot = resourceWrites[resource];
    const token = slot.gate.begin();
    if (!token) return false;
    const snapshot = beginResourceWrite(resource, kind, transitionAction);
    if (!snapshot) {
      slot.gate.cancel(token);
      return false;
    }
    const controller = new AbortController();
    slot.operation = { token, controller };
    onStateChange();
    try {
      const result = await request({ snapshot, signal: controller.signal });
      if (destroyed || !slot.gate.isCurrent(token)) return false;
      slot.gate.finish(token);
      if (!complete(resource, result)) {
        failResourceWrite(resource, { kind: 'server', retryable: true });
        onStateChange();
        return false;
      }
      announce(`${resourceLabel(resource)}已经记下。`);
      onStateChange();
      refreshTodayAfterWrite();
      return true;
    } catch (error) {
      if (destroyed || !slot.gate.isCurrent(token)) return false;
      slot.gate.finish(token);
      if (error?.kind === 'cancelled') return false;
      if (failResourceWrite(resource, error)) {
        announce(`${resourceLabel(resource)}暂时没有更新。`);
        onStateChange();
      }
      return false;
    } finally {
      if (slot.operation?.token === token) slot.operation = null;
    }
  }

  function selected(resource) {
    const domain = getState().lifeFlow?.[resource];
    return Number.isInteger(domain?.selectedIndex)
      ? domain.items[domain.selectedIndex] ?? null
      : null;
  }

  function submitResource(resource) {
    const domain = getState().lifeFlow?.[resource];
    const mode = domain?.editor?.mode;
    if (mode !== 'create' && mode !== 'edit') return Promise.resolve(false);
    const current = selected(resource);
    return runResourceWrite(resource, mode, ({ snapshot, signal }) => {
      const input = resource === 'tasks' ? taskInput(snapshot)
        : resource === 'routines' ? routineInput(snapshot)
          : resource === 'activities' ? activityInput(snapshot)
            : resource === 'diaries' ? diaryInput(snapshot, localDate())
              : resource === 'reminders' ? reminderInput(snapshot) : calendarInput(snapshot);
      if (mode === 'create') {
        return resource === 'tasks'
          ? dataSource.createTask({ input, signal })
          : resource === 'routines'
            ? dataSource.createRoutine({ input, signal })
            : resource === 'activities'
              ? dataSource.createActivity({ input, signal })
              : resource === 'diaries' ? dataSource.createDiaryEntry({ input, signal })
                : resource === 'reminders' ? dataSource.createReminder({ input, signal })
                  : dataSource.createCalendarEvent({ input, signal });
      }
      if (!current) throw { kind: 'not-found', retryable: false };
      return resource === 'tasks'
        ? dataSource.updateTask({ key: current.key, changes: input, signal })
        : resource === 'routines'
          ? dataSource.updateRoutine({ key: current.key, changes: input, signal })
          : resource === 'diaries'
            ? dataSource.updateDiaryEntry({ key: current.key, changes: input, signal })
            : resource === 'reminders'
              ? dataSource.updateReminder({
                key: current.key, changes: changedReminderFields(current, input), signal,
              })
              : dataSource.updateCalendarEvent({
                key: current.key, changes: changedCalendarFields(current, input), signal,
              });
    });
  }

  function runTaskAction(kind, action = null) {
    const task = selected('tasks');
    if (!task) return Promise.resolve(false);
    return runResourceWrite('tasks', kind, ({ signal }) => {
      if (kind === 'archive') return dataSource.archiveTask({ key: task.key, signal });
      return dataSource.transitionTask({ key: task.key, action, input: {}, signal });
    });
  }

  function runRoutineAction(kind) {
    const routine = selected('routines');
    if (!routine) return Promise.resolve(false);
    if (kind === 'checkin') {
      return runResourceWrite(
        'routines',
        kind,
        ({ signal }) => dataSource.checkinRoutine({ key: routine.key, input: {}, signal }),
        () => completeRoutineCheckin(),
      );
    }
    return runResourceWrite(
      'routines',
      kind,
      ({ signal }) => dataSource.deactivateRoutine({ key: routine.key, signal }),
    );
  }

  function runActivityAction(action) {
    const activity = selected('activities');
    if (!activity) return Promise.resolve(false);
    return runResourceWrite(
      'activities',
      'transition',
      ({ signal }) => dataSource.transitionActivity({
        key: activity.key, action, input: {}, signal,
      }),
      completeResourceWrite,
      action,
    );
  }

  function generateDiaryDraft() {
    return runResourceWrite(
      'diaries',
      'draft',
      ({ signal }) => dataSource.draftDiaryEntry({ date: localDate(), signal }),
    );
  }

  function removeDiary() {
    const diary = selected('diaries');
    if (!diary) return Promise.resolve(false);
    return runResourceWrite(
      'diaries',
      'remove',
      ({ signal }) => dataSource.removeDiaryEntry({ key: diary.key, signal }),
    );
  }

  function runReminderAction(action, dueAt = null) {
    const reminder = selected('reminders');
    if (!reminder) return Promise.resolve(false);
    return runResourceWrite(
      'reminders',
      'transition',
      ({ signal }) => {
        let input = {};
        if (action === 'snooze') {
          const parsedDueAt = isISOInstant(dueAt) ? dueAt : parseLocalTimedToISO(dueAt);
          if (!parsedDueAt) throw validationError();
          input = { due_at: parsedDueAt };
        }
        return dataSource.transitionReminder({ key: reminder.key, action, input, signal });
      },
      completeResourceWrite,
      action,
    );
  }

  function removeCalendarEvent() {
    const event = selected('calendarEvents');
    if (!event) return Promise.resolve(false);
    return runResourceWrite(
      'calendarEvents',
      'remove',
      ({ signal }) => dataSource.removeCalendarEvent({ key: event.key, signal }),
    );
  }

  async function runStepWrite(index, kind) {
    if (destroyed || stepOperations.has(index) || resourceWrites.tasks.gate.isPending()) return false;
    const task = selected('tasks');
    const step = kind === 'toggle' ? task?.steps?.[index] : null;
    if (!task || (kind === 'toggle' && !step)) return false;
    const payload = beginTaskStepWrite(index, kind);
    if (!payload) return false;
    const gate = createOperationGate(`task-step-${index}`);
    const token = gate.begin();
    const controller = new AbortController();
    stepOperations.set(index, { gate, token, controller });
    onStateChange();
    try {
      if (kind === 'add' && payload.title.trim() === '') throw validationError();
      const result = kind === 'add'
        ? await dataSource.addTaskStep({
          taskKey: task.key, input: { title: payload.title }, signal: controller.signal,
        })
        : await dataSource.updateTaskStep({
          taskKey: task.key,
          stepKey: step.key,
          changes: { status: payload.status },
          signal: controller.signal,
        });
      const operation = stepOperations.get(index);
      if (destroyed || operation?.token !== token || !gate.isCurrent(token)) return false;
      gate.finish(token);
      if (!completeTaskStepWrite(index, result)) {
        failTaskStepWrite(index, { kind: 'server', retryable: true });
        onStateChange();
        return false;
      }
      announce(kind === 'add' ? '这一步已经加上。' : '这一步已经更新。');
      onStateChange();
      refreshTodayAfterWrite();
      return true;
    } catch (error) {
      const operation = stepOperations.get(index);
      if (destroyed || operation?.token !== token || !gate.isCurrent(token)) return false;
      gate.finish(token);
      if (error?.kind !== 'cancelled' && failTaskStepWrite(index, error)) {
        announce('这一步暂时没有更新。');
        onStateChange();
      }
      return false;
    } finally {
      if (stepOperations.get(index)?.token === token) stepOperations.delete(index);
    }
  }

  const ensureTodayLoaded = () => loadToday(false);
  const refreshToday = () => loadToday(true);
  const revealTimeline = () => {
    if (showTimelineView()) onStateChange();
    if (getState().lifeFlow?.timeline?.status === 'unloaded') void loadTimeline();
  };
  const backToToday = () => {
    if (showTodayView()) {
      announce('已回到今日。');
      onStateChange();
    }
  };
  const retryTimeline = () => loadTimeline(true);

  function openResource(resource) {
    if (!RESOURCE_VIEWS[resource]) return false;
    const changed = showLifeFlowView(resourceListView(resource));
    if (changed) onStateChange();
    const status = getState().lifeFlow[resource].status;
    if (status === 'unloaded' || status === 'error') void loadResource(resource, status === 'error');
    return changed;
  }

  async function openResourceItem(resource, key) {
    if (!RESOURCE_VIEWS[resource] || typeof key !== 'string' || key === '') return false;
    if (showLifeFlowView(resourceListView(resource))) onStateChange();
    const status = getState().lifeFlow[resource].status;
    if (status !== 'ready' && !await loadResource(resource, status === 'error')) return false;
    if (!selectResourceItem(resource, key)) {
      announce(`暂时找不到这个${resourceLabel(resource)}。`);
      return false;
    }
    onStateChange();
    return true;
  }

  function backFromResource(resource) {
    const state = getState().lifeFlow;
    if (
      state[resource].editor.status === 'pending'
      || state[resource].action.status === 'pending'
      || (resource === 'tasks' && stepOperations.size > 0)
    ) return false;
    if (state.view === resourceListView(resource)) {
      if (resetResourceSubview(resource)) {
        announce('已回到今日。');
        onStateChange();
        return true;
      }
      return false;
    }
    const editor = state[resource].editor;
    const next = state.view.endsWith('-edit') || editor.mode === 'edit'
      ? `${resourceSingular(resource)}-detail`
      : resourceListView(resource);
    if (showLifeFlowView(next)) {
      onStateChange();
      return true;
    }
    return false;
  }

  function chooseResourceItem(resource, index) {
    const item = getState().lifeFlow?.[resource]?.items?.[index];
    if (!item || !selectResourceItem(resource, item.key)) return false;
    onStateChange();
    return true;
  }

  function handleTaskEvent(event) {
    if (destroyed || !event || typeof event.type !== 'string') return false;
    switch (event.type) {
      case 'BACK': return backFromResource('tasks');
      case 'CREATE':
        if (openResourceEditor('tasks', 'create')) { onStateChange(); return true; }
        return false;
      case 'SELECT': return chooseResourceItem('tasks', event.index);
      case 'EDIT':
        if (openResourceEditor('tasks', 'edit')) { onStateChange(); return true; }
        return false;
      case 'FIELD':
        if (updateResourceDraft('tasks', event.field, event.value)) { onStateChange(); return true; }
        return false;
      case 'SUBMIT': return submitResource('tasks');
      case 'CANCEL_EDIT': return backFromResource('tasks');
      case 'TRANSITION': return runTaskAction('transition', event.action);
      case 'ARCHIVE_INTENT':
        if (setResourceConfirmation('tasks', 'archive', true)) { onStateChange(); return true; }
        return false;
      case 'ARCHIVE_CONFIRM': return runTaskAction('archive');
      case 'ARCHIVE_CANCEL':
        if (setResourceConfirmation('tasks', 'archive', false)) { onStateChange(); return true; }
        return false;
      case 'STEP_FIELD':
        if (updateTaskStepDraft(event.value)) { onStateChange(); return true; }
        return false;
      case 'STEP_ADD': return runStepWrite(-1, 'add');
      case 'STEP_TOGGLE': return runStepWrite(event.index, 'toggle');
      case 'RETRY_LOAD': return loadResource('tasks', true);
      default: return false;
    }
  }

  function handleRoutineEvent(event) {
    if (destroyed || !event || typeof event.type !== 'string') return false;
    switch (event.type) {
      case 'BACK': return backFromResource('routines');
      case 'CREATE':
        if (openResourceEditor('routines', 'create')) { onStateChange(); return true; }
        return false;
      case 'SELECT': return chooseResourceItem('routines', event.index);
      case 'EDIT':
        if (openResourceEditor('routines', 'edit')) { onStateChange(); return true; }
        return false;
      case 'FIELD':
        if (updateResourceDraft('routines', event.field, event.value)) { onStateChange(); return true; }
        return false;
      case 'SUBMIT': return submitResource('routines');
      case 'CANCEL_EDIT': return backFromResource('routines');
      case 'CHECKIN': return runRoutineAction('checkin');
      case 'DEACTIVATE_INTENT':
        if (setResourceConfirmation('routines', 'deactivate', true)) {
          onStateChange(); return true;
        }
        return false;
      case 'DEACTIVATE_CONFIRM': return runRoutineAction('deactivate');
      case 'DEACTIVATE_CANCEL':
        if (setResourceConfirmation('routines', 'deactivate', false)) {
          onStateChange(); return true;
        }
        return false;
      case 'RETRY_LOAD': return loadResource('routines', true);
      default: return false;
    }
  }

  function handleActivityEvent(event) {
    if (destroyed || !event || typeof event.type !== 'string') return false;
    switch (event.type) {
      case 'BACK': return backFromResource('activities');
      case 'CREATE':
        if (openResourceEditor('activities', 'create')) { onStateChange(); return true; }
        return false;
      case 'SELECT': return chooseResourceItem('activities', event.index);
      case 'FIELD':
        if (updateResourceDraft('activities', event.field, event.value)) {
          onStateChange(); return true;
        }
        return false;
      case 'SUBMIT': return submitResource('activities');
      case 'CANCEL_EDIT': return backFromResource('activities');
      case 'TRANSITION': return runActivityAction(event.action);
      case 'RETRY_LOAD': return loadResource('activities', true);
      default: return false;
    }
  }

  function handleDiaryEvent(event) {
    if (destroyed || !event || typeof event.type !== 'string') return false;
    switch (event.type) {
      case 'BACK': return backFromResource('diaries');
      case 'CREATE':
        if (openResourceEditor('diaries', 'create')) { onStateChange(); return true; }
        return false;
      case 'GENERATE': return generateDiaryDraft();
      case 'SELECT': return chooseResourceItem('diaries', event.index);
      case 'EDIT':
        if (openResourceEditor('diaries', 'edit')) { onStateChange(); return true; }
        return false;
      case 'FIELD':
        if (updateResourceDraft('diaries', event.field, event.value)) {
          onStateChange(); return true;
        }
        return false;
      case 'SUBMIT': return submitResource('diaries');
      case 'CANCEL_EDIT': return backFromResource('diaries');
      case 'REMOVE_INTENT':
        if (setResourceConfirmation('diaries', 'remove', true)) {
          onStateChange(); return true;
        }
        return false;
      case 'REMOVE_CONFIRM': return removeDiary();
      case 'REMOVE_CANCEL':
        if (setResourceConfirmation('diaries', 'remove', false)) {
          onStateChange(); return true;
        }
        return false;
      case 'RETRY_LOAD': return loadResource('diaries', true);
      default: return false;
    }
  }

  function handleReminderEvent(event) {
    if (destroyed || !event || typeof event.type !== 'string') return false;
    switch (event.type) {
      case 'BACK': return backFromResource('reminders');
      case 'CREATE':
        if (openResourceEditor('reminders', 'create')) { onStateChange(); return true; }
        return false;
      case 'SELECT': return chooseResourceItem('reminders', event.index);
      case 'EDIT':
        if (openResourceEditor('reminders', 'edit')) { onStateChange(); return true; }
        return false;
      case 'FIELD':
        if (updateResourceDraft('reminders', event.field, event.value)) {
          onStateChange(); return true;
        }
        return false;
      case 'SUBMIT': return submitResource('reminders');
      case 'CANCEL_EDIT': return backFromResource('reminders');
      case 'COMPLETE': return runReminderAction('complete');
      case 'SNOOZE': return runReminderAction('snooze', event.dueAt);
      case 'CANCEL_INTENT':
        if (setResourceConfirmation('reminders', 'cancel', true)) {
          onStateChange(); return true;
        }
        return false;
      case 'CANCEL_CONFIRM': return runReminderAction('cancel');
      case 'CANCEL_DISMISS':
        if (setResourceConfirmation('reminders', 'cancel', false)) {
          onStateChange(); return true;
        }
        return false;
      case 'RETRY_LOAD': return loadResource('reminders', true);
      default: return false;
    }
  }

  function handleCalendarEvent(event) {
    if (destroyed || !event || typeof event.type !== 'string') return false;
    switch (event.type) {
      case 'BACK': return backFromResource('calendarEvents');
      case 'CREATE':
        if (openResourceEditor('calendarEvents', 'create')) { onStateChange(); return true; }
        return false;
      case 'SELECT': return chooseResourceItem('calendarEvents', event.index);
      case 'EDIT':
        if (openResourceEditor('calendarEvents', 'edit')) { onStateChange(); return true; }
        return false;
      case 'FIELD':
        if (updateResourceDraft('calendarEvents', event.field, event.value)) {
          onStateChange(); return true;
        }
        return false;
      case 'SUBMIT': return submitResource('calendarEvents');
      case 'CANCEL_EDIT': return backFromResource('calendarEvents');
      case 'REMOVE_INTENT':
        if (setResourceConfirmation('calendarEvents', 'remove', true)) {
          onStateChange(); return true;
        }
        return false;
      case 'REMOVE_CONFIRM': return removeCalendarEvent();
      case 'REMOVE_CANCEL':
        if (setResourceConfirmation('calendarEvents', 'remove', false)) {
          onStateChange(); return true;
        }
        return false;
      case 'RETRY_LOAD': return loadResource('calendarEvents', true);
      default: return false;
    }
  }

  function failPending(screen) {
    const operation = screen === 'today' ? todayOperation : timelineOperation;
    const gate = screen === 'today' ? todayGate : timelineGate;
    if (!operation || !gate.isCurrent(operation.token)) return false;
    operation.controller.abort();
    gate.cancel(operation.token);
    screen === 'today' ? failTodayLoad({ kind: 'offline', retryable: true })
      : failTimelineLoad({ kind: 'offline', retryable: true });
    announce('连接暂时远了一些。');
    onStateChange();
    return true;
  }

  function failResourceOperationsOffline() {
    let changed = false;
    for (const resource of resources) {
      const load = resourceLoads[resource];
      if (load.operation && load.gate.isCurrent(load.operation.token)) {
        load.operation.controller.abort();
        load.gate.cancel(load.operation.token);
        changed = failResourceLoad(resource, { kind: 'offline', retryable: true }) || changed;
      }
      const write = resourceWrites[resource];
      if (write.operation && write.gate.isCurrent(write.operation.token)) {
        write.operation.controller.abort();
        write.gate.cancel(write.operation.token);
        changed = failResourceWrite(resource, { kind: 'offline', retryable: true }) || changed;
      }
    }
    for (const [index, operation] of stepOperations) {
      operation.controller.abort();
      operation.gate.cancel(operation.token);
      changed = failTaskStepWrite(index, { kind: 'offline', retryable: true }) || changed;
      stepOperations.delete(index);
    }
    if (changed) {
      announce('连接暂时远了一些。');
      onStateChange();
    }
    return changed;
  }

  function handleOnline() {
    if (destroyed || !dom.dialog?.open || isOnline() === false) return;
    const lifeFlow = getState().lifeFlow;
    if (lifeFlow.view === 'today' && lifeFlow.today.error?.retryable) void refreshToday();
    else if (lifeFlow.view === 'timeline' && lifeFlow.timeline.error?.retryable) {
      void retryTimeline();
    } else {
      const resource = resourceForView(lifeFlow.view);
      if (resource && lifeFlow[resource].status === 'error'
        && lifeFlow[resource].error?.retryable) void loadResource(resource, true);
    }
  }

  function handleOffline() {
    if (destroyed) return;
    const view = getState().lifeFlow?.view;
    if (view === 'today' || view === 'timeline') failPending(view);
    failResourceOperationsOffline();
  }

  function handleDialogClose() {
    if (destroyed) return;
    for (const resource of resources) {
      const load = resourceLoads[resource];
      if (load.operation && load.gate.isCurrent(load.operation.token)) {
        load.operation.controller.abort();
        load.gate.cancel(load.operation.token);
        failResourceLoad(resource, { kind: 'cancelled', retryable: false });
        load.operation = null;
      }
      const write = resourceWrites[resource];
      if (write.operation && write.gate.isCurrent(write.operation.token)) {
        write.operation.controller.abort();
        write.gate.cancel(write.operation.token);
        failResourceWrite(resource, { kind: 'cancelled', retryable: false });
        write.operation = null;
      }
    }
    for (const [index, operation] of stepOperations) {
      operation.controller.abort();
      operation.gate.cancel(operation.token);
      failTaskStepWrite(index, { kind: 'cancelled', retryable: false });
    }
    stepOperations.clear();
    resetResourceSubview();
    onStateChange();
  }

  const listeners = [
    [dom.portal, 'click', ensureTodayLoaded],
    [dom.refresh, 'click', refreshToday],
    [dom.todayRetry, 'click', refreshToday],
    [dom.timelineReveal, 'click', revealTimeline],
    [dom.timelineBack, 'click', backToToday],
    [dom.timelineRetry, 'click', retryTimeline],
    [dom.tasksOpen, 'click', () => openResource('tasks')],
    [dom.routinesOpen, 'click', () => openResource('routines')],
    [dom.activitiesOpen, 'click', () => openResource('activities')],
    [dom.diariesOpen, 'click', () => openResource('diaries')],
    [dom.remindersOpen, 'click', () => openResource('reminders')],
    [dom.calendarOpen, 'click', () => openResource('calendarEvents')],
    [dom.dialog, 'close', handleDialogClose],
    [eventTarget, 'online', handleOnline],
    [eventTarget, 'offline', handleOffline],
  ];
  listeners.forEach(([target, event, handler]) => target?.addEventListener?.(event, handler));

  return Object.freeze({
    ensureTodayLoaded,
    refreshToday,
    revealTimeline,
    backToToday,
    openTasks: () => openResource('tasks'),
    openRoutines: () => openResource('routines'),
    openActivities: () => openResource('activities'),
    openDiaries: () => openResource('diaries'),
    openReminders: () => openResource('reminders'),
    openCalendar: () => openResource('calendarEvents'),
    openResourceItem,
    handleTaskEvent,
    handleRoutineEvent,
    handleActivityEvent,
    handleDiaryEvent,
    handleReminderEvent,
    handleCalendarEvent,
    destroy() {
      destroyed = true;
      for (const [gate, operation] of [
        [todayGate, todayOperation], [timelineGate, timelineOperation],
        ...Object.values(resourceLoads).map((slot) => [slot.gate, slot.operation]),
        ...Object.values(resourceWrites).map((slot) => [slot.gate, slot.operation]),
      ]) {
        operation?.controller.abort();
        if (operation && gate.isCurrent(operation.token)) gate.cancel(operation.token);
      }
      for (const operation of stepOperations.values()) {
        operation.controller.abort();
        if (operation.gate.isCurrent(operation.token)) operation.gate.cancel(operation.token);
      }
      stepOperations.clear();
      todayOperation = null;
      timelineOperation = null;
      listeners.forEach(([target, event, handler]) => (
        target?.removeEventListener?.(event, handler)
      ));
    },
  });
}
