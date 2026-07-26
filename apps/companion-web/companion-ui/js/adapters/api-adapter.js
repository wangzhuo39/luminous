import { requestJson } from '../services/api-client.js';
import { AppError } from '../shared/errors.js';

const HISTORY_LIMIT = 10;
const MESSAGE_TEXT_LIMIT = 8_000;
const CAPTION_LIMIT = 120;
let fallbackMessageCounter = 0;

function safeText(value, limit) {
  if (typeof value !== 'string') {
    return '';
  }
  return value.replace(/\s+/g, ' ').trim().slice(0, limit);
}

function mapSceneTone(state) {
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    return 'unknown';
  }

  const risk = safeText(state.risk_level, 32).toLowerCase();
  const mood = safeText(state.mood, 32).toLowerCase();
  const supportNeed = typeof state.support_need === 'number' ? state.support_need : 0;
  const energy = typeof state.energy === 'number' ? state.energy : 1;

  if (['high', 'critical', 'severe'].includes(risk) || supportNeed >= 0.65) {
    return 'concerned';
  }
  if (['anxious', 'distressed', 'overwhelmed', 'concerned'].includes(mood)) {
    return 'concerned';
  }
  if (['warm', 'gentle', 'bright', 'happy', 'joyful'].includes(mood)) {
    return 'warm';
  }
  if (energy <= 0.3 || ['quiet', 'low', 'sad', 'tired', 'withdrawn'].includes(mood)) {
    return 'quiet';
  }
  if (['steady', 'calm', 'neutral'].includes(mood)) {
    return 'calm';
  }
  return 'unknown';
}

function defaultCaption(tone) {
  return {
    calm: '我在这里。',
    warm: '我在，光线也暖了一些。',
    quiet: '我在这里，陪你慢一点。',
    concerned: '我在，先和你一起稳下来。',
    unknown: '我在这里。',
  }[tone];
}

function adaptScene(state, captionCandidate = '') {
  const tone = mapSceneTone(state);
  return {
    caption: safeText(captionCandidate, CAPTION_LIMIT) || defaultCaption(tone),
    tone,
  };
}

function nextMessageId(candidate) {
  const safeCandidate = safeText(candidate, 80);
  if (safeCandidate) {
    return safeCandidate;
  }
  fallbackMessageCounter += 1;
  return `api-assistant-${fallbackMessageCounter}`;
}

export function adaptStateResponse(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new AppError('server');
  }
  const state = raw.state;
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    throw new AppError('server');
  }
  return adaptScene(state);
}

export function adaptChatResponse(raw, options = {}) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new AppError('server');
  }
  const reply = safeText(raw.reply, MESSAGE_TEXT_LIMIT);
  if (!reply) {
    throw new AppError('server');
  }

  return {
    assistantMessage: {
      id: nextMessageId(options.messageId),
      role: 'assistant',
      text: reply,
    },
    scene: adaptScene(raw.state, raw.presence?.caption),
  };
}

export function sanitizeChatHistory(history) {
  const source = Array.isArray(history) ? history : [];
  return source.flatMap((message) => {
    if (!message || (message.role !== 'user' && message.role !== 'assistant')) {
      return [];
    }
    const content = safeText(message.content, MESSAGE_TEXT_LIMIT);
    return content ? [{ role: message.role, content }] : [];
  }).slice(-HISTORY_LIMIT);
}

export async function loadCompanionState(options = {}) {
  const raw = await requestJson('/api/state', {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? 15_000,
    dependencies: options.dependencies,
  });
  return adaptStateResponse(raw);
}

export async function sendChatMessage(message, history, options = {}) {
  const safeMessage = safeText(message, MESSAGE_TEXT_LIMIT);
  if (!safeMessage) {
    throw new AppError('validation');
  }

  const raw = await requestJson('/api/chat', {
    method: 'POST',
    body: {
      message: safeMessage,
      history: sanitizeChatHistory(history),
    },
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? 60_000,
    dependencies: options.dependencies,
  });
  return adaptChatResponse(raw, options);
}
