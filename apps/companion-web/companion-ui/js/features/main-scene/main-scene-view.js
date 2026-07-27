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

export function createMainSceneView({ body, companionFigure, dialogueStream, chatInput }) {
  return {
    renderScene(viewModel) {
      companionFigure?.setAttribute('aria-label', viewModel.caption);
      body.dataset.tone = viewModel.tone;
    },

    renderConversation(viewModel, draft) {
      renderMessages(dialogueStream, viewModel.messages);
      if (chatInput && chatInput.value !== draft) chatInput.value = draft;
    },
  };
}
