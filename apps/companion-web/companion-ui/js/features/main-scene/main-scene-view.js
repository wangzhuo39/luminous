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
