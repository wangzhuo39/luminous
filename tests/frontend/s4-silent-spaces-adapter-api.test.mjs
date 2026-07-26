import test from 'node:test';
import assert from 'node:assert/strict';

import {
  adaptMemoryResponse, adaptOutboxResponse, adaptPrivacyResponse, adaptSavedNotifications,
} from '../../apps/companion-web/companion-ui/js/adapters/silent-spaces-adapter.js';
import { createSilentSpacesApi } from '../../apps/companion-web/companion-ui/js/services/silent-spaces-api.js';

test('outbox adapter exposes only the user-safe letter model', () => {
  assert.deepEqual(adaptOutboxResponse({ items: [{
    message_id: 'out-1', draft_text: '  晨光抵达。 ', status: 'delivered', signal_type: 'checkin',
    created_at: '2026-07-26T07:00:00Z', trace_id: 'secret', score: 0.99,
    reason: 'internal', anchor_memory_ids: ['private'], payload: { prompt: 'secret' },
  }] }), [{
    key: 'out-1', body: '晨光抵达。', status: 'delivered', kind: 'checkin',
    occurredAt: '2026-07-26T07:00:00Z',
  }]);
});

test('memory adapter drops evidence, scores and forgotten records', () => {
  const result = adaptMemoryResponse({ hits: [
    { memory_id: 'mem-1', text: '用户喜欢雨后的光。', kind: 'preference', status: 'active', observed_at: '2026-07-26T07:00:00Z', evidence_quote: 'private', score: 0.9, confidence: 0.8, metadata: { secret: true } },
    { memory_id: 'mem-2', text: '不应显示', kind: 'fact', status: 'forgotten' },
  ] });
  assert.deepEqual(result, [{ key: 'mem-1', content: '用户喜欢雨后的光。', kind: 'preference', occurredAt: '2026-07-26T07:00:00Z' }]);
});

test('privacy adapter clamps the visible daily limit and keeps DND read-only', () => {
  assert.deepEqual(adaptPrivacyResponse({
    notifications: { enabled: false, daily_limit: 18, quiet_start: '22:00', quiet_end: '08:00', allowed_kinds: ['checkin', 'trace', 'reminder'] },
    state: { state: { dnd_until: '2026-07-26T14:00:00Z', relationship: { trust: 0.9 } } },
  }), {
    enabled: false, dailyLimit: 6, quietStart: '22:00', quietEnd: '08:00',
    allowedKinds: ['checkin', 'reminder'], dndUntil: '2026-07-26T14:00:00Z',
  });
});

test('saved notification response preserves the read-only DND value', () => {
  assert.equal(adaptSavedNotifications({ enabled: true, daily_limit: 2, quiet_start: '', quiet_end: '', allowed_kinds: [] }, { dndUntil: '2026-07-26T14:00:00Z' }).dndUntil, '2026-07-26T14:00:00Z');
});

test('silent-spaces API emits exact safe routes and mutation bodies', async () => {
  const calls = [];
  const api = createSilentSpacesApi({ request: async (path, options = {}) => { calls.push({ path, options }); return {}; } });
  await api.loadOutbox({ status: 'delivered', limit: 20 });
  await api.markOutboxRead({ key: 'out-1' });
  await api.sendOutboxFeedback({ key: 'out-1', status: 'not_needed' });
  await api.searchMemory({ query: '雨 后', limit: 8 });
  await api.updateMemory({ key: 'mem-1', text: ' 修订后的记忆 ' });
  await api.forgetMemory({ key: 'mem-1' });
  await api.saveNotifications({ changes: { enabled: false, daily_limit: 1 } });
  assert.equal(calls[0].path, '/api/outbox?status=delivered&limit=20');
  assert.deepEqual(calls[1].options.body, { message_id: 'out-1', receipt_type: 'read' });
  assert.deepEqual(calls[2].options.body, { message_id: 'out-1', status: 'not_needed' });
  assert.equal(calls[3].path, '/api/memory?q=%E9%9B%A8+%E5%90%8E&limit=8');
  assert.deepEqual(calls[4].options.body, { memory_id: 'mem-1', updates: { text: '修订后的记忆' } });
  assert.deepEqual(calls[5].options.body, { memory_id: 'mem-1', hard_delete: false });
  assert.equal(calls[6].options.method, 'PATCH');
});

test('invalid feedback status and empty memory writes fail before request', async () => {
  let calls = 0;
  const api = createSilentSpacesApi({ request: async () => { calls += 1; return {}; } });
  assert.throws(() => api.sendOutboxFeedback({ key: 'out-1', status: 'rating-5' }));
  assert.throws(() => api.updateMemory({ key: 'mem-1', text: '   ' }));
  assert.throws(() => api.searchMemory({ query: '' }));
  assert.equal(calls, 0);
});
