function renderMessages(dialogueStream, messages) {
  if (!dialogueStream) return;

  const wasAtBottom = dialogueStream.scrollHeight - dialogueStream.clientHeight
    - dialogueStream.scrollTop <= 24;
  const fragment = document.createDocumentFragment();

  messages.forEach((message) => {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${message.role}-message`;
    const paragraph = document.createElement('p');
    paragraph.textContent = message.text;
    messageElement.appendChild(paragraph);
    messageElement.dataset.messageId = message.id;
    if (message.role === 'assistant') {
      const controls = document.createElement('div');
      controls.className = 'message-voice-controls';
      controls.innerHTML = `
        <button type="button" class="message-voice-button" data-voice-action="play" aria-label="播放语音" title="播放语音"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7Z"/></svg></button>
        <button type="button" class="message-voice-button" data-voice-action="replay" aria-label="重播" title="重播"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"/></svg></button>
        <button type="button" class="message-voice-button" data-voice-action="mute" aria-label="静音" title="静音"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H2v6h4l5 4ZM15 9l6 6M21 9l-6 6"/></svg></button>`;
      messageElement.appendChild(controls);
    }
    fragment.appendChild(messageElement);
  });

  dialogueStream.replaceChildren(fragment);
  if (wasAtBottom) dialogueStream.scrollTop = dialogueStream.scrollHeight;
}

export function createMainSceneView({ body, scene, companionFigure, dialogueStream, chatInput }) {
  const statusNodes = {
    heartLabel: scene?.querySelector('[data-hook="companion-heart-label"]'),
    heartDetail: scene?.querySelector('[data-hook="companion-heart-detail"]'),
    activityLabel: scene?.querySelector('[data-hook="companion-activity-label"]'),
    activityDetail: scene?.querySelector('[data-hook="companion-activity-detail"]'),
    moodLabel: scene?.querySelector('[data-hook="companion-mood-label"]'),
    moodDetail: scene?.querySelector('[data-hook="companion-mood-detail"]'),
  };
  return {
    renderScene(viewModel) {
      companionFigure?.setAttribute('aria-label', viewModel.caption);
      body.dataset.tone = viewModel.tone;
      Object.entries(statusNodes).forEach(([key, node]) => {
        if (node && typeof viewModel.status?.[key] === 'string') {
          node.textContent = viewModel.status[key];
        }
      });
    },

    renderConversation(viewModel, draft) {
      renderMessages(dialogueStream, viewModel.messages);
      if (chatInput && chatInput.value !== draft) chatInput.value = draft;
    },
  };
}
