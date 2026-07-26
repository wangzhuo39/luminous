/** Local-only fixtures for the Luminous S1 static prototype. */

export const sceneFixture = {
  presence_caption: '静静地陪伴着你。',
  visual_tone: 'calm',
};

export const conversationFixture = {
  history: [
    { id: 'msg-user-1', author: 'user', content: '昨天的雨下得很大...' },
    { id: 'msg-asst-1', author: 'assistant', content: '但今天阳光很好，不是吗？' },
  ],
  draft_text: '',
  local_response: {
    id_prefix: 'local-reply',
    content: '我在这里。无论发生什么，都可以和我说。',
  },
  scene_after_local_send: {
    presence_caption: '正专注地倾听你。',
    visual_tone: 'warm',
  },
};

export const todayFixture = {
  date_iso: '2026-07-25',
  summary_items: [
    { id: 'item-1', text: '上午有一次重要的会议提醒。' },
    { id: 'item-2', text: '下午三点，记得留一点时间休息。' },
  ],
};

export const outboxFixture = {
  arrivals: [
    { id: 'arr-1', title: '关于昨晚的梦', snippet: '我想，或许可以和你聊聊...' },
  ],
  unread_count: 1,
};

export const memoryPrivacyFixture = {
  memory_prompt: '关于记忆，你想了解什么？',
  privacy_caption: '这里的记忆由你决定保留或忘却。',
  boundary_status: '边界已收好',
};
