export function createSilentSpacesFixtureDataSource({ date = '2026-07-26' } = {}) {
  let memories = [
    { memory_id: 'fixture-memory-light', text: '用户喜欢雨停以后安静、偏冷的晨光。', kind: 'preference', status: 'active', observed_at: `${date}T07:20:00+08:00` },
    { memory_id: 'fixture-memory-rest', text: '用户希望在忙碌的下午为自己留一点休息时间。', kind: 'open_loop', status: 'active', observed_at: `${date}T15:00:00+08:00` },
  ];
  const outbox = [
    { message_id: 'fixture-letter-morning', draft_text: '晨光刚落进窗里。今天也按自己的节奏来，不必急着回答。', status: 'delivered', signal_type: 'checkin', created_at: `${date}T07:40:00+08:00` },
  ];
  let preferences = { enabled: true, daily_limit: 3, quiet_start: '22:00', quiet_end: '08:00', allowed_kinds: ['checkin', 'reminder', 'routine'] };
  let companionSettings = {
    llm: { base_url: '', model: '', temperature: 0.7, max_tokens: 768, api_key_configured: false, configured: false },
    companion: { instructions: '', customized: false },
    updated_at: '',
  };
  return Object.freeze({
    async loadOutbox() { return { items: outbox }; },
    async markOutboxRead() { return { ok: true }; },
    async sendOutboxFeedback() { return { ok: true }; },
    async searchMemory({ query }) { return { hits: memories.filter((item) => item.text.includes(query.trim())) }; },
    async updateMemory({ key, text }) {
      memories = memories.map((item) => item.memory_id === key ? { ...item, text } : item);
      return { ok: true, memory: memories.find((item) => item.memory_id === key) };
    },
    async forgetMemory({ key }) { memories = memories.filter((item) => item.memory_id !== key); return { ok: true, memory: null }; },
    async loadPrivacy() { return { notifications: preferences, state: { state: { dnd_until: '' } }, companion: companionSettings }; },
    async saveNotifications({ changes }) { preferences = { ...preferences, ...changes }; return preferences; },
    async saveCompanionSettings({ changes }) {
      companionSettings = {
        llm: {
          ...companionSettings.llm,
          base_url: changes.base_url,
          model: changes.model,
          temperature: changes.temperature,
          max_tokens: changes.max_tokens,
          api_key_configured: companionSettings.llm.api_key_configured || Boolean(changes.api_key),
          configured: Boolean(changes.base_url && changes.model && (companionSettings.llm.api_key_configured || changes.api_key)),
        },
        companion: { instructions: changes.companion_prompt, customized: Boolean(changes.companion_prompt) },
        updated_at: new Date().toISOString(),
      };
      return companionSettings;
    },
  });
}
