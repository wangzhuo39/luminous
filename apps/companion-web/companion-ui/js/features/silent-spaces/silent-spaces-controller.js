import {
  adaptCompanionSettings, adaptForgottenMemory, adaptMemoryResponse, adaptOutboxMutation, adaptOutboxResponse,
  adaptPrivacyResponse, adaptSavedNotifications, adaptUpdatedMemory,
} from '../../adapters/silent-spaces-adapter.js';
import { toAppError } from '../../shared/errors.js';
import { renderCompanionSettings, renderMemory, renderOutbox, renderPrivacy } from './silent-spaces-view.js';

function initialState() {
  const privacy = { enabled: true, dailyLimit: 3, quietStart: '', quietEnd: '', allowedKinds: [], dndUntil: '' };
  const companion = {
    baseUrl: '', model: '', temperature: 0.7, maxTokens: 768,
    apiKeyConfigured: false, configured: false, instructions: '', customized: false, updatedAt: '',
  };
  return {
    outbox: { status: 'idle', items: [], actions: {} },
    memory: { status: 'idle', query: '', items: [], editKey: '', editDraft: '', forgetKey: '', actionKey: '', actionStatus: 'idle' },
    privacy: {
      status: 'idle', value: privacy, draft: { ...privacy }, dirty: false, loaded: false,
      companion: { status: 'idle', value: companion, draft: { ...companion, apiKey: '' }, dirty: false },
    },
  };
}

