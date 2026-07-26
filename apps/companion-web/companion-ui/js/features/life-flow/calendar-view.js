import { getCalendarActions } from './life-flow-state.js';

const CALENDAR_VIEWS = new Set([
  'calendar-events', 'calendar-detail', 'calendar-create', 'calendar-edit',
]);
const STATUS_LABELS = Object.freeze({ active: '正在窗框上', deleted: '已经移出', unknown: '状态未知' });

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

function selectedEvent(state) {
  return Number.isInteger(state?.selectedIndex) ? state.items?.[state.selectedIndex] ?? null : null;
}

function formatEventTime(item) {
  const start = new Date(item.startsAt);
  const end = item.endsAt ? new Date(item.endsAt) : null;
  if (Number.isNaN(start.getTime())) return '时间未定';
  const date = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(start);
  if (item.allDay) {
    if (end && !Number.isNaN(end.getTime())) {
      const endDate = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(end);
      return date === endDate ? `${date} · 全天` : `${date} — ${endDate} · 全天`;
    }
    return `${date} · 全天`;
  }
  const time = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  });
  const startTime = time.format(start);
  if (!end || Number.isNaN(end.getTime())) return `${date} · ${startTime}`;
  return `${date} · ${startTime} — ${time.format(end)}`;
}

function setSubview(dom, view) {
  const list = view === 'calendar-events';
  const detail = view === 'calendar-detail';
  const form = view === 'calendar-create' || view === 'calendar-edit';
  setVisible(dom.panel, CALENDAR_VIEWS.has(view));
  setVisible(dom.listState, list);
  setVisible(dom.scale, list);
  setVisible(dom.create, list);
  setVisible(dom.detail, detail);
  setVisible(dom.detailActions, detail);
  setVisible(dom.confirmation, detail);
  setVisible(dom.form, form);
  setVisible(dom.error, detail || form);
}

function renderList(dom, state) {
  const items = Array.isArray(state?.items) ? state.items : [];
  const messages = [];
  if (state?.status === 'loading') {
    const material = node('div', 'calendar-loading-material');
    material.setAttribute('aria-label', '日历刻度正在显现');
    material.append(...Array.from({ length: 3 }, () => node('span', 'calendar-loading-tick')));
    messages.push(material);
  }
  if (state?.status === 'refreshing') messages.push(node('p', '', '正在轻轻更新……'));
  if (state?.status === 'error') {
    messages.push(node('p', '', state.error?.message || '日历刻度暂时没有展开。'));
    messages.push(button('再试一次', 'retry', 'today-secondary-button'));
  }
  if (state?.status === 'ready' && items.length === 0) {
    messages.push(node('p', 'calendar-empty-copy', '窗框上还没有落下时间刻度。'));
  }
  dom.listState.replaceChildren(...messages);
  dom.listState.hidden = messages.length === 0;
  dom.scale.replaceChildren(...items.map((item, index) => {
    const row = node('li', `calendar-event ${item.allDay ? 'is-all-day' : 'is-timed'} is-${item.status}`);
    const entry = button('', null, 'calendar-entry');
    entry.dataset.itemIndex = String(index);
    const rail = node('span', 'calendar-rail');
    rail.append(node('span', 'calendar-tick'));
    rail.setAttribute('aria-hidden', 'true');
    const copy = node('span', 'calendar-event-copy');
    const time = node('time', 'calendar-time', formatEventTime(item));
    time.dateTime = item.startsAt;
    copy.append(node('span', 'calendar-title', item.title), time);
    entry.append(rail, copy, node('span', 'calendar-status', item.allDay ? '全天' : STATUS_LABELS[item.status]));
    row.append(entry);
    return row;
  }));
}

function renderDetail(dom, state) {
  const item = selectedEvent(state);
  if (!item) {
    dom.detail.replaceChildren(node('p', '', '没有找到这个日历刻度。'));
    dom.detailActions.replaceChildren();
    return;
  }
  const pending = state.action?.status === 'pending';
  const time = node('time', 'calendar-detail-time', formatEventTime(item));
  time.dateTime = item.startsAt;
  dom.detail.className = `calendar-detail ${item.allDay ? 'is-all-day' : 'is-timed'}`;
  dom.detail.replaceChildren(
    node('p', 'calendar-detail-kicker', item.allDay ? '全天光带' : '时间刻度'),
    node('h3', 'calendar-detail-title', item.title),
    time,
    node('p', 'calendar-detail-timezone', item.timezoneName),
  );
  dom.detailActions.replaceChildren(...getCalendarActions(item.status).map((action) => {
    const actionButton = button(
      action === 'edit' ? '编辑' : '移出窗框',
      action,
      action === 'edit' ? 'life-flow-primary-action' : 'today-secondary-button',
    );
    actionButton.disabled = pending;
    return actionButton;
  }));
  dom.detailActions.hidden = getCalendarActions(item.status).length === 0;
  dom.confirmation.hidden = !state.action?.confirmingRemove;
  dom.confirmation.querySelectorAll('button').forEach((entry) => { entry.disabled = pending; });
  dom.error.textContent = state.action?.error?.message || '';
  dom.error.hidden = !state.action?.error;
}

