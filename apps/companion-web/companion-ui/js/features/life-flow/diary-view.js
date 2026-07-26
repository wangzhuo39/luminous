const DIARY_VIEWS = new Set(['diaries', 'diary-detail', 'diary-create', 'diary-edit']);
const STATUS_LABELS = Object.freeze({
  draft: '草稿', saved: '已保存', deleted: '已移出', unknown: '状态未知',
});

function node(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function button(label, action, className = '') {
  const element = node('button', className, label);
  element.type = 'button';
  if (action) element.dataset.action = action;
  return element;
}

function setVisible(element, visible) {
  if (element) element.hidden = !visible;
}

function selectedDiary(state) {
  const index = state?.selectedIndex;
  return Number.isInteger(index) ? state.items?.[index] ?? null : null;
}

function formatDate(value) {
  const match = typeof value === 'string' ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value) : null;
  if (!match) return '日期未定';
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
  if (Number.isNaN(date.getTime())) return '日期未定';
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
  }).format(date);
}

function setSubview(dom, activeView) {
  const list = activeView === 'diaries';
  const detail = activeView === 'diary-detail';
  const form = activeView === 'diary-create' || activeView === 'diary-edit';
  setVisible(dom.panel, DIARY_VIEWS.has(activeView));
  setVisible(dom.listState, list);
  setVisible(dom.list, list);
  setVisible(dom.create, list);
  setVisible(dom.generate, list);
  setVisible(dom.detail, detail);
  setVisible(dom.edit, detail);
  setVisible(dom.remove, detail);
  setVisible(dom.confirmation, detail);
  setVisible(dom.form, form);
  setVisible(dom.error, list || detail || form);
}

function renderList(dom, state) {
  const items = Array.isArray(state?.items) ? state.items : [];
  const messages = [];
  if (state?.status === 'loading') {
    const dust = node('div', 'diary-loading-dust');
    dust.setAttribute('aria-label', '日记正在靠近');
    dust.append(...Array.from({ length: 3 }, () => node('span', 'diary-loading-line')));
    messages.push(dust);
  }
  if (state?.status === 'refreshing') messages.push(node('p', '', '正在轻轻更新……'));
  if (state?.status === 'error') {
    messages.push(node('p', '', state.error?.message || '日记暂时没有展开。'));
    messages.push(button('再试一次', 'retry', 'today-secondary-button'));
  }
  if (state?.status === 'ready' && items.length === 0) {
    messages.push(node('p', 'diary-empty-copy', '今天的思绪，也可以在这里安放'));
  }
  dom.listState.replaceChildren(...messages);
  dom.listState.hidden = messages.length === 0;
  dom.list.replaceChildren(...items.map((item, index) => {
    const row = node('li', `diary-list-item is-${item.status}`);
    const entry = button('', null, 'diary-list-entry');
    entry.dataset.itemIndex = String(index);
    const date = node('time', 'diary-list-date', formatDate(item.date));
    if (item.date) date.dateTime = item.date;
    entry.append(
      node('span', 'diary-list-glint'),
      node('span', 'diary-list-title', item.title),
      date,
      node('span', 'diary-list-status', STATUS_LABELS[item.status] || STATUS_LABELS.unknown),
    );
    row.append(entry);
    return row;
  }));

  const generating = state.action?.status === 'pending' && state.action?.kind === 'draft';
  dom.generate.disabled = generating || state.status === 'loading' || state.status === 'refreshing';
  dom.create.disabled = state.action?.status === 'pending';
  dom.generate.textContent = generating ? '正在汇聚今日光影……' : '生成今日回顾';
  dom.error.textContent = state.action?.error?.message || '';
  dom.error.hidden = !state.action?.error;
}

function renderDetail(dom, state) {
  const item = selectedDiary(state);
  if (!item) {
    dom.detail.replaceChildren(node('p', '', '没有找到这篇日记。'));
    setVisible(dom.edit, false);
    setVisible(dom.remove, false);
    setVisible(dom.confirmation, false);
    return;
  }
  const date = node('time', 'diary-detail-date', formatDate(item.date));
  if (item.date) date.dateTime = item.date;
  dom.detail.replaceChildren(
    node('p', 'diary-detail-kicker', STATUS_LABELS[item.status] || STATUS_LABELS.unknown),
    date,
    node('h3', 'diary-detail-title', item.title),
    node('p', 'diary-detail-body', item.body),
  );
  const editable = item.status === 'draft' || item.status === 'saved';
  const pending = state.action?.status === 'pending';
  setVisible(dom.edit, editable);
  setVisible(dom.remove, editable);
  dom.edit.disabled = pending;
  dom.remove.disabled = pending;
  setVisible(dom.confirmation, editable && state.action?.confirmingRemove === true);
  dom.confirmation.querySelectorAll('button').forEach((control) => { control.disabled = pending; });
  dom.error.textContent = state.action?.error?.message || '';
  dom.error.hidden = !state.action?.error;
}

