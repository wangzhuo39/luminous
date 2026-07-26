export const DRAFT_STORAGE_KEY = 'luminous.unsent-chat-draft.v1';
export const DRAFT_MAX_LENGTH = 8000;
export const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;

function safeRemove(storage) {
  try { storage?.removeItem(DRAFT_STORAGE_KEY); } catch { /* Storage can be unavailable. */ }
}

export function loadRecoveredDraft(storage, now = Date.now()) {
  let raw = null;
  try { raw = storage?.getItem(DRAFT_STORAGE_KEY) ?? null; } catch { return null; }
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    const valid = value?.version === 1
      && typeof value.text === 'string'
      && value.text.length > 0
      && value.text.length <= DRAFT_MAX_LENGTH
      && Number.isFinite(value.savedAt)
      && value.savedAt <= now
      && now - value.savedAt <= DRAFT_TTL_MS;
    if (!valid) {
      safeRemove(storage);
      return null;
    }
    return Object.freeze({ text: value.text, savedAt: value.savedAt });
  } catch {
    safeRemove(storage);
    return null;
  }
}

export function saveRecoverableDraft(storage, text, now = Date.now()) {
  const value = typeof text === 'string' ? text.slice(0, DRAFT_MAX_LENGTH) : '';
  if (!value) {
    safeRemove(storage);
    return false;
  }
  try {
    storage?.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ version: 1, text: value, savedAt: now }));
    return true;
  } catch {
    return false;
  }
}

export function clearRecoverableDraft(storage) {
  safeRemove(storage);
}
