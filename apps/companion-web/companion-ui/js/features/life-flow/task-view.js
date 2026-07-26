import { getTaskActions } from './life-flow-state.js';
import { formatISOToLocalTimed, isISOInstant } from '../../shared/time.js';

const TASK_VIEWS = new Set(['tasks', 'task-detail', 'task-create', 'task-edit']);
const TRANSITIONS = new Set(['start', 'block', 'complete', 'cancel']);
const ACTION_LABELS = Object.freeze({
  start: '开始进行',
  block: '暂时搁置',
  complete: '完成任务',
  cancel: '取消任务',
});
const STATUS_LABELS = Object.freeze({
  open: '待开始',
  in_progress: '进行中',
  blocked: '暂时搁置',
  completed: '已完成',
  cancelled: '已取消',
  archived: '已归档',
  unknown: '状态未知',
});
const PRIORITY_LABELS = Object.freeze({ low: '舒缓', normal: '平常', high: '优先' });
const DUE_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
});

function taskNode(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function button(label, action, className = '') {
  const element = taskNode('button', className, label);
  element.type = 'button';
  if (action) element.dataset.action = action;
  return element;
}

function selectedTask(tasksState) {
  const index = tasksState?.selectedIndex;
  return Number.isInteger(index) ? tasksState.items?.[index] ?? null : null;
}

function formatTaskDue(value) {
  if (!isISOInstant(value)) return '未设时间';
  return DUE_FORMATTER.format(new Date(value));
}

function setVisible(node, visible) {
  if (node) node.hidden = !visible;
}

function setTaskSubview(dom, activeView) {
  const list = activeView === 'tasks';
  const detail = activeView === 'task-detail';
  const form = activeView === 'task-create' || activeView === 'task-edit';
  setVisible(dom.panel, TASK_VIEWS.has(activeView));
  setVisible(dom.list, list);
  setVisible(dom.listState, list);
  setVisible(dom.create, list);
  setVisible(dom.form, form);
  setVisible(dom.error, detail || form);
  for (const node of [
    dom.detail, dom.stepList, dom.stepForm, dom.statusActions, dom.archive, dom.confirmation,
  ]) setVisible(node, detail);
}

function renderTaskList(dom, tasksState) {
  const items = Array.isArray(tasksState?.items) ? tasksState.items : [];
  const stateNodes = [];
  if (tasksState?.status === 'loading') stateNodes.push(taskNode('p', '', '任务正在靠近……'));
  if (tasksState?.status === 'refreshing') stateNodes.push(taskNode('p', '', '正在轻轻更新……'));
  if (tasksState?.status === 'error') {
    stateNodes.push(taskNode('p', '', tasksState.error?.message || '任务暂时没有展开。'));
    stateNodes.push(button('再试一次', 'retry', 'today-secondary-button'));
  }
  if (tasksState?.status === 'ready' && items.length === 0) {
    stateNodes.push(taskNode('p', '', '这里还没有任务，先写下一件想照看的事。'));
  }
  dom.listState.replaceChildren(...stateNodes);
  dom.listState.hidden = stateNodes.length === 0;

  const entries = items.map((item, index) => {
    const row = taskNode('li', 'resource-list-item');
    const entry = button('', null, 'resource-list-entry');
    entry.dataset.itemIndex = String(index);
    entry.append(
      taskNode('span', 'resource-list-title', item.title),
      taskNode(
        'span',
        'resource-list-meta',
        `${STATUS_LABELS[item.status] || STATUS_LABELS.unknown} · ${PRIORITY_LABELS[item.priority] || PRIORITY_LABELS.normal}`,
      ),
    );
    row.append(entry);
    return row;
  });
  dom.list.replaceChildren(...entries);
}

function renderTaskDetail(dom, tasksState) {
  const item = selectedTask(tasksState);
  if (!item) {
    dom.detail.replaceChildren(taskNode('p', '', '没有找到这项任务。'));
    dom.stepList.replaceChildren();
    dom.statusActions.replaceChildren();
    setVisible(dom.archive, false);
    setVisible(dom.confirmation, false);
    return;
  }

  const due = formatTaskDue(item.dueAt);
  dom.detail.replaceChildren(
    taskNode('p', 'resource-kicker', STATUS_LABELS[item.status] || STATUS_LABELS.unknown),
    taskNode('h3', 'resource-detail-title', item.title),
    taskNode('p', 'resource-detail-description', item.description || '没有补充描述。'),
    taskNode('p', 'resource-detail-meta', `${due} · ${PRIORITY_LABELS[item.priority] || PRIORITY_LABELS.normal}`),
  );

  const writes = new Map((tasksState.stepWrites || []).map((entry) => [entry.index, entry]));
  dom.stepList.replaceChildren(...item.steps.map((step, index) => {
    const row = taskNode('li', 'task-step-item');
    const write = writes.get(index);
    const toggle = button(step.title, null, 'task-step-toggle');
    toggle.dataset.stepIndex = String(index);
    toggle.setAttribute('aria-pressed', String(step.status === 'completed'));
    toggle.disabled = write?.status === 'pending';
    row.append(toggle);
    if (write?.status === 'error') {
      row.append(taskNode('p', 'resource-inline-error', write.error?.message || '这一步暂时没有更新。'));
    }
    return row;
  }));

  const pending = tasksState.action?.status === 'pending';
  const actions = getTaskActions(item.status);
  const actionButtons = [];
  if (!['archived', 'unknown'].includes(item.status)) {
    const edit = button('编辑任务', 'edit', 'today-secondary-button');
    edit.disabled = pending;
    actionButtons.push(edit);
  }
  for (const action of actions.filter((name) => TRANSITIONS.has(name))) {
    const preferredAction = ['open', 'blocked'].includes(item.status) ? 'start' : 'complete';
    const transition = button(
      ACTION_LABELS[action],
      action,
      action === preferredAction ? 'life-flow-primary-action' : 'today-secondary-button',
    );
    transition.disabled = pending;
    actionButtons.push(transition);
  }
  dom.statusActions.replaceChildren(...actionButtons);
  setVisible(dom.archive, actions.includes('archive'));
  dom.archive.disabled = pending;
  setVisible(dom.confirmation, tasksState.action?.confirmingArchive === true);

  dom.stepTitle.value = tasksState.stepDraft || '';
  const addWrite = writes.get(-1);
  dom.stepTitle.readOnly = addWrite?.status === 'pending';
  const addButton = dom.stepForm.querySelector('button[type="submit"]');
  if (addButton) addButton.disabled = addWrite?.status === 'pending';
  const error = tasksState.action?.error || (addWrite?.status === 'error' ? addWrite.error : null);
  dom.error.textContent = error?.message || '';
  dom.error.hidden = !error;
}

function renderTaskForm(dom, tasksState, activeView) {
  const editor = tasksState.editor;
  const draft = editor?.draft || {};
  const pending = editor?.status === 'pending';
  dom.title.value = draft.title || '';
  dom.description.value = draft.description || '';
  dom.dueAt.value = formatISOToLocalTimed(draft.dueAt)
    || (typeof draft.dueAt === 'string' ? draft.dueAt : '');
  dom.priority.value = draft.priority || 'normal';
  dom.title.readOnly = pending;
  dom.description.readOnly = pending;
  dom.dueAt.readOnly = pending;
  dom.priority.disabled = pending;
  dom.submit.disabled = pending;
  dom.cancelEdit.disabled = pending;
  dom.submit.textContent = activeView === 'task-create' ? '创建任务' : '保存修改';
  dom.error.textContent = editor?.error?.message || '';
  dom.error.hidden = !editor?.error;
}

function eventIndex(value) {
  return /^\d+$/.test(value || '') ? Number(value) : null;
}

export function createTaskView(dom, { dispatch, announce = () => {} }) {
  const emit = (event) => dispatch(Object.freeze(event));
  let lastState = null;

  function handleSubmit(event) {
    if (event.target !== dom.form && event.target !== dom.stepForm) return;
    event.preventDefault();
    emit({ type: event.target === dom.form ? 'SUBMIT' : 'STEP_ADD' });
  }

  function handleInput(event) {
    const target = event.target;
    if (target === dom.stepTitle) emit({ type: 'STEP_FIELD', value: target.value });
    else if (target === dom.title) emit({ type: 'FIELD', field: 'title', value: target.value });
    else if (target === dom.description) {
      emit({ type: 'FIELD', field: 'description', value: target.value });
    } else if (target === dom.dueAt) emit({ type: 'FIELD', field: 'dueAt', value: target.value });
  }

  function handleChange(event) {
    if (event.target === dom.priority) {
      emit({ type: 'FIELD', field: 'priority', value: event.target.value });
    }
  }

  function handleClick(event) {
    const target = event.target?.closest?.('button');
    if (!target || !dom.panel.contains(target) || target.disabled) return;
    if (target === dom.back) emit({ type: 'BACK' });
    else if (target === dom.create) emit({ type: 'CREATE' });
    else if (target === dom.cancelEdit) emit({ type: 'CANCEL_EDIT' });
    else if (target === dom.archive) emit({ type: 'ARCHIVE_INTENT' });
    else if (target.dataset.action === 'retry') emit({ type: 'RETRY_LOAD' });
    else if (target.dataset.action === 'edit') emit({ type: 'EDIT' });
    else if (target.dataset.action === 'archive-confirm') emit({ type: 'ARCHIVE_CONFIRM' });
    else if (target.dataset.action === 'archive-cancel') emit({ type: 'ARCHIVE_CANCEL' });
    else if (TRANSITIONS.has(target.dataset.action)) {
      emit({ type: 'TRANSITION', action: target.dataset.action });
    } else {
      const itemIndex = eventIndex(target.dataset.itemIndex);
      const stepIndex = eventIndex(target.dataset.stepIndex);
      if (itemIndex !== null) emit({ type: 'SELECT', index: itemIndex });
      else if (stepIndex !== null) emit({ type: 'STEP_TOGGLE', index: stepIndex });
    }
  }

  dom.panel.addEventListener('click', handleClick);
  dom.panel.addEventListener('input', handleInput);
  dom.panel.addEventListener('change', handleChange);
  dom.panel.addEventListener('submit', handleSubmit);

  return Object.freeze({
    render(tasksState, activeView) {
      lastState = tasksState;
      setTaskSubview(dom, activeView);
      if (activeView === 'tasks') renderTaskList(dom, tasksState);
      else if (activeView === 'task-detail') renderTaskDetail(dom, tasksState);
      else if (activeView === 'task-create' || activeView === 'task-edit') {
        renderTaskForm(dom, tasksState, activeView);
      }
    },
    focusEntry(activeView) {
      const selectedEntry = Number.isInteger(lastState?.selectedIndex)
        ? dom.list.querySelector(`[data-item-index="${lastState.selectedIndex}"]`)
        : null;
      const target = activeView === 'tasks'
        ? selectedEntry || dom.create
        : activeView === 'task-detail'
          ? dom.back
          : activeView === 'task-create' || activeView === 'task-edit' ? dom.title : null;
      requestAnimationFrame(() => {
        if (target && !target.hidden && !target.disabled) target.focus({ preventScroll: true });
        else if (TASK_VIEWS.has(activeView)) announce('当前任务视图已经打开。');
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
