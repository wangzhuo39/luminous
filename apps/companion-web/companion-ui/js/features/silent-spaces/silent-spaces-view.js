const KIND_LABELS = {
  checkin: '轻轻问候', reminder: '提醒', routine: '日常节律', repair: '关系修复',
  fact: '片段', preference: '偏好', relationship: '关系', event: '经历', boundary: '边界',
  recurring_topic: '常被提起', open_loop: '仍在心上', identity: '关于你', emotion: '感受', state: '近况',
};

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function button(label, action, className = 'silent-button silent-button--ghost') {
  const element = node('button', className, label);
  element.type = 'button';
  element.dataset.action = action;
  return element;
}

function timeLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
}

function setState(statusNode, text, tone = '') {
  statusNode.textContent = text;
  statusNode.dataset.tone = tone;
  statusNode.hidden = !text;
}

export function renderOutbox(dom, state) {
  if (!dom.list || !dom.status) return;
  const copy = {
    idle: '信笺仍安静地合着。', loading: '正在整理抵达的信笺…',
    empty: '此刻没有新信。', error: '信笺暂时没有展开。', ready: '',
  };
  setState(dom.status, copy[state.status] ?? '', state.status === 'error' ? 'error' : '');
  if (dom.retry) dom.retry.hidden = state.status !== 'error';
  const fragment = document.createDocumentFragment();
  state.items.forEach((item) => {
    const li = node('li', 'outbox-item');
    li.dataset.key = item.key;
    const meta = node('div', 'outbox-meta');
    meta.append(node('span', 'outbox-signal', KIND_LABELS[item.kind] ?? '一封来信'));
    const occurred = timeLabel(item.occurredAt);
    if (occurred) meta.append(node('time', 'outbox-time', occurred));
    const body = node('p', 'outbox-text', item.body);
    const actions = node('div', 'outbox-actions');
    const action = state.actions[item.key] ?? { status: 'idle', read: item.status === 'read' || item.status === 'replied' };
    const read = button(action.read ? '已读' : '轻轻收下', 'outbox-read', 'silent-button silent-button--quiet');
    read.disabled = action.status === 'pending' || action.read;
    actions.append(read);
    const feedback = node('div', 'outbox-feedback');
    const helpful = button('对我有帮助', 'outbox-helpful');
    const unneeded = button('现在不需要', 'outbox-unneeded');
    helpful.disabled = action.status === 'pending';
    unneeded.disabled = action.status === 'pending';
    feedback.append(helpful, unneeded);
    actions.append(feedback);
    const status = node('p', 'silent-item-status');
    status.setAttribute('aria-live', 'polite');
    if (action.status === 'pending') status.textContent = '正在送回你的选择…';
    if (action.status === 'saved') status.textContent = action.message || '已安静记下。';
    if (action.status === 'error') {
      status.textContent = '没有送达，你可以再试一次。';
      status.dataset.tone = 'error';
    }
    li.append(meta, body, actions, status);
    fragment.append(li);
  });
  dom.list.replaceChildren(fragment);
}

export function renderMemory(dom, state) {
  if (!dom.list || !dom.status) return;
  const copy = {
    idle: '记忆悬浮于深处，等待你用一个片段唤醒。', loading: '正在让折射慢慢清晰…',
    empty: '没有找到与这段文字相近的记忆。', error: '这次折射没有显现。', ready: '',
  };
  setState(dom.status, copy[state.status] ?? '', state.status === 'error' ? 'error' : '');
  if (dom.retry) dom.retry.hidden = state.status !== 'error';
  if (dom.input && dom.input.value !== state.query) dom.input.value = state.query;
  const fragment = document.createDocumentFragment();
  state.items.forEach((item) => {
    const li = node('li', 'memory-facet');
    li.dataset.key = item.key;
    const meta = node('div', 'memory-meta');
    meta.append(node('span', 'memory-kind', KIND_LABELS[item.kind] ?? '记忆片段'));
    const occurred = timeLabel(item.occurredAt);
    if (occurred) meta.append(node('time', 'memory-time', occurred));
    const display = node('div', 'memory-display');
    display.append(node('p', 'memory-text', item.content));
    const actions = node('div', 'memory-actions');
    actions.append(button('修琢', 'memory-edit'), button('忘却', 'memory-forget'));
    display.append(actions);
    li.append(meta, display);

    if (state.editKey === item.key) {
      const form = node('form', 'memory-edit-form');
      form.dataset.action = 'memory-edit-form';
      const label = node('label', 'silent-label', '把这段记忆修订为');
      const area = node('textarea', 'crystal-textarea');
      area.name = 'text'; area.required = true; area.maxLength = 1200; area.value = state.editDraft;
      label.append(area);
      const row = node('div', 'memory-actions');
      const save = node('button', 'silent-button silent-button--quiet', state.actionStatus === 'pending' ? '正在保存…' : '保存修订');
      save.type = 'submit'; save.disabled = state.actionStatus === 'pending';
      row.append(button('取消', 'memory-edit-cancel'), save);
      form.append(label, row);
      li.append(form);
    }
    if (state.forgetKey === item.key) {
      const confirm = node('div', 'memory-confirm');
      confirm.setAttribute('role', 'group');
      confirm.setAttribute('aria-label', '确认忘却这段记忆');
      confirm.append(node('p', '', '忘却后，这段内容不会再参与平常的陪伴。'));
      const row = node('div', 'memory-actions');
      const execute = button(state.actionStatus === 'pending' ? '正在忘却…' : '确认忘却', 'memory-forget-execute', 'silent-button silent-button--danger');
      execute.disabled = state.actionStatus === 'pending';
      row.append(button('保留', 'memory-forget-cancel'), execute);
      confirm.append(row);
      li.append(confirm);
    }
    if (state.actionKey === item.key && state.actionStatus === 'error') {
      const error = node('p', 'silent-item-status', '没有完成，内容仍被保留。请再试一次。');
      error.dataset.tone = 'error'; error.setAttribute('aria-live', 'polite'); li.append(error);
    }
    fragment.append(li);
  });
  dom.list.replaceChildren(fragment);
}

