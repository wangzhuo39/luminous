import { AppError } from '../shared/errors.js';
import { requestJson } from './api-client.js';

function requiredPathKey(key) {
  if (typeof key !== 'string' || !key.trim()) throw new AppError('validation');
  return encodeURIComponent(key);
}

function requiredAction(action, allowed) {
  if (!allowed.has(action)) throw new AppError('validation');
  return action;
}

function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(name, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

export function createLifeFlowApi({ request = requestJson } = {}) {
  return Object.freeze({
    loadToday({ date, signal } = {}) {
      return request(`/api/today${buildQuery({ date })}`, { signal });
    },
    loadTimeline({ from, to, kind, limit, signal } = {}) {
      return request(`/api/timeline${buildQuery({ from, to, kind, limit })}`, { signal });
    },

    loadTasks({ status, limit, signal } = {}) {
      return request(`/api/tasks${buildQuery({ status, limit })}`, { signal });
    },
    createTask({ input, signal }) {
      return request('/api/tasks', { method: 'POST', body: input, signal });
    },
    updateTask({ key, changes, signal }) {
      return request(`/api/tasks/${requiredPathKey(key)}`, {
        method: 'PATCH', body: changes, signal,
      });
    },
    addTaskStep({ taskKey, input, signal }) {
      return request(`/api/tasks/${requiredPathKey(taskKey)}/steps`, {
        method: 'POST', body: input, signal,
      });
    },
    updateTaskStep({ taskKey, stepKey, changes, signal }) {
      return request(
        `/api/tasks/${requiredPathKey(taskKey)}/steps/${requiredPathKey(stepKey)}`,
        { method: 'PATCH', body: changes, signal },
      );
    },
    transitionTask({ key, action, input, signal }) {
      requiredAction(action, new Set(['start', 'complete', 'block', 'cancel']));
      return request(`/api/tasks/${requiredPathKey(key)}/${action}`, {
        method: 'POST', body: input ?? {}, signal,
      });
    },
    archiveTask({ key, signal }) {
      return request(`/api/tasks/${requiredPathKey(key)}`, { method: 'DELETE', signal });
    },

    loadRoutines({ activeOnly, limit, signal } = {}) {
      return request(`/api/routines${buildQuery({
        active_only: activeOnly, limit,
      })}`, { signal });
    },
    createRoutine({ input, signal }) {
      return request('/api/routines', { method: 'POST', body: input, signal });
    },
    updateRoutine({ key, changes, signal }) {
      return request(`/api/routines/${requiredPathKey(key)}`, {
        method: 'PATCH', body: changes, signal,
      });
    },
    checkinRoutine({ key, input, signal }) {
      return request(`/api/routines/${requiredPathKey(key)}/checkins`, {
        method: 'POST', body: input, signal,
      });
    },
    deactivateRoutine({ key, signal }) {
      return request(`/api/routines/${requiredPathKey(key)}`, { method: 'DELETE', signal });
    },

    loadActivities({ status, limit, signal } = {}) {
      return request(`/api/activities${buildQuery({ status, limit })}`, { signal });
    },
    createActivity({ input, signal }) {
      return request('/api/activities', { method: 'POST', body: input, signal });
    },
    transitionActivity({ key, action, input, signal }) {
      requiredAction(action, new Set(['start', 'pause', 'resume', 'complete', 'cancel']));
      return request(`/api/activities/${requiredPathKey(key)}/${action}`, {
        method: 'POST', body: input ?? {}, signal,
      });
    },

    loadDiaryEntries({ date, limit, signal } = {}) {
      return request(`/api/diary-entries${buildQuery({ date, limit })}`, { signal });
    },
    createDiaryEntry({ input, signal }) {
      return request('/api/diary-entries', { method: 'POST', body: input, signal });
    },
    draftDiaryEntry({ date, signal }) {
      return request('/api/diary-entries/draft', {
        method: 'POST', body: date ? { date } : {}, signal,
      });
    },
    updateDiaryEntry({ key, changes, signal }) {
      return request(`/api/diary-entries/${requiredPathKey(key)}`, {
        method: 'PATCH', body: changes, signal,
      });
    },
    removeDiaryEntry({ key, signal }) {
      return request(`/api/diary-entries/${requiredPathKey(key)}`, {
        method: 'DELETE', signal,
      });
    },

    loadReminders({ status, limit, signal } = {}) {
      return request(`/api/reminders${buildQuery({ status, limit })}`, { signal });
    },
    createReminder({ input, signal }) {
      return request('/api/reminders', { method: 'POST', body: input, signal });
    },
    updateReminder({ key, changes, signal }) {
      return request(`/api/reminders/${requiredPathKey(key)}`, {
        method: 'PATCH', body: changes, signal,
      });
    },
    transitionReminder({ key, action, input, signal }) {
      requiredAction(action, new Set(['snooze', 'complete', 'cancel']));
      if (action === 'snooze' && (typeof input?.due_at !== 'string' || !input.due_at.trim())) {
        throw new AppError('validation');
      }
      return request(`/api/reminders/${requiredPathKey(key)}/${action}`, {
        method: 'POST', body: input ?? {}, signal,
      });
    },

    loadCalendarEvents({ limit, signal } = {}) {
      return request(`/api/calendar-events${buildQuery({ limit })}`, { signal });
    },
    createCalendarEvent({ input, signal }) {
      return request('/api/calendar-events', { method: 'POST', body: input, signal });
    },
    updateCalendarEvent({ key, changes, signal }) {
      return request(`/api/calendar-events/${requiredPathKey(key)}`, {
        method: 'PATCH', body: changes, signal,
      });
    },
    removeCalendarEvent({ key, signal }) {
      return request(`/api/calendar-events/${requiredPathKey(key)}`, {
        method: 'DELETE', signal,
      });
    },

    previewAction({ proposal, signal }) {
      if (!proposal || typeof proposal !== 'object' || Array.isArray(proposal)) {
        throw new AppError('validation');
      }
      return request('/api/actions/preview', { method: 'POST', body: proposal, signal });
    },
    confirmAction({ preview, signal }) {
      if (
        !preview
        || typeof preview !== 'object'
        || typeof preview.action !== 'string'
        || !preview.action
        || !preview.requestSnapshot
        || typeof preview.requestSnapshot !== 'object'
        || Array.isArray(preview.requestSnapshot)
      ) throw new AppError('validation');
      return request('/api/actions/confirm', {
        method: 'POST',
        body: {
          action: preview.action,
          payload: preview.requestSnapshot,
          confirmed: true,
        },
        signal,
      });
    },
  });
}

export const lifeFlowApi = createLifeFlowApi();
export default lifeFlowApi;
