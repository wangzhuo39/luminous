import { getReminderActions } from './life-flow-state.js';

const REMINDER_VIEWS = new Set([
  'reminders', 'reminder-detail', 'reminder-create', 'reminder-edit',
]);
const ACTIVE_STATUSES = new Set(['scheduled', 'due', 'snoozed']);
const STATUS_LABELS = Object.freeze({
  scheduled: '等待抵达',
  due: '此刻抵达',
  snoozed: '稍后再来',
  completed: '已经完成',
  cancelled: '已经取消',
  expired: '已经远去',
  unknown: '状态未知',
});
const RECURRENCE_LABELS = Object.freeze({ daily: '每日', weekly: '每周' });

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

function selectedReminder(state) {
  return Number.isInteger(state?.selectedIndex) ? state.items?.[state.selectedIndex] ?? null : null;
}

function formatInstant(value, withDate = true) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未定';
  return new Intl.DateTimeFormat('zh-CN', {
    ...(withDate ? { month: 'long', day: 'numeric' } : {}),
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date);
}

function setSubview(dom, view) {
  const list = view === 'reminders';
  const detail = view === 'reminder-detail';
  const form = view === 'reminder-create' || view === 'reminder-edit';
  setVisible(dom.panel, REMINDER_VIEWS.has(view));
  setVisible(dom.listState, list);
  setVisible(dom.activeList, list);
  setVisible(dom.terminalRegion, list);
  setVisible(dom.create, list);
  setVisible(dom.detail, detail);
  setVisible(dom.detailActions, detail);
  setVisible(dom.snoozeForm, detail);
  setVisible(dom.confirmation, detail);
  setVisible(dom.form, form);
  setVisible(dom.error, detail || form);
}

function createEntry(item, index) {
  const row = node('li', `reminder-item is-${item.status}`);
  const entry = button('', null, 'reminder-entry');
  entry.dataset.itemIndex = String(index);
  const dust = node('span', 'reminder-dust');
  dust.setAttribute('aria-hidden', 'true');
  const copy = node('span', 'reminder-item-copy');
  copy.append(
    node('span', 'reminder-title', item.title),
    node('span', 'reminder-meta', formatInstant(item.dueAt)),
  );
  entry.append(dust, copy, node('span', 'reminder-status', STATUS_LABELS[item.status]));
  row.append(entry);
  return row;
}

