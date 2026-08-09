import { AppError } from '../shared/errors.js';

const OUTBOX_STATUSES = new Set(['drafted', 'queued', 'sent', 'delivered', 'read', 'replied', 'suppressed', 'failed']);
const MEMORY_KINDS = new Set(['fact', 'preference', 'relationship', 'event', 'boundary', 'recurring_topic', 'open_loop', 'identity', 'emotion', 'state']);
const ALLOWED_KINDS = new Set(['checkin', 'open_loop_followup', 'reminder', 'anniversary', 'routine', 'repair']);

function object(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new AppError('server');
  return value;
}

function text(value, limit = 240) {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim().slice(0, limit) : '';
}

function key(value) {
  const normalized = text(value, 100);
  if (!normalized) throw new AppError('server');
  return normalized;
}

function iso(value) {
  const normalized = text(value, 40);
  return normalized && !Number.isNaN(Date.parse(normalized)) ? normalized : '';
}

export function adaptOutboxResponse(raw) {
  const source = object(raw);
  const items = Array.isArray(source.items) ? source.items : [];
  return items.flatMap((candidate) => {
    try {
      const item = object(candidate);
      const body = text(item.draft_text, 1200);
      if (!body) return [];
      const status = text(item.status, 32);
      return [{
        key: key(item.message_id),
        body,
        status: OUTBOX_STATUSES.has(status) ? status : 'drafted',
        kind: text(item.signal_type, 48),
        occurredAt: iso(item.sent_at) || iso(item.created_at) || iso(item.replied_at),
      }];
    } catch {
      return [];
    }
  }).reverse();
}

export function adaptOutboxMutation(raw) {
  const response = object(raw);
  if (response.ok === false) throw new AppError('server');
  return true;
}

export function adaptMemoryResponse(raw) {
  const source = object(raw);
  const hits = Array.isArray(source.hits) ? source.hits : [];
  return hits.flatMap((candidate) => {
    try {
      const item = object(candidate);
      const content = text(item.text, 1200);
      if (!content || text(item.status, 24) === 'forgotten') return [];
      const kind = text(item.kind, 32);
      return [{
        key: key(item.memory_id),
        content,
        kind: MEMORY_KINDS.has(kind) ? kind : 'fact',
        occurredAt: iso(item.observed_at) || iso(item.created_at),
      }];
    } catch {
      return [];
    }
  });
}

export function adaptUpdatedMemory(raw) {
  const source = object(raw);
  if (source.ok !== true) throw new AppError(source.reason === 'not_found' ? 'not-found' : 'server');
  return adaptMemoryResponse({ hits: [source.memory] })[0] ?? (() => { throw new AppError('server'); })();
}

export function adaptForgottenMemory(raw) {
  const source = object(raw);
  if (source.ok !== true) throw new AppError('server');
  return true;
}

export function adaptPrivacyResponse(raw) {
  const source = object(raw);
  const notifications = object(source.notifications);
  const stateWrapper = object(source.state);
  const state = object(stateWrapper.state);
  const dailyLimit = Number.parseInt(notifications.daily_limit, 10);
  return {
    enabled: notifications.enabled !== false,
    dailyLimit: Number.isInteger(dailyLimit) ? Math.max(0, Math.min(6, dailyLimit)) : 3,
    quietStart: /^\d{2}:\d{2}$/.test(notifications.quiet_start) ? notifications.quiet_start : '',
    quietEnd: /^\d{2}:\d{2}$/.test(notifications.quiet_end) ? notifications.quiet_end : '',
    allowedKinds: Array.isArray(notifications.allowed_kinds)
      ? notifications.allowed_kinds.filter((kind) => ALLOWED_KINDS.has(kind))
      : [],
    dndUntil: iso(state.dnd_until),
  };
}

export function adaptSavedNotifications(raw, previous = {}) {
  const source = object(raw);
  return adaptPrivacyResponse({ notifications: source, state: { state: { dnd_until: previous.dndUntil ?? '' } } });
}

export function adaptCompanionSettings(raw) {
  const source = object(raw);
  const llm = object(source.llm);
  const companion = object(source.companion);
  const tts = source.tts && typeof source.tts === 'object' ? source.tts : {};
  const voice = source.voice && typeof source.voice === 'object' ? source.voice : {};
  const providers = source.providers && typeof source.providers === 'object' ? source.providers : {};
  const temperature = Number(llm.temperature);
  const maxTokens = Number.parseInt(llm.max_tokens, 10);
  return {
    baseUrl: typeof llm.base_url === 'string' ? llm.base_url.trim().slice(0, 2048) : '',
    model: text(llm.model, 256),
    temperature: Number.isFinite(temperature) ? Math.max(0, Math.min(2, temperature)) : 0.7,
    maxTokens: Number.isInteger(maxTokens) ? Math.max(1, Math.min(32768, maxTokens)) : 768,
    apiKeyConfigured: llm.api_key_configured === true,
    configured: llm.configured === true,
    instructions: typeof companion.instructions === 'string' ? companion.instructions.slice(0, 12000) : '',
    customized: companion.customized === true,
    ttsBaseUrl: typeof tts.base_url === 'string' ? tts.base_url.trim().slice(0, 2048) : '',
    ttsModel: text(tts.model, 256),
    ttsApiKeyConfigured: tts.api_key_configured === true,
    voiceEnabled: voice.voice_enabled !== false,
    autoPlay: voice.auto_play === true,
    voiceId: text(voice.voice_id, 128) || 'alloy',
    speakingRate: Number.isFinite(Number(voice.speaking_rate))
      ? Math.max(0.5, Math.min(2, Number(voice.speaking_rate))) : 1,
    outputVolume: Number.isFinite(Number(voice.output_volume))
      ? Math.max(0, Math.min(1, Number(voice.output_volume))) : 1,
    sttProvider: text(providers.stt?.provider, 80) || 'openai-compatible',
    sttConfigured: providers.stt?.configured === true,
    ttsProvider: text(tts.provider || providers.tts?.provider, 80) || 'openai-compatible',
    ttsConfigured: tts.configured === true || providers.tts?.configured === true,
    updatedAt: iso(source.updated_at),
  };
}