function renderForm(dom, state, activeView) {
  const editor = state.editor;
  const draft = editor?.draft || {};
  const pending = editor?.status === 'pending';
  const generated = activeView === 'diary-edit' && draft.status === 'draft';
  dom.form.dataset.editorKind = generated ? 'generated' : activeView === 'diary-create' ? 'manual' : 'saved';
  dom.formHeading.textContent = generated ? '整理今日回顾'
    : activeView === 'diary-create' ? '写下一页' : '编辑这篇日记';
  dom.formCaption.textContent = generated
    ? '这份草稿已经保存到 Luminous，修改后再把它收好。'
    : '让这一页保留你愿意留下的部分。';
  dom.title.value = draft.title || '';
  dom.body.value = draft.body || '';
  dom.title.readOnly = pending;
  dom.body.readOnly = pending;
  dom.submit.disabled = pending;
  dom.cancelEdit.disabled = pending;
  dom.submit.textContent = pending ? '正在收好……' : '保存到 Luminous';
  dom.error.textContent = editor?.error?.message || '';
  dom.error.hidden = !editor?.error;
}

function eventIndex(value) {
  return /^\d+$/.test(value || '') ? Number(value) : null;
}

export function createDiaryView(dom, { dispatch, announce = () => {} }) {
  const emit = (event) => dispatch(Object.freeze(event));
  let lastState = null;

  function handleClick(event) {
    const target = event.target?.closest?.('button');
    if (!target || !dom.panel.contains(target) || target.disabled) return;
    const action = target.dataset.action;
    if (target === dom.back) emit({ type: 'BACK' });
    else if (target === dom.create) emit({ type: 'CREATE' });
    else if (target === dom.generate) emit({ type: 'GENERATE' });
    else if (target === dom.edit) emit({ type: 'EDIT' });
    else if (target === dom.remove) emit({ type: 'REMOVE_INTENT' });
    else if (target === dom.cancelEdit) emit({ type: 'CANCEL_EDIT' });
    else if (action === 'retry') emit({ type: 'RETRY_LOAD' });
    else if (action === 'remove-confirm') emit({ type: 'REMOVE_CONFIRM' });
    else if (action === 'remove-cancel') emit({ type: 'REMOVE_CANCEL' });
    else {
      const index = eventIndex(target.dataset.itemIndex);
      if (index !== null) emit({ type: 'SELECT', index });
    }
  }

  function handleInput(event) {
    if (event.target === dom.title) emit({ type: 'FIELD', field: 'title', value: event.target.value });
    else if (event.target === dom.body) emit({ type: 'FIELD', field: 'body', value: event.target.value });
  }

  function handleSubmit(event) {
    if (event.target !== dom.form) return;
    event.preventDefault();
    emit({ type: 'SUBMIT' });
  }

  dom.panel.addEventListener('click', handleClick);
  dom.panel.addEventListener('input', handleInput);
  dom.panel.addEventListener('submit', handleSubmit);

  return Object.freeze({
    render(state, activeView) {
      lastState = state;
      setSubview(dom, activeView);
      if (activeView === 'diaries') renderList(dom, state);
      else if (activeView === 'diary-detail') renderDetail(dom, state);
      else if (activeView === 'diary-create' || activeView === 'diary-edit') {
        renderForm(dom, state, activeView);
      }
    },
    focusEntry(activeView) {
      const selectedEntry = Number.isInteger(lastState?.selectedIndex)
        ? dom.list.querySelector(`[data-item-index="${lastState.selectedIndex}"]`)
        : null;
      const target = activeView === 'diaries' ? selectedEntry || dom.create
        : activeView === 'diary-detail' ? dom.back
          : activeView === 'diary-create' || activeView === 'diary-edit' ? dom.title : null;
      requestAnimationFrame(() => {
        if (target && !target.hidden && !target.disabled) target.focus({ preventScroll: true });
        else if (DIARY_VIEWS.has(activeView)) announce('当前日记视图已经打开。');
      });
    },
    destroy() {
      dom.panel.removeEventListener('click', handleClick);
      dom.panel.removeEventListener('input', handleInput);
      dom.panel.removeEventListener('submit', handleSubmit);
    },
  });
}
