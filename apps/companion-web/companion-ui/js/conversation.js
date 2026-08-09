import {
  beginChatSubmission,
  completeChatSubmission,
  failChatSubmission,
  getState,
  submitLocalConversation,
  updateDraft,
} from './app-state.js';

function resizeInput(input) {
  if (!input) return;
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 144)}px`;
}

function clearSubmittedInput(input) {
  if (!input) return;
  input.value = '';
  resizeInput(input);
}

function replyAnnouncement(text) {
  const normalized = typeof text === 'string' ? text.replace(/\s+/g, ' ').trim() : '';
  return normalized.length > 240 ? `${normalized.slice(0, 237)}…` : normalized;
}

export function initConversation(dom, {
  mode,
  sendChat,
  announce,
  onStateChange,
  onDraftInput = () => {},
  onDraftSent = () => {},
  onReply = () => {},
  onSendingChange = () => {},
}) {
  let isComposing = false;
  let activeController = null;

  function renderAndResize() {
    onStateChange();
    resizeInput(dom.chatInput);
  }

  async function submit(message = dom.chatInput?.value ?? '') {
    if (mode === 'fixture') {
      if (submitLocalConversation(message)) {
        onDraftSent();
        renderAndResize();
        clearSubmittedInput(dom.chatInput);
        const messages = getState().viewModels?.conversation?.messages ?? [];
        announce(replyAnnouncement(messages.at(-1)?.text));
      }
      return;
    }

    const payload = beginChatSubmission(message);
    if (!payload) return;

    const controller = new AbortController();
    activeController = controller;
    renderAndResize();
    onSendingChange(true);
    announce('我听见了，正在回应。');

    try {
      const result = await sendChat(payload.message, payload.history, {
        messageId: payload.assistantMessageId,
        signal: controller.signal,
      });
      if (controller !== activeController) return;
      if (completeChatSubmission(payload, result)) {
        onDraftSent();
        renderAndResize();
        clearSubmittedInput(dom.chatInput);
        dom.dialogueStream?.lastElementChild?.scrollIntoView({ block: 'nearest' });
        announce(replyAnnouncement(result.assistantMessage.text));
        onReply(result.assistantMessage);
        dom.chatInput?.focus({ preventScroll: true });
      }
    } catch (error) {
      if (controller !== activeController) return;
      if (failChatSubmission(error)) {
        renderAndResize();
        const safeError = getState().conversation.chatError;
        if (safeError) announce(safeError.message);
      }
    } finally {
      if (controller === activeController) activeController = null;
      onSendingChange(false);
    }
  }

  function handleInput(event) {
    updateDraft(event.currentTarget.value);
    onDraftInput(event.currentTarget.value);
    renderAndResize();
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!isComposing) submit();
  }

  function handleKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !isComposing) {
      event.preventDefault();
      submit();
    }
  }

  function handleCompositionStart() {
    isComposing = true;
  }

  function handleCompositionEnd() {
    isComposing = false;
  }

  dom.chatInput?.addEventListener('input', handleInput);
  dom.chatInput?.addEventListener('keydown', handleKeydown);
  dom.chatInput?.addEventListener('compositionstart', handleCompositionStart);
  dom.chatInput?.addEventListener('compositionend', handleCompositionEnd);
  dom.inputForm?.addEventListener('submit', handleSubmit);
  resizeInput(dom.chatInput);

  return {
    submitText(text) {
      return submit(text);
    },
    destroy() {
      activeController?.abort();
      activeController = null;
      dom.chatInput?.removeEventListener('input', handleInput);
      dom.chatInput?.removeEventListener('keydown', handleKeydown);
      dom.chatInput?.removeEventListener('compositionstart', handleCompositionStart);
      dom.chatInput?.removeEventListener('compositionend', handleCompositionEnd);
      dom.inputForm?.removeEventListener('submit', handleSubmit);
    },
  };
}
