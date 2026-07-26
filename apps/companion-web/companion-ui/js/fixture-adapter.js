import * as Fixtures from './fixtures.js';

const VISUAL_TONES = new Set(['calm', 'warm', 'quiet', 'concerned']);

function safeText(value, fallback = '') {
  return typeof value === 'string' ? value : fallback;
}

function safeId(value, fallback) {
  const id = safeText(value).trim();
  return id || fallback;
}

function adaptScene(fixture) {
  const tone = safeText(fixture?.visual_tone);
  return {
    caption: safeText(fixture?.presence_caption, '陪伴者静静地在场。'),
    tone: VISUAL_TONES.has(tone) ? tone : 'unknown',
  };
}

function adaptConversation(fixture) {
  const history = Array.isArray(fixture?.history) ? fixture.history : [];
  const messages = history.flatMap((message, index) => {
    if (!message || (message.author !== 'user' && message.author !== 'assistant')) {
      return [];
    }
    return [{
      id: safeId(message.id, `message-${index + 1}`),
      role: message.author,
      text: safeText(message.content),
    }];
  });
  const nextTone = safeText(fixture?.scene_after_local_send?.visual_tone);
  return {
    messages,
    localReply: {
      idPrefix: safeId(fixture?.local_response?.id_prefix, 'local-reply'),
      text: safeText(fixture?.local_response?.content, '我在这里。'),
    },
    sceneAfterLocalSend: {
      caption: safeText(
        fixture?.scene_after_local_send?.presence_caption,
        '陪伴者正专注地倾听。',
      ),
      tone: VISUAL_TONES.has(nextTone) ? nextTone : 'calm',
    },
  };
}

function adaptToday(fixture) {
  let date = '';
  const rawDate = safeText(fixture?.date_iso);
  if (/^\d{4}-\d{2}-\d{2}$/.test(rawDate)) {
    const parsed = new Date(`${rawDate}T00:00:00`);
    if (!Number.isNaN(parsed.getTime())) {
      date = parsed.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    }
  }

  const sourceItems = Array.isArray(fixture?.summary_items) ? fixture.summary_items : [];
  const summaryItems = sourceItems.map((item, index) => ({
    id: safeId(item?.id, `today-item-${index + 1}`),
    text: safeText(item?.text),
  }));
  return { date, summaryItems };
}

function adaptOutbox(fixture) {
  const sourceItems = Array.isArray(fixture?.arrivals) ? fixture.arrivals : [];
  const arrivals = sourceItems.map((item, index) => ({
    id: safeId(item?.id, `arrival-${index + 1}`),
    title: safeText(item?.title),
    snippet: safeText(item?.snippet),
  }));
  const rawCount = fixture?.unread_count;
  const unreadCount = Number.isInteger(rawCount) && rawCount >= 0 ? rawCount : 0;
  return { arrivals, unreadCount };
}

function adaptMemoryPrivacy(fixture) {
  return {
    memoryPrompt: safeText(fixture?.memory_prompt),
    privacyCaption: safeText(fixture?.privacy_caption),
    boundaryStatus: safeText(fixture?.boundary_status),
  };
}

export function loadInitialViewModels() {
  return {
    scene: adaptScene(Fixtures.sceneFixture),
    conversation: adaptConversation(Fixtures.conversationFixture),
    today: adaptToday(Fixtures.todayFixture),
    outbox: adaptOutbox(Fixtures.outboxFixture),
    memoryPrivacy: adaptMemoryPrivacy(Fixtures.memoryPrivacyFixture),
  };
}
