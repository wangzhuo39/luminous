import { AppError } from '../shared/errors.js';
import { requestJson } from './api-client.js';

const EMPTY_COMPANION_SETTINGS = Object.freeze({
  llm: Object.freeze({
    base_url: '', model: '', temperature: 0.7, max_tokens: 768,
    api_key_configured: false, configured: false,
  }),
  companion: Object.freeze({ instructions: '', customized: false }),
  tts: Object.freeze({
    provider: 'openai-compatible', base_url: '', model: '',
    api_key_configured: false, configured: false,
  }),
  voice: Object.freeze({ voice_enabled: true, auto_play: false, voice_id: 'alloy', speaking_rate: 1, output_volume: 1 }),
  providers: Object.freeze({
    stt: Object.freeze({ provider: 'openai-compatible', configured: false }),
    tts: Object.freeze({ provider: 'openai-compatible', configured: false }),
  }),
  updated_at: '',
});

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
        request('/api/settings/companion', { signal })
          .then((companion) => ({ companion, companionUnavailable: false }))
          .catch(() => ({ companion: EMPTY_COMPANION_SETTINGS, companionUnavailable: true })),
      ]).then(([notifications, state, result]) => ({ notifications, state, ...result }));
    },
    saveNotifications({ changes, signal }) {
      return request('/api/settings/notifications', { method: 'PATCH', body: changes, signal });
    },
    saveCompanionSettings({ changes, signal }) {
      return request('/api/settings/companion', { method: 'PATCH', body: changes, signal });
    },
  });
}

export const silentSpacesApi = createSilentSpacesApi();
