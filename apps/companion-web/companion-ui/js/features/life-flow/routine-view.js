import { getRoutineActions } from './life-flow-state.js';

const ROUTINE_VIEWS = new Set([
  'routines', 'routine-detail', 'routine-create', 'routine-edit',
]);
const SCHEDULE_LABELS = Object.freeze({ daily: '每日', weekly: '每周', unknown: '周期未知' });
const REMINDER_LABELS = Object.freeze({
  none: '不提醒',
  remind: '轻声提醒',
  unknown: '提醒方式未知',
});

function routineNode(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function button(label, action, className = '') {
  const element = routineNode('button', className, label);
  element.type = 'button';
  if (action) element.dataset.action = action;
  return element;
}

function setVisible(node, visible) {
  if (node) node.hidden = !visible;
}

function selectedRoutine(routinesState) {
  const index = routinesState?.selectedIndex;
  return Number.isInteger(index) ? routinesState.items?.[index] ?? null : null;
}

function setRoutineSubview(dom, activeView) {
  const list = activeView === 'routines';
  const detail = activeView === 'routine-detail';
  const form = activeView === 'routine-create' || activeView === 'routine-edit';
  setVisible(dom.panel, ROUTINE_VIEWS.has(activeView));
  setVisible(dom.list, list);
  setVisible(dom.listState, list);
  setVisible(dom.create, list);
  setVisible(dom.form, form);
  setVisible(dom.error, detail || form);
  for (const node of [dom.detail, dom.checkin, dom.deactivate, dom.confirmation]) {
    setVisible(node, detail);
  }
}

function renderRoutineList(dom, routinesState) {
  const items = Array.isArray(routinesState?.items) ? routinesState.items : [];
  const stateNodes = [];
  if (routinesState?.status === 'loading') stateNodes.push(routineNode('p', '', '日常正在靠近……'));
  if (routinesState?.status === 'refreshing') stateNodes.push(routineNode('p', '', '正在轻轻更新……'));
  if (routinesState?.status === 'error') {
    stateNodes.push(routineNode('p', '', routinesState.error?.message || '日常暂时没有展开。'));
    stateNodes.push(button('再试一次', 'retry', 'today-secondary-button'));
  }
  if (routinesState?.status === 'ready' && items.length === 0) {
    stateNodes.push(routineNode('p', '', '还没有固定日常，可以从一件很小的事开始。'));
  }
  dom.listState.replaceChildren(...stateNodes);
  dom.listState.hidden = stateNodes.length === 0;
  dom.list.replaceChildren(...items.map((item, index) => {
    const row = routineNode('li', 'resource-list-item');
    const entry = button('', null, 'resource-list-entry');
    entry.dataset.itemIndex = String(index);
    entry.append(
      routineNode('span', 'resource-list-title', item.title),
      routineNode(
        'span',
        'resource-list-meta',
        `${SCHEDULE_LABELS[item.schedule] || SCHEDULE_LABELS.unknown} · ${item.active ? '正在照看' : '已停用'}`,
      ),
    );
    row.append(entry);
    return row;
  }));
}

function renderRoutineDetail(dom, routinesState) {
  const item = selectedRoutine(routinesState);
  if (!item) {
    dom.detail.replaceChildren(routineNode('p', '', '没有找到这个日常。'));
    setVisible(dom.checkin, false);
    setVisible(dom.deactivate, false);
    setVisible(dom.confirmation, false);
    return;
  }
  dom.detail.replaceChildren(
    routineNode('p', 'resource-kicker', item.active ? '正在照看' : '已停用'),
    routineNode('h3', 'resource-detail-title', item.title),
    routineNode(
      'p',
      'resource-detail-meta',
      `${SCHEDULE_LABELS[item.schedule] || SCHEDULE_LABELS.unknown} · ${REMINDER_LABELS[item.reminderPolicy] || REMINDER_LABELS.unknown}`,
    ),
  );

  const actions = getRoutineActions(item.active);
  const pending = routinesState.action?.status === 'pending';
  const editable = actions.includes('edit');
  let edit = dom.detail.querySelector('[data-action="edit"]');
  if (editable) {
    edit = button('编辑日常', 'edit', 'today-secondary-button');
    edit.disabled = pending;
    dom.detail.append(edit);
  }

  setVisible(dom.checkin, actions.includes('checkin'));
  dom.checkin.disabled = pending || item.checkinStatus === 'completed';
  dom.checkin.textContent = item.checkinStatus === 'completed'
    ? '今日已照看'
    : pending && routinesState.action?.kind === 'checkin' ? '正在记下……' : '照看今天';
  setVisible(dom.deactivate, actions.includes('deactivate'));
  dom.deactivate.disabled = pending;
  setVisible(dom.confirmation, routinesState.action?.confirmingDeactivate === true);
  dom.error.textContent = routinesState.action?.error?.message || '';
  dom.error.hidden = !routinesState.action?.error;
}

function renderRoutineForm(dom, routinesState, activeView) {
  const editor = routinesState.editor;
  const draft = editor?.draft || {};
  const pending = editor?.status === 'pending';
  dom.title.value = draft.title || '';
  dom.schedule.value = draft.schedule || 'daily';
  dom.reminderPolicy.value = draft.reminderPolicy || 'none';
  dom.title.readOnly = pending;
  dom.schedule.disabled = pending;
  dom.reminderPolicy.disabled = pending;
  dom.submit.disabled = pending;
  dom.cancelEdit.disabled = pending;
  dom.submit.textContent = activeView === 'routine-create' ? '创建日常' : '保存修改';
  dom.error.textContent = editor?.error?.message || '';
  dom.error.hidden = !editor?.error;
}

function eventIndex(value) {
  return /^\d+$/.test(value || '') ? Number(value) : null;
}

export function createRoutineView(dom, { dispatch, announce = () => {} }) {
  const emit = (event) => dispatch(Object.freeze(event));
  let lastState = null;

  function handleSubmit(event) {
    if (event.target !== dom.form) return;
    event.preventDefault();
    emit({ type: 'SUBMIT' });
  }

  function handleInput(event) {
    if (event.target === dom.title) {
      emit({ type: 'FIELD', field: 'title', value: event.target.value });
    }
  }

  function handleChange(event) {
    if (event.target === dom.schedule) {
      emit({ type: 'FIELD', field: 'schedule', value: event.target.value });
    } else if (event.target === dom.reminderPolicy) {
      emit({ type: 'FIELD', field: 'reminderPolicy', value: event.target.value });
    }
  }

  function handleClick(event) {
    const target = event.target?.closest?.('button');
    if (!target || !dom.panel.contains(target) || target.disabled) return;
    const action = target.dataset.action;
    if (target === dom.back) emit({ type: 'BACK' });
    else if (target === dom.create) emit({ type: 'CREATE' });
    else if (target === dom.cancelEdit) emit({ type: 'CANCEL_EDIT' });
    else if (target === dom.checkin) emit({ type: 'CHECKIN' });
    else if (target === dom.deactivate) emit({ type: 'DEACTIVATE_INTENT' });
    else if (action === 'retry') emit({ type: 'RETRY_LOAD' });
    else if (action === 'edit') emit({ type: 'EDIT' });
    else if (action === 'deactivate-confirm') emit({ type: 'DEACTIVATE_CONFIRM' });
    else if (action === 'deactivate-cancel') emit({ type: 'DEACTIVATE_CANCEL' });
    else {
      const index = eventIndex(target.dataset.itemIndex);
      if (index !== null) emit({ type: 'SELECT', index });
    }
  }

  dom.panel.addEventListener('click', handleClick);
  dom.panel.addEventListener('input', handleInput);
  dom.panel.addEventListener('change', handleChange);
  dom.panel.addEventListener('submit', handleSubmit);

  return Object.freeze({
    render(routinesState, activeView) {
      lastState = routinesState;
      setRoutineSubview(dom, activeView);
      if (activeView === 'routines') renderRoutineList(dom, routinesState);
      else if (activeView === 'routine-detail') renderRoutineDetail(dom, routinesState);
      else if (activeView === 'routine-create' || activeView === 'routine-edit') {
        renderRoutineForm(dom, routinesState, activeView);
      }
    },
    focusEntry(activeView) {
      const selectedEntry = Number.isInteger(lastState?.selectedIndex)
        ? dom.list.querySelector(`[data-item-index="${lastState.selectedIndex}"]`)
        : null;
      const target = activeView === 'routines'
        ? selectedEntry || dom.create
        : activeView === 'routine-detail'
          ? dom.back
          : activeView === 'routine-create' || activeView === 'routine-edit' ? dom.title : null;
      requestAnimationFrame(() => {
        if (target && !target.hidden && !target.disabled) target.focus({ preventScroll: true });
        else if (ROUTINE_VIEWS.has(activeView)) announce('当前日常视图已经打开。');
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
