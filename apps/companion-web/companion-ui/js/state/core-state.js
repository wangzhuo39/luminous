import {
  appStore,
  createInitialState,
  safeErrorDescriptor,
  safeScene,
} from './app-store.js';

export function initializeState(initialViewModels, options = {}) {
  const runtimeMode = options.runtimeMode === 'api' ? 'api' : 'fixture';
  appStore.state = createInitialState();
  appStore.state.runtimeMode = runtimeMode;
  appStore.state.appStatus = runtimeMode === 'api' ? 'loading' : 'fixture';
  appStore.state.conversation.draft = typeof options.initialDraft === 'string' ? options.initialDraft : '';
  appStore.state.viewModels = initialViewModels;
  appStore.messageCounter = 0;
}

export function beginInitialLoad() {
  if (appStore.state.runtimeMode !== 'api') return false;
  appStore.state.appStatus = 'loading';
  appStore.state.appError = null;
  return true;
}

export function completeInitialLoad(scene) {
  if (appStore.state.runtimeMode !== 'api' || !appStore.state.viewModels) return false;
  const nextScene = safeScene(scene);
  if (!nextScene) return false;
  appStore.state.viewModels.scene = nextScene;
  appStore.state.appStatus = 'ready';
  appStore.state.appError = null;
  return true;
}

export function hydrateConversationHistory(messages) {
  if (!appStore.state.viewModels?.conversation || !Array.isArray(messages)) return false;
  appStore.state.viewModels.conversation.messages = messages.flatMap((item) => {
    if (!item || (item.role !== 'user' && item.role !== 'assistant')) return [];
    const text = typeof item.text === 'string' ? item.text.trim().slice(0, 8_000) : '';
    return text ? [{
      id: typeof item.id === 'string' && item.id.trim() ? item.id.trim() : `history-${appStore.messageCounter++}`,
      role: item.role,
      text,
    }] : [];
  }).slice(-10);
  return true;
}

export function failInitialLoad(error) {
  if (appStore.state.runtimeMode !== 'api') return false;
  const descriptor = safeErrorDescriptor(error);
  appStore.state.appStatus = descriptor.retryable ? 'offline' : 'error';
  appStore.state.appError = descriptor;
  return true;
}

export function updateDraft(newDraft) {
  if (appStore.state.conversation.chatStatus === 'submitting') return false;
  appStore.state.conversation.draft = typeof newDraft === 'string' ? newDraft : '';
  if (appStore.state.conversation.chatStatus === 'error') {
    appStore.state.conversation.chatStatus = 'idle';
    appStore.state.conversation.chatError = null;
  }
  return true;
}

export function beginChatSubmission() {
  const draft = appStore.state.conversation.draft;
  const message = draft.trim();
  const canSend = appStore.state.runtimeMode === 'fixture' || appStore.state.appStatus === 'ready';
  if (!message || !appStore.state.viewModels || !canSend || appStore.state.conversation.chatStatus === 'submitting') {
    return null;
  }

  appStore.messageCounter += 1;
  const submissionId = `submission-${appStore.messageCounter}`;
  const history = (appStore.state.viewModels.conversation.messages ?? []).flatMap((item) => {
    if (!item || (item.role !== 'user' && item.role !== 'assistant') || typeof item.text !== 'string') return [];
    const content = item.text.trim();
    return content ? [{ role: item.role, content }] : [];
  }).slice(-10);

  appStore.state.conversation.pendingDraft = draft;
  appStore.state.conversation.pendingSubmissionId = submissionId;
  appStore.state.conversation.chatStatus = 'submitting';
  appStore.state.conversation.chatError = null;

  return Object.freeze({
    submissionId,
    draft,
    message,
    history,
    userMessageId: `api-user-${appStore.messageCounter}`,
    assistantMessageId: `api-assistant-${appStore.messageCounter}`,
  });
}

export function completeChatSubmission(payload, result) {
  if (
    appStore.state.conversation.chatStatus !== 'submitting'
    || !payload
    || payload.submissionId !== appStore.state.conversation.pendingSubmissionId
    || !appStore.state.viewModels
  ) return false;

  const assistant = result?.assistantMessage;
  const assistantText = typeof assistant?.text === 'string' ? assistant.text.trim() : '';
  if (!assistantText || assistant?.role !== 'assistant') return false;

  const nextMessages = [
    ...(appStore.state.viewModels.conversation.messages ?? []),
    { id: payload.userMessageId, role: 'user', text: payload.message },
    {
      id: typeof assistant.id === 'string' && assistant.id.trim()
        ? assistant.id.trim()
        : payload.assistantMessageId,
      role: 'assistant',
      text: assistantText,
    },
  ];
  appStore.state.viewModels.conversation.messages = nextMessages.slice(-10);

  const nextScene = safeScene(result.scene);
  if (nextScene) appStore.state.viewModels.scene = nextScene;

  appStore.state.conversation.draft = '';
  appStore.state.conversation.pendingDraft = '';
  appStore.state.conversation.pendingSubmissionId = null;
  appStore.state.conversation.chatStatus = 'idle';
  appStore.state.conversation.chatError = null;
  return true;
}

export function submitLocalConversation(userText) {
  if (appStore.state.runtimeMode !== 'fixture' || appStore.state.conversation.chatStatus === 'submitting') {
    return false;
  }
  appStore.state.conversation.draft = typeof userText === 'string' ? userText : '';
  const payload = beginChatSubmission();
  const fixtureConversation = appStore.state.viewModels?.conversation;
  if (!payload || !fixtureConversation?.localReply) {
    return false;
  }
  const completed = completeChatSubmission(payload, {
    assistantMessage: {
      id: `${fixtureConversation.localReply.idPrefix}-${appStore.messageCounter}`,
      role: 'assistant',
      text: fixtureConversation.localReply.text,
    },
    scene: fixtureConversation.sceneAfterLocalSend,
  });
  if (completed) {
    appStore.state.viewModels.conversation.messages = appStore.state.viewModels.conversation.messages.slice(-5);
  }
  return completed;
}

export function failChatSubmission(error) {
  if (appStore.state.conversation.chatStatus !== 'submitting') return false;
  const descriptor = safeErrorDescriptor(error);
  appStore.state.conversation.draft = appStore.state.conversation.pendingDraft;
  appStore.state.conversation.pendingDraft = '';
  appStore.state.conversation.pendingSubmissionId = null;

  if (descriptor.kind === 'cancelled') {
    appStore.state.conversation.chatStatus = 'idle';
    appStore.state.conversation.chatError = null;
    return true;
  }

  appStore.state.conversation.chatStatus = 'error';
  appStore.state.conversation.chatError = descriptor;
  return true;
}