export function initSilentSpaces(dom, { dataSource, onStateChange, announce = () => {} }) {
  let state = initialState();
  const controllers = { outbox: null, memory: null, privacy: null };
  const update = (space, patch) => {
    state = { ...state, [space]: { ...state[space], ...patch } };
    onStateChange();
  };
  const run = async (space, status, task, commit) => {
    controllers[space]?.abort();
    const controller = new AbortController(); controllers[space] = controller;
    update(space, { status });
    try { commit(await task(controller.signal)); }
    catch (error) { if (toAppError(error).kind !== 'cancelled') update(space, { status: 'error' }); }
  };

  const loadOutbox = () => run('outbox', 'loading',
    (signal) => dataSource.loadOutbox({ limit: 20, signal }),
    (raw) => { const items = adaptOutboxResponse(raw); update('outbox', { items, status: items.length ? 'ready' : 'empty' }); });
  const searchMemory = (query = state.memory.query) => {
    const safeQuery = query.trim();
    if (!safeQuery) { update('memory', { query: '', items: [], status: 'idle' }); return; }
    update('memory', { query: safeQuery, editKey: '', forgetKey: '' });
    run('memory', 'loading', (signal) => dataSource.searchMemory({ query: safeQuery, limit: 8, signal }),
      (raw) => { const items = adaptMemoryResponse(raw); update('memory', { items, status: items.length ? 'ready' : 'empty' }); });
  };
  const loadPrivacy = () => run('privacy', 'loading',
    (signal) => dataSource.loadPrivacy({ signal }),
    (raw) => {
      const value = adaptPrivacyResponse(raw);
      const companion = adaptCompanionSettings(raw.companion);
      update('privacy', {
        value, draft: { ...value }, dirty: false, loaded: true, status: 'ready',
        companion: {
          status: raw.companionUnavailable ? 'load-error' : 'ready',
          value: companion, draft: { ...companion, apiKey: '' }, dirty: false,
        },
      });
    });

  const activate = (space) => {
    if (space === 'outbox' && state.outbox.status === 'idle') return loadOutbox();
    if (space === 'privacy' && state.privacy.status === 'idle') return loadPrivacy();
    return Promise.resolve();
  };

  dom.portals.outbox?.addEventListener('click', () => activate('outbox'));
  dom.portals.privacy?.addEventListener('click', () => activate('privacy'));
  dom.outbox.retry?.addEventListener('click', loadOutbox);
  dom.memory.retry?.addEventListener('click', () => searchMemory());
  dom.privacy.retry?.addEventListener('click', loadPrivacy);
  dom.memory.form?.addEventListener('submit', (event) => { event.preventDefault(); searchMemory(dom.memory.input.value); });

  dom.outbox.list?.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-action]');
    const key = button?.closest('[data-key]')?.dataset.key;
    if (!button || !key) return;
    const current = state.outbox.actions[key] ?? { status: 'idle', read: false };
    update('outbox', { actions: { ...state.outbox.actions, [key]: { ...current, status: 'pending' } } });
    try {
      if (button.dataset.action === 'outbox-read') {
        adaptOutboxMutation(await dataSource.markOutboxRead({ key }));
        update('outbox', { actions: { ...state.outbox.actions, [key]: { status: 'saved', read: true, message: '已轻轻收下。' } } });
      } else {
        const status = button.dataset.action === 'outbox-helpful' ? 'helpful' : 'not_needed';
        adaptOutboxMutation(await dataSource.sendOutboxFeedback({ key, status }));
        update('outbox', { actions: { ...state.outbox.actions, [key]: { ...current, status: 'saved', message: '我会记得。' } } });
      }
    } catch { update('outbox', { actions: { ...state.outbox.actions, [key]: { ...current, status: 'error' } } }); }
  });

  dom.memory.list?.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-action]'); const item = button?.closest('[data-key]');
    if (!button || !item) return; const key = item.dataset.key; const current = state.memory.items.find((entry) => entry.key === key);
    if (!current) return;
    if (button.dataset.action === 'memory-edit') update('memory', { editKey: key, editDraft: current.content, forgetKey: '', actionStatus: 'idle' });
    if (button.dataset.action === 'memory-edit-cancel') update('memory', { editKey: '', actionStatus: 'idle' });
    if (button.dataset.action === 'memory-forget') update('memory', { forgetKey: key, editKey: '', actionStatus: 'idle' });
    if (button.dataset.action === 'memory-forget-cancel') update('memory', { forgetKey: '', actionStatus: 'idle' });
    if (button.dataset.action === 'memory-forget-execute') {
      update('memory', { actionKey: key, actionStatus: 'pending' });
      try {
        adaptForgottenMemory(await dataSource.forgetMemory({ key }));
        const items = state.memory.items.filter((entry) => entry.key !== key);
        update('memory', { items, forgetKey: '', actionKey: '', actionStatus: 'idle', status: items.length ? 'ready' : 'empty' }); announce('这段记忆已被忘却。');
      } catch { update('memory', { actionKey: key, actionStatus: 'error' }); }
    }
  });
  dom.memory.list?.addEventListener('submit', async (event) => {
    if (event.target.dataset.action !== 'memory-edit-form') return; event.preventDefault();
    const key = event.target.closest('[data-key]')?.dataset.key; const text = new FormData(event.target).get('text')?.toString().trim();
    if (!key || !text) return;
    update('memory', { actionKey: key, actionStatus: 'pending', editDraft: text });
    try {
      const updated = adaptUpdatedMemory(await dataSource.updateMemory({ key, text }));
      update('memory', { items: state.memory.items.map((item) => item.key === key ? updated : item), editKey: '', actionKey: '', actionStatus: 'idle' }); announce('记忆修订已保存。');
    } catch { update('memory', { actionKey: key, actionStatus: 'error' }); }
  });

  const privacyChanged = () => {
    const draft = { ...state.privacy.draft, enabled: dom.privacy.enabled.checked, dailyLimit: Number(dom.privacy.limit.value), quietStart: dom.privacy.quietStart.value, quietEnd: dom.privacy.quietEnd.value };
    update('privacy', { draft, dirty: JSON.stringify(draft) !== JSON.stringify(state.privacy.value), status: 'ready' });
  };
  dom.privacy.form?.addEventListener('input', privacyChanged);
  dom.privacy.form?.addEventListener('submit', async (event) => {
    event.preventDefault(); if (!state.privacy.dirty) return;
    update('privacy', { status: 'saving' });
    const changes = { enabled: state.privacy.draft.enabled, daily_limit: state.privacy.draft.dailyLimit, quiet_start: state.privacy.draft.quietStart, quiet_end: state.privacy.draft.quietEnd, allowed_kinds: state.privacy.draft.allowedKinds };
    try {
      const value = adaptSavedNotifications(await dataSource.saveNotifications({ changes }), state.privacy.value);
      update('privacy', { value, draft: { ...value }, dirty: false, status: 'saved' }); announce('通知边界已保存。');
    } catch { update('privacy', { status: 'error' }); }
  });

  const companionChanged = () => {
    const draft = {
      ...state.privacy.companion.draft,
      baseUrl: dom.privacy.companionBaseUrl.value.trim(),
      model: dom.privacy.companionModel.value.trim(),
      temperature: Number(dom.privacy.companionTemperature.value),
      maxTokens: Number(dom.privacy.companionMaxTokens.value),
      apiKey: dom.privacy.companionApiKey.value.trim(),
      instructions: dom.privacy.companionInstructions.value,
    };
    const comparable = ({ apiKey, ...value }) => value;
    const dirty = Boolean(draft.apiKey)
      || JSON.stringify(comparable(draft)) !== JSON.stringify(state.privacy.companion.value);
    update('privacy', {
      companion: { ...state.privacy.companion, draft, dirty, status: 'ready' },
    });
  };
  dom.privacy.companionForm?.addEventListener('input', companionChanged);
  dom.privacy.companionForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const current = state.privacy.companion;
    if (!current.dirty) return;
    update('privacy', { companion: { ...current, status: 'saving' } });
    const changes = {
      base_url: current.draft.baseUrl,
      model: current.draft.model,
      temperature: current.draft.temperature,
      max_tokens: current.draft.maxTokens,
      companion_prompt: current.draft.instructions,
    };
    if (current.draft.apiKey) changes.api_key = current.draft.apiKey;
    try {
      const value = adaptCompanionSettings(await dataSource.saveCompanionSettings({ changes }));
      update('privacy', {
        companion: { status: 'saved', value, draft: { ...value, apiKey: '' }, dirty: false },
      });
      announce('连接与伴侣设定已保存。');
    } catch {
      update('privacy', { companion: { ...state.privacy.companion, status: 'error' } });
    }
  });

  return Object.freeze({
    activate,
    render() {
      renderOutbox(dom.outbox, state.outbox);
      renderMemory(dom.memory, state.memory);
      renderPrivacy(dom.privacy, state.privacy);
      renderCompanionSettings(dom.privacy, state.privacy);
    },
    summary() { return { memoryCount: state.memory.items.length, outboxUnread: state.outbox.items.some((item) => !['read', 'replied'].includes(item.status)), dnd: Boolean(state.privacy.value.dndUntil) }; },
    destroy() { Object.values(controllers).forEach((controller) => controller?.abort()); },
  });
}