export function renderPrivacy(dom, state) {
  if (!dom.form || !dom.status) return;
  const ready = state.loaded && (state.status === 'ready' || state.status === 'saving' || state.status === 'saved' || state.status === 'error');
  setState(dom.status, state.status === 'loading' ? '正在确认这层雾帘的位置…'
    : state.status === 'error' ? (state.loaded ? '设置暂时没有保存，原来的选择仍然有效。' : '这层雾帘暂时没有展开。')
      : state.status === 'saved' ? '边界已安静地放回原处。' : '', state.status === 'error' ? 'error' : '');
  if (dom.retry) dom.retry.hidden = state.status !== 'error' || state.loaded;
  dom.form.hidden = !ready;
  if (!ready) return;
  dom.enabled.checked = state.draft.enabled;
  dom.limit.value = String(state.draft.dailyLimit);
  dom.quietStart.value = state.draft.quietStart;
  dom.quietEnd.value = state.draft.quietEnd;
  dom.save.disabled = !state.dirty || state.status === 'saving';
  dom.save.textContent = state.status === 'saving' ? '正在合上雾帘…' : state.dirty ? '保存边界' : '维持现状';
  if (dom.dnd) dom.dnd.textContent = state.value.dndUntil
    ? `当前免打扰至 ${timeLabel(state.value.dndUntil)}。这项状态由陪伴服务维护。`
    : '当前没有额外的免打扰时段。';
}

export function renderCompanionSettings(dom, state) {
  const form = dom.companionForm;
  const status = dom.companionStatus;
  if (!form || !status) return;
  const companion = state.companion;
  const ready = state.loaded && companion.status !== 'idle';
  form.hidden = !ready;
  setState(status, !state.loaded && state.status === 'loading' ? '正在读取连接与伴侣设定…'
    : companion.status === 'saving' ? '正在保存新的连接与设定…'
      : companion.status === 'saved' ? '连接与伴侣设定已保存，将从下一轮对话开始生效。'
        : companion.status === 'load-error' ? '暂时无法读取服务端已有设定；你仍可填写，保存时会再次连接。'
        : companion.status === 'error' ? '设置没有保存，请检查地址、模型和生成参数。'
          : '', companion.status === 'error' || companion.status === 'load-error' ? 'error' : '');
  if (!ready) return;
  const draft = companion.draft;
  dom.companionBaseUrl.value = draft.baseUrl;
  dom.companionModel.value = draft.model;
  dom.companionTemperature.value = String(draft.temperature);
  dom.companionMaxTokens.value = String(draft.maxTokens);
  dom.companionInstructions.value = draft.instructions;
  if (dom.ttsBaseUrl) dom.ttsBaseUrl.value = draft.ttsBaseUrl;
  if (dom.ttsModel) dom.ttsModel.value = draft.ttsModel;
  if (dom.voiceEnabled) dom.voiceEnabled.checked = draft.voiceEnabled;
  if (dom.voiceAutoPlay) dom.voiceAutoPlay.checked = draft.autoPlay;
  if (dom.voiceId) dom.voiceId.value = draft.voiceId;
  if (dom.voiceRate) dom.voiceRate.value = String(draft.speakingRate);
  if (dom.voiceVolume) dom.voiceVolume.value = String(draft.outputVolume);
  if (dom.voiceProviderSummary) dom.voiceProviderSummary.textContent = `语音合成：${draft.ttsConfigured ? '已配置' : '未配置'}`;
  const ttsDraftChanged = Boolean(draft.ttsApiKey)
    || draft.ttsBaseUrl !== companion.value.ttsBaseUrl
    || draft.ttsModel !== companion.value.ttsModel;
  if (dom.voiceTest) {
    dom.voiceTest.disabled = companion.status === 'saving' || !draft.ttsConfigured || ttsDraftChanged;
    dom.voiceTest.title = ttsDraftChanged ? '先保存 TTS API 设置' : '';
  }
  if (dom.companionApiKey.value !== draft.apiKey) dom.companionApiKey.value = draft.apiKey;
  dom.companionApiKey.placeholder = companion.value.apiKeyConfigured ? '已保存；留空表示不修改' : '输入 API key';
  dom.companionKeyState.textContent = companion.value.apiKeyConfigured ? '密钥已保存在服务端，页面不会回显。' : '尚未保存 API key。';
  if (dom.ttsApiKey && dom.ttsApiKey.value !== draft.ttsApiKey) dom.ttsApiKey.value = draft.ttsApiKey;
  if (dom.ttsApiKey) dom.ttsApiKey.placeholder = companion.value.ttsApiKeyConfigured ? '已保存；留空表示不修改' : '输入 TTS API key';
  if (dom.ttsKeyState) dom.ttsKeyState.textContent = companion.value.ttsApiKeyConfigured ? 'TTS 密钥已保存在服务端，页面不会回显。' : '尚未保存 TTS API key。';
  dom.companionConnectionState.textContent = companion.value.configured ? '当前 LLM 连接信息完整。' : '请填写地址、API key 与模型。';
  dom.companionSave.disabled = !companion.dirty || companion.status === 'saving';
  dom.companionSave.textContent = companion.status === 'saving' ? '正在保存…' : companion.dirty ? '保存连接与设定' : '已是当前设定';
}
