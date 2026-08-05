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

function boundedNumber(value, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.min(1, Math.max(0, value))
    : fallback;
}

function recentActivityDetail(lastAssistantAt, conversationCount) {
  const timestamp = Date.parse(lastAssistantAt);
  if (Number.isFinite(timestamp)) {
    const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60_000));
    if (minutes < 2) return '刚刚 · 还在听你说';
    if (minutes < 60) return `${minutes} 分钟前 · 仍在这里`;
  }
  return conversationCount > 0 ? `相伴 ${conversationCount} 次对话` : '窗边 · 安静等你';
}

function adaptCompanionStatus(state, tone) {
  const energy = boundedNumber(state?.energy, 0.75);
  const supportNeed = boundedNumber(state?.support_need, 0);
  const heartRate = Math.round(58 + energy * 18 + supportNeed * 8);
  const mode = safeText(state?.conversation_mode, 40).toLowerCase();
  const mood = safeText(state?.mood, 32).toLowerCase();
  const conversationCount = Number.isInteger(state?.conversation_count)
    ? Math.max(0, state.conversation_count)
    : 0;
  const heartLabel = tone === 'concerned'
    ? '心跳微紧'
    : energy < 0.4 ? '心跳舒缓' : energy > 0.82 ? '心跳轻快' : '心跳平稳';
  const activityLabel = {
    supportive: '正专心陪你',
    reflective: '在整理思绪',
    playful: '想和你聊聊',
    repair: '在等你靠近',
  }[mode] || (conversationCount > 0 ? '仍在陪着你' : '正在看雨');
  const moodLabels = {
    warm: ['有些温柔', '心里暖着'],
    gentle: ['有些温柔', '心里暖着'],
    happy: ['心情明亮', '带着一点笑意'],
    joyful: ['心情明亮', '带着一点笑意'],
    anxious: ['有些牵挂', '正在留意你的感受'],
    concerned: ['有些牵挂', '正在留意你的感受'],
    tired: ['稍微疲倦', '想慢一点陪你'],
    quiet: ['有点安静', '心绪轻缓'],
  };
  const [moodLabel, moodDetail] = moodLabels[mood]
    || (tone === 'concerned' ? ['有些担心', '想先陪你稳下来'] : ['有点安静', '心情平静']);
  return {
    heartLabel,
    heartDetail: `${heartRate} 次/分`,
    activityLabel,
    activityDetail: recentActivityDetail(state?.last_assistant_at, conversationCount),
    moodLabel,
    moodDetail,
  };
}

function adaptScene(state, captionCandidate = '') {
  const tone = mapSceneTone(state);
  return {
    caption: safeText(captionCandidate, CAPTION_LIMIT) || defaultCaption(tone),
    tone,
    status: adaptCompanionStatus(state, tone),
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
  const raw = await requestJson('/api/state?include=history', {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? 15_000,
    dependencies: options.dependencies,
  });
  return {
    scene: adaptStateResponse(raw),
    history: adaptChatHistoryResponse(raw.history ?? { items: [] }),
  };
}

export function adaptChatHistoryResponse(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new AppError('server');
  }
  const items = Array.isArray(raw.items) ? raw.items : [];
  return items.flatMap((item) => {
    if (!item || (item.role !== 'user' && item.role !== 'assistant')) return [];
    const text = safeText(item.content, MESSAGE_TEXT_LIMIT);
    if (!text) return [];
    const id = nextMessageId(item.message_id);
    return [{ id, role: item.role, text }];
  }).slice(-HISTORY_LIMIT);
}

export async function loadChatHistory(options = {}) {
  const raw = await requestJson('/api/chat/history?limit=10', {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? 15_000,
    dependencies: options.dependencies,
  });
  return adaptChatHistoryResponse(raw);
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