function renderForm(dom, state, view) {
  const editor = state.editor;
  const draft = editor?.draft || {};
  const pending = editor?.status === 'pending';
  const allDay = draft.allDay === true;
  dom.formHeading.textContent = view === 'calendar-edit' ? '调整窗框刻度' : '落下一段时间';
  dom.title.value = draft.title || '';
  dom.allDay.checked = allDay;
  dom.timedFields.hidden = allDay;
  dom.dateFields.hidden = !allDay;
  dom.startsAt.value = draft.startsAt || '';
  dom.endsAt.value = draft.endsAt || '';
  dom.startDate.value = draft.startDate || '';
  dom.endDate.value = draft.endDate || '';
  [dom.title, dom.startsAt, dom.endsAt, dom.startDate, dom.endDate]
    .forEach((entry) => { entry.readOnly = pending; });
  dom.allDay.disabled = pending;
  dom.startsAt.required = !allDay;
  dom.startDate.required = allDay;
  dom.submit.disabled = pending;
  dom.cancelEdit.disabled = pending;
  dom.submit.textContent = pending ? '正在落下……' : view === 'calendar-edit' ? '保存变化' : '留下刻度';
  dom.error.textContent = editor?.error?.message || '';
  dom.error.hidden = !editor?.error;
}

export function createCalendarView(dom, { dispatch, announce = () => {} }) {
  const emit = (event) => dispatch(Object.freeze(event));
  let lastState = null;

  function handleClick(event) {
    const target = event.target?.closest?.('button');
    if (!target || !dom.panel.contains(target) || target.disabled) return;
    if (target === dom.back) emit({ type: 'BACK' });
    else if (target === dom.create) emit({ type: 'CREATE' });
    else if (target === dom.cancelEdit) emit({ type: 'CANCEL_EDIT' });
    else if (target.dataset.action === 'retry') emit({ type: 'RETRY_LOAD' });
    else if (target.dataset.action === 'edit') emit({ type: 'EDIT' });
    else if (target.dataset.action === 'remove') emit({ type: 'REMOVE_INTENT' });
    else if (target.dataset.action === 'remove-confirm') emit({ type: 'REMOVE_CONFIRM' });
    else if (target.dataset.action === 'remove-cancel') emit({ type: 'REMOVE_CANCEL' });
    else if (/^\d+$/.test(target.dataset.itemIndex || '')) {
      emit({ type: 'SELECT', index: Number(target.dataset.itemIndex) });
    }
  }

  function handleInput(event) {
    const fields = new Map([
      [dom.title, 'title'], [dom.startsAt, 'startsAt'], [dom.endsAt, 'endsAt'],
      [dom.startDate, 'startDate'], [dom.endDate, 'endDate'],
    ]);
    const field = fields.get(event.target);
    if (field) emit({ type: 'FIELD', field, value: event.target.value });
  }

  function handleChange(event) {
    if (event.target === dom.allDay) {
      emit({ type: 'FIELD', field: 'allDay', value: event.target.checked });
    }
  }

  function handleSubmit(event) {
    if (event.target !== dom.form) return;
    event.preventDefault();
    const draft = lastState?.editor?.draft;
    const start = draft?.allDay ? draft.startDate : draft?.startsAt;
    const end = draft?.allDay ? draft.endDate : draft?.endsAt;
    if (start && end && end < start) {
      dom.error.textContent = '结束光影不能早于开始。';
      dom.error.hidden = false;
      announce('结束光影不能早于开始。');
      return;
    }
    emit({ type: 'SUBMIT' });
  }

  dom.panel.addEventListener('click', handleClick);
  dom.panel.addEventListener('input', handleInput);
  dom.panel.addEventListener('change', handleChange);
  dom.panel.addEventListener('submit', handleSubmit);

  return Object.freeze({
    render(state, view) {
      lastState = state;
      setSubview(dom, view);
      if (view === 'calendar-events') renderList(dom, state);
      else if (view === 'calendar-detail') renderDetail(dom, state);
      else if (view === 'calendar-create' || view === 'calendar-edit') renderForm(dom, state, view);
    },
    focusEntry(view) {
      const selected = Number.isInteger(lastState?.selectedIndex)
        ? dom.scale.querySelector(`[data-item-index="${lastState.selectedIndex}"]`) : null;
      const target = view === 'calendar-events' ? selected || dom.create
        : view === 'calendar-detail' ? dom.back
          : view === 'calendar-create' || view === 'calendar-edit' ? dom.title : null;
      requestAnimationFrame(() => {
        if (target && !target.hidden && !target.disabled) target.focus({ preventScroll: true });
        else if (CALENDAR_VIEWS.has(view)) announce('当前日历视图已经打开。');
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
