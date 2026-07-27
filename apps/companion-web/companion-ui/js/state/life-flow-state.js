import {
  appStore,
  ACTIVE_SPACES,
  createActivityDraft,
  createCalendarDraft,
  createDiaryDraft,
  createReminderDraft,
  createRoutineDraft,
  createTaskDraft,
  resourceDraft,
  safeErrorDescriptor,
} from './app-store.js';
import {
  formatISOToLocalAllDay,
  formatISOToLocalTimed,
} from '../shared/time.js';
import {
  LIFE_FLOW_VIEWS,
  TASK_PRIORITIES,
  ROUTINE_SCHEDULES,
  ROUTINE_POLICIES,
  ACTIVITY_KINDS,
  ACTIVITY_TRANSITIONS,
  REMINDER_RECURRENCES,
  REMINDER_TRANSITIONS,
  RESOURCE_WRITE_KINDS,
  safeLifeFlowList,
  safeTodayData,
  safeTaskStep,
  safeTaskVM,
  safeRoutineVM,
  safeActivityVM,
  safeDiaryVM,
  safeReminderVM,
  safeCalendarEventVM,
} from './life-flow-schema.js';

function resourceState(resource) {
  return resource === 'tasks' || resource === 'routines'
    || resource === 'activities' || resource === 'diaries'
    || resource === 'reminders' || resource === 'calendarEvents'
    ? appStore.state.lifeFlow[resource]
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
  if (!LIFE_FLOW_VIEWS.has(view) || appStore.state.lifeFlow.view === view) return false;
  appStore.state.lifeFlow.view = view;
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
  appStore.state.lifeFlow.view = resourceDetailView(resource);
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
  appStore.state.lifeFlow.view = resourceEditorView(resource, mode);
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
    appStore.state.lifeFlow.view = 'diaries';
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
    appStore.state.lifeFlow.view = 'calendar-events';
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
    appStore.state.lifeFlow.view = 'diary-edit';
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
  appStore.state.lifeFlow.view = resourceDetailView(resource);
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
  return appStore.state.lifeFlow.tasks.stepWrites.find((entry) => entry.index === index) ?? null;
}

export function updateTaskStepDraft(value) {
  if (typeof value !== 'string' || taskStepWrite(-1)?.status === 'pending') return false;
  appStore.state.lifeFlow.tasks.stepDraft = value;
  return true;
}

export function beginTaskStepWrite(index, kind) {
  const tasks = appStore.state.lifeFlow.tasks;
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
    appStore.state.lifeFlow.tasks.stepDraft = '';
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
  const routines = appStore.state.lifeFlow.routines;
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
    const tasks = appStore.state.lifeFlow.tasks;
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
    const tasks = appStore.state.lifeFlow.tasks;
    const index = tasks.items.findIndex((candidate) => candidate.key === safeItem.key);
    if (index >= 0) tasks.items[index] = safeItem;
    return true;
  }
  if (action === 'start_focus_session') {
    const safeItem = safeActivityVM(item);
    if (!safeItem) return false;
    const activities = appStore.state.lifeFlow.activities;
    if (activities.status === 'ready') {
      const index = activities.items.findIndex((candidate) => candidate.key === safeItem.key);
      if (index >= 0) activities.items[index] = safeItem;
      else activities.items.push(safeItem);
    }
    return true;
  }
  if (action === 'checkin_routine') {
    if (!item || typeof item !== 'object' || item.status !== 'completed') return false;
    const routines = appStore.state.lifeFlow.routines;
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
    const diaries = appStore.state.lifeFlow.diaries;
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
    appStore.state.lifeFlow.view = 'diary-edit';
    appStore.state.activeSpace = 'today';
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
  appStore.state.lifeFlow.view = 'today';
  return true;
}

export function beginTodayLoad(refresh = false) {
  const today = appStore.state.lifeFlow.today;
  if (today.status === 'loading' || today.status === 'refreshing') return false;
  today.status = refresh && today.data ? 'refreshing' : 'loading';
  today.error = null;
  return true;
}

export function completeTodayLoad(data) {
  const today = appStore.state.lifeFlow.today;
  if (today.status !== 'loading' && today.status !== 'refreshing') return false;
  const safeData = safeTodayData(data);
  if (!safeData) return false;
  today.data = safeData;
  today.status = 'ready';
  today.error = null;
  return true;
}

export function failTodayLoad(error) {
  const today = appStore.state.lifeFlow.today;
  if (today.status !== 'loading' && today.status !== 'refreshing') return false;
  today.status = 'error';
  today.error = safeErrorDescriptor(error);
  return true;
}

export function beginTimelineLoad() {
  const timeline = appStore.state.lifeFlow.timeline;
  if (timeline.status === 'loading') return false;
  timeline.status = 'loading';
  timeline.error = null;
  return true;
}

export function completeTimelineLoad(items) {
  const timeline = appStore.state.lifeFlow.timeline;
  if (timeline.status !== 'loading' || !Array.isArray(items)) return false;
  timeline.items = safeLifeFlowList(items);
  timeline.status = 'ready';
  timeline.error = null;
  return true;
}

export function failTimelineLoad(error) {
  const timeline = appStore.state.lifeFlow.timeline;
  if (timeline.status !== 'loading') return false;
  timeline.status = 'error';
  timeline.error = safeErrorDescriptor(error);
  return true;
}

export function setActiveSpace(space) {
  appStore.state.activeSpace = ACTIVE_SPACES.has(space) ? space : null;
}

export function setPresentationState(key, value) {
  if (Object.hasOwn(appStore.state.presentation, key) && typeof value === 'boolean') {
    appStore.state.presentation[key] = value;
  }
}
