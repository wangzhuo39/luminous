import { AppError } from '../shared/errors.js';
import { requestJson } from './api-client.js';

function buildQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  });
  const value = query.toString();
  return value ? `?${value}` : '';
}

function requiredKey(value) {
  if (typeof value !== 'string' || !value.trim()) throw new AppError('validation');
  return value.trim();
}

export function createSilentSpacesApi({ request = requestJson } = {}) {
  return Object.freeze({
    loadOutbox({ status, limit = 20, signal } = {}) {
      return request(`/api/outbox${buildQuery({ status, limit })}`, { signal });
    },
    markOutboxRead({ key, signal }) {
      return request('/api/outbox/receipt', {
        method: 'POST', body: { message_id: requiredKey(key), receipt_type: 'read' }, signal,
      });
    },
    sendOutboxFeedback({ key, status, signal }) {
      if (!new Set(['helpful', 'not_needed']).has(status)) throw new AppError('validation');
      return request('/api/outbox/feedback', {
        method: 'POST', body: { message_id: requiredKey(key), status }, signal,
      });
    },
    searchMemory({ query, limit = 8, signal }) {
      const safeQuery = typeof query === 'string' ? query.trim() : '';
      if (!safeQuery) throw new AppError('validation');
      return request(`/api/memory${buildQuery({ q: safeQuery, limit })}`, { signal });
    },
    updateMemory({ key, text, signal }) {
      const safeText = typeof text === 'string' ? text.trim() : '';
      if (!safeText) throw new AppError('validation');
      return request('/api/memory/update', {
        method: 'POST', body: { memory_id: requiredKey(key), updates: { text: safeText } }, signal,
      });
    },
    forgetMemory({ key, signal }) {
      return request('/api/memory/forget', {
        method: 'POST', body: { memory_id: requiredKey(key), hard_delete: false }, signal,
      });
    },
    loadPrivacy({ signal } = {}) {
      return Promise.all([
        request('/api/settings/notifications', { signal }),
        request('/api/state', { signal }),
      ]).then(([notifications, state]) => ({ notifications, state }));
    },
    saveNotifications({ changes, signal }) {
      return request('/api/settings/notifications', { method: 'PATCH', body: changes, signal });
    },
  });
}

export const silentSpacesApi = createSilentSpacesApi();
