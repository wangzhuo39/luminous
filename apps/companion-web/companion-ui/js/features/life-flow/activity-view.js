import { getActivityActions } from './life-flow-state.js';

const ACTIVITY_VIEWS = new Set(['activities', 'activity-detail', 'activity-create']);
const KIND_LABELS = Object.freeze({
  focus: '专注', checkin: '相伴', planning: '梳理', reflection: '回望', unknown: '类型未知',
});
const STATUS_LABELS = Object.freeze({
  planned: '等待开始', active: '正在发生', paused: '暂时停驻', completed: '已经完成',
  cancelled: '已经取消', expired: '已经远去', unknown: '状态未知',
});
const ACTION_LABELS = Object.freeze({
  start: '开始', pause: '暂停', resume: '继续', complete: '完成', cancel: '取消',
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

function selectedActivity(state) {
  const index = state?.selectedIndex;
  return Number.isInteger(index) ? state.items?.[index] ?? null : null;
}

function setSubview(dom, activeView) {
  const list = activeView === 'activities';
  const detail = activeView === 'activity-detail';
  const form = activeView === 'activity-create';
  setVisible(dom.panel, ACTIVITY_VIEWS.has(activeView));
  setVisible(dom.list, list);
  setVisible(dom.listState, list);
  setVisible(dom.create, list);
  setVisible(dom.detail, detail);
  setVisible(dom.crystal, detail);
  setVisible(dom.statusActions, detail);
  setVisible(dom.form, form);
  setVisible(dom.error, detail || form);
}

function renderList(dom, state) {
  const items = Array.isArray(state?.items) ? state.items : [];
  const messages = [];
  if (state?.status === 'loading') {
    const cradle = node('div', 'activity-loading-material');
    cradle.setAttribute('aria-label', '活动正在靠近');
    cradle.append(...Array.from({ length: 3 }, () => node('span', 'activity-loading-shard')));
    messages.push(cradle);
  }
  if (state?.status === 'refreshing') messages.push(node('p', '', '正在轻轻更新……'));
  if (state?.status === 'error') {
    messages.push(node('p', '', state.error?.message || '活动暂时没有展开。'));
    messages.push(button('再试一次', 'retry', 'today-secondary-button'));
  }
  if (state?.status === 'ready' && items.length === 0) {
    messages.push(node('p', 'activity-empty-copy', '还没有共同度过的活动'));
  }
  dom.listState.replaceChildren(...messages);
  dom.listState.hidden = messages.length === 0;
  dom.list.replaceChildren(...items.map((item, index) => {
    const row = node('li', `activity-list-item is-${item.status}`);
    const entry = button('', null, 'activity-list-entry');
    entry.dataset.itemIndex = String(index);
    const mark = node('span', 'activity-kind-mark');
    mark.setAttribute('aria-hidden', 'true');
    entry.append(
      mark,
      node('span', 'activity-list-copy'),
      node('span', 'activity-list-status', STATUS_LABELS[item.status] || STATUS_LABELS.unknown),
    );
    const copy = entry.querySelector('.activity-list-copy');
    copy.append(
      node('span', 'activity-list-title', item.title),
      node('span', 'activity-list-kind', KIND_LABELS[item.kind] || KIND_LABELS.unknown),
    );
    row.append(entry);
    return row;
  }));
}

function appendTime(detail, label, value) {
  if (!value) return;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return;
  const line = node('p', 'activity-detail-time');
  line.append(node('span', '', `${label} `));
  const time = node('time', '', new Intl.DateTimeFormat('zh-CN', {
    month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date));
  time.dateTime = value;
  line.append(time);
  detail.append(line);
}

function renderDetail(dom, state) {
  const item = selectedActivity(state);
  if (!item) {
    dom.detail.replaceChildren(node('p', '', '没有找到这个活动。'));
    dom.statusActions.replaceChildren();
    setVisible(dom.crystal, false);
    return;
  }

  dom.crystal.className = `activity-crystal is-${item.status}`;
  dom.crystal.dataset.activityStatus = item.status;
  dom.crystal.setAttribute('aria-label', `时间晶体，${STATUS_LABELS[item.status] || STATUS_LABELS.unknown}`);
  dom.detail.replaceChildren(
    node('p', 'activity-detail-kicker', KIND_LABELS[item.kind] || KIND_LABELS.unknown),
    node('h3', 'activity-detail-title', item.title),
    node('p', 'activity-detail-status', STATUS_LABELS[item.status] || STATUS_LABELS.unknown),
  );
  appendTime(dom.detail, '开始于', item.startedAt);
  appendTime(dom.detail, '结束于', item.endedAt);
  if (item.summary) dom.detail.append(node('p', 'activity-detail-summary', item.summary));

  const pending = state.action?.status === 'pending';
  const actions = getActivityActions(item.status);
  dom.statusActions.replaceChildren(...actions.map((action) => {
    const actionButton = button(
      pending && state.action?.transitionAction === action ? '正在凝结……' : ACTION_LABELS[action],
      action,
      action === 'start' || action === 'resume' || action === 'complete'
        ? 'life-flow-primary-action'
        : 'today-secondary-button',
    );
    actionButton.disabled = pending;
    return actionButton;
  }));
  dom.statusActions.hidden = actions.length === 0;
  dom.error.textContent = state.action?.error?.message || '';
  dom.error.hidden = !state.action?.error;
}

function renderForm(dom, state) {
  const editor = state.editor;
  const draft = editor?.draft || {};
  const pending = editor?.status === 'pending';
  dom.title.value = draft.title || '';
  dom.kind.value = draft.kind || 'focus';
  dom.title.readOnly = pending;
  dom.kind.disabled = pending;
  dom.submit.disabled = pending;
  dom.cancelEdit.disabled = pending;
  dom.submit.textContent = pending ? '正在凝结……' : '计划活动';
  dom.error.textContent = editor?.error?.message || '';
  dom.error.hidden = !editor?.error;
}

function eventIndex(value) {
  return /^\d+$/.test(value || '') ? Number(value) : null;
}

export function createActivityView(dom, { dispatch, announce = () => {} }) {
  const emit = (event) => dispatch(Object.freeze(event));
  let lastState = null;

  function handleClick(event) {
    const target = event.target?.closest?.('button');
    if (!target || !dom.panel.contains(target) || target.disabled) return;
    if (target === dom.back) emit({ type: 'BACK' });
    else if (target === dom.create) emit({ type: 'CREATE' });
    else if (target === dom.cancelEdit) emit({ type: 'CANCEL_EDIT' });
    else if (target.dataset.action === 'retry') emit({ type: 'RETRY_LOAD' });
    else if (Object.hasOwn(ACTION_LABELS, target.dataset.action)) {
      emit({ type: 'TRANSITION', action: target.dataset.action });
    } else {
      const index = eventIndex(target.dataset.itemIndex);
      if (index !== null) emit({ type: 'SELECT', index });
    }
  }

  function handleInput(event) {
    if (event.target === dom.title) {
      emit({ type: 'FIELD', field: 'title', value: event.target.value });
    }
  }

  function handleChange(event) {
    if (event.target === dom.kind) {
      emit({ type: 'FIELD', field: 'kind', value: event.target.value });
    }
  }

  function handleSubmit(event) {
    if (event.target !== dom.form) return;
    event.preventDefault();
    emit({ type: 'SUBMIT' });
  }

  dom.panel.addEventListener('click', handleClick);
  dom.panel.addEventListener('input', handleInput);
  dom.panel.addEventListener('change', handleChange);
  dom.panel.addEventListener('submit', handleSubmit);

  return Object.freeze({
    render(state, activeView) {
      lastState = state;
      setSubview(dom, activeView);
      if (activeView === 'activities') renderList(dom, state);
      else if (activeView === 'activity-detail') renderDetail(dom, state);
      else if (activeView === 'activity-create') renderForm(dom, state);
    },
    focusEntry(activeView) {
      const selectedEntry = Number.isInteger(lastState?.selectedIndex)
        ? dom.list.querySelector(`[data-item-index="${lastState.selectedIndex}"]`)
        : null;
      const target = activeView === 'activities' ? selectedEntry || dom.create
        : activeView === 'activity-detail' ? dom.back
          : activeView === 'activity-create' ? dom.title : null;
      requestAnimationFrame(() => {
        if (target && !target.hidden && !target.disabled) target.focus({ preventScroll: true });
        else if (ACTIVITY_VIEWS.has(activeView)) announce('当前活动视图已经打开。');
      });
    },
    destroy() {
      dom.panel.removeEventListener('click', handleClick);
      dom.panel.removeEventListener('input', handleInput);
      dom.panel.removeEventListener('change', handleChange);
      dom.panel.removeEventListener('submit', handleSubmit);
    },
  });
}