export function createReminderView(dom, { dispatch, announce = () => {} }) {
  const emit = (event) => dispatch(Object.freeze(event));
  let lastState = null;
  let terminalExpanded = false;
  let snoozeOpen = false;
  let snoozeDraft = '';
  let detailKey = null;

  function renderList(state) {
    const items = Array.isArray(state?.items) ? state.items : [];
    const active = [];
    const terminal = [];
    items.forEach((item, index) => {
      (ACTIVE_STATUSES.has(item.status) ? active : terminal).push({ item, index });
    });
    const messages = [];
    if (state?.status === 'loading') {
      const material = node('div', 'reminder-loading-material');
      material.setAttribute('aria-label', '提醒光尘正在凝结');
      material.append(...Array.from({ length: 3 }, () => node('span', 'reminder-loading-dust')));
      messages.push(material);
    }
    if (state?.status === 'refreshing') messages.push(node('p', '', '正在轻轻更新……'));
    if (state?.status === 'error') {
      messages.push(node('p', '', state.error?.message || '提醒暂时没有展开。'));
      messages.push(button('再试一次', 'retry', 'today-secondary-button'));
    }
    if (state?.status === 'ready' && items.length === 0) {
      messages.push(node('p', 'reminder-empty-copy', '眼前还没有需要接住的提醒光尘。'));
    }
    dom.listState.replaceChildren(...messages);
    dom.listState.hidden = messages.length === 0;
    dom.activeList.replaceChildren(...active.map(({ item, index }) => createEntry(item, index)));
    dom.terminalToggle.textContent = terminalExpanded
      ? '收起已经落定的光尘'
      : `已经落定的光尘 · ${terminal.length}`;
    dom.terminalToggle.setAttribute('aria-expanded', String(terminalExpanded));
    dom.terminalToggle.hidden = terminal.length === 0;
    dom.terminalList.hidden = !terminalExpanded;
    dom.terminalList.replaceChildren(...terminal.map(({ item, index }) => createEntry(item, index)));
    dom.terminalRegion.hidden = state?.status !== 'ready' || terminal.length === 0;
  }

  function renderDetail(state) {
    const item = selectedReminder(state);
    if (!item) {
      dom.detail.replaceChildren(node('p', '', '没有找到这个提醒。'));
      dom.detailActions.replaceChildren();
      return;
    }
    if (detailKey !== item.key) {
      detailKey = item.key;
      snoozeOpen = false;
      snoozeDraft = '';
    }
    const pending = state.action?.status === 'pending';
    const recurrence = item.recurrence ? ` · ${RECURRENCE_LABELS[item.recurrence]}` : '';
    dom.detail.className = `reminder-detail is-${item.status}`;
    const time = node('time', 'reminder-detail-time', formatInstant(item.dueAt));
    time.dateTime = item.dueAt;
    dom.detail.replaceChildren(
      node('p', 'reminder-detail-kicker', STATUS_LABELS[item.status]),
      node('h3', 'reminder-detail-title', item.title),
      time,
      node('p', 'reminder-detail-timezone', `${item.timezoneName}${recurrence}`),
    );
    if (item.description) dom.detail.append(node('p', 'reminder-detail-description', item.description));

    dom.detailActions.replaceChildren(...getReminderActions(item.status).map((action) => {
      const labels = { complete: '已经完成', snooze: '稍后提醒', cancel: '取消提醒', edit: '编辑' };
      const actionButton = button(labels[action], action,
        action === 'complete' ? 'life-flow-primary-action' : 'today-secondary-button');
      actionButton.disabled = pending;
      if (pending && state.action?.transitionAction === action) actionButton.textContent = '正在落定……';
      return actionButton;
    }));
    dom.detailActions.hidden = getReminderActions(item.status).length === 0;
    dom.snoozeForm.hidden = !snoozeOpen || !ACTIVE_STATUSES.has(item.status);
    dom.snoozeAt.value = snoozeDraft;
    dom.snoozeAt.readOnly = pending;
    dom.snoozeSubmit.disabled = pending;
    dom.snoozeDismiss.disabled = pending;
    dom.confirmation.hidden = !state.action?.confirmingCancel;
    dom.confirmation.querySelectorAll('button').forEach((entry) => { entry.disabled = pending; });
    dom.error.textContent = state.action?.error?.message || '';
    dom.error.hidden = !state.action?.error;
  }

  function renderForm(state, view) {
    const editor = state.editor;
    const draft = editor?.draft || {};
    const pending = editor?.status === 'pending';
    dom.formHeading.textContent = view === 'reminder-edit' ? '调整这粒光尘' : '凝结一粒提醒光尘';
    dom.title.value = draft.title || '';
    dom.description.value = draft.description || '';
    dom.dueAt.value = draft.dueAt || '';
    dom.recurrence.value = draft.recurrence || '';
    [dom.title, dom.description, dom.dueAt].forEach((entry) => { entry.readOnly = pending; });
    dom.recurrence.disabled = pending;
    dom.submit.disabled = pending;
    dom.cancelEdit.disabled = pending;
    dom.submit.textContent = pending ? '正在凝结……' : view === 'reminder-edit' ? '保存变化' : '留下提醒';
    dom.error.textContent = editor?.error?.message || '';
    dom.error.hidden = !editor?.error;
  }

  function handleClick(event) {
    const target = event.target?.closest?.('button');
    if (!target || !dom.panel.contains(target) || target.disabled) return;
    if (target === dom.back) emit({ type: 'BACK' });
    else if (target === dom.create) emit({ type: 'CREATE' });
    else if (target === dom.cancelEdit) emit({ type: 'CANCEL_EDIT' });
    else if (target === dom.terminalToggle) {
      terminalExpanded = !terminalExpanded;
      renderList(lastState);
    } else if (target === dom.snoozeDismiss) {
      snoozeOpen = false;
      renderDetail(lastState);
    } else if (target.dataset.action === 'retry') emit({ type: 'RETRY_LOAD' });
    else if (target.dataset.action === 'edit') emit({ type: 'EDIT' });
    else if (target.dataset.action === 'complete') emit({ type: 'COMPLETE' });
    else if (target.dataset.action === 'snooze') {
      snoozeOpen = true;
      renderDetail(lastState);
      requestAnimationFrame(() => dom.snoozeAt.focus({ preventScroll: true }));
    } else if (target.dataset.action === 'cancel') emit({ type: 'CANCEL_INTENT' });
    else if (target.dataset.action === 'cancel-confirm') emit({ type: 'CANCEL_CONFIRM' });
    else if (target.dataset.action === 'cancel-dismiss') emit({ type: 'CANCEL_DISMISS' });
    else if (/^\d+$/.test(target.dataset.itemIndex || '')) {
      emit({ type: 'SELECT', index: Number(target.dataset.itemIndex) });
    }
  }

  function handleInput(event) {
    if (event.target === dom.snoozeAt) snoozeDraft = event.target.value;
    else if ([dom.title, dom.description, dom.dueAt].includes(event.target)) {
      const field = event.target === dom.title ? 'title'
        : event.target === dom.description ? 'description' : 'dueAt';
      emit({ type: 'FIELD', field, value: event.target.value });
    }
  }

  function handleChange(event) {
    if (event.target === dom.recurrence) {
      emit({ type: 'FIELD', field: 'recurrence', value: event.target.value });
    }
  }

  function handleSubmit(event) {
    if (event.target === dom.form) {
      event.preventDefault();
      emit({ type: 'SUBMIT' });
    } else if (event.target === dom.snoozeForm) {
      event.preventDefault();
      emit({ type: 'SNOOZE', dueAt: snoozeDraft });
    }
  }

  dom.panel.addEventListener('click', handleClick);
  dom.panel.addEventListener('input', handleInput);
  dom.panel.addEventListener('change', handleChange);
  dom.panel.addEventListener('submit', handleSubmit);

  return Object.freeze({
    render(state, view) {
      lastState = state;
      setSubview(dom, view);
      if (view === 'reminders') renderList(state);
      else if (view === 'reminder-detail') renderDetail(state);
      else if (view === 'reminder-create' || view === 'reminder-edit') renderForm(state, view);
    },
    focusEntry(view) {
      const selected = Number.isInteger(lastState?.selectedIndex)
        ? dom.activeList.querySelector(`[data-item-index="${lastState.selectedIndex}"]`)
          || dom.terminalList.querySelector(`[data-item-index="${lastState.selectedIndex}"]`)
        : null;
      const target = view === 'reminders' ? selected || dom.create
        : view === 'reminder-detail' ? dom.back
          : view === 'reminder-create' || view === 'reminder-edit' ? dom.title : null;
      requestAnimationFrame(() => {
        if (target && !target.hidden && !target.disabled) target.focus({ preventScroll: true });
        else if (REMINDER_VIEWS.has(view)) announce('当前提醒视图已经打开。');
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
