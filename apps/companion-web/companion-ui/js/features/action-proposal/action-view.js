const ACTION_LABELS = Object.freeze({
  create_task: '留下一项任务',
  complete_task: '完成这项任务',
  start_focus_session: '开始一段专注',
  checkin_routine: '照看这项日常',
  draft_diary: '生成一页回顾',
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
  element.dataset.action = action;
  return element;
}

function renderSummary(dom, state) {
  const lines = Array.isArray(state.preview?.summaryLines) ? state.preview.summaryLines : [];
  dom.summary.replaceChildren(...lines.map((line) => node('li', 'action-summary-line', line)));
  dom.summary.hidden = lines.length === 0;
}

export function createActionView(dom, { dispatch, announce = () => {} }) {
  const emit = (event) => dispatch(Object.freeze(event));

  function handleClick(event) {
    const target = event.target?.closest?.('button[data-action]');
    if (!target || !dom.card.contains(target) || target.disabled) return;
    if (target.dataset.action === 'confirm') emit({ type: 'CONFIRM' });
    else if (target.dataset.action === 'cancel') emit({ type: 'CANCEL' });
    else if (target.dataset.action === 'retry-preview') emit({ type: 'RETRY_PREVIEW' });
    else if (target.dataset.action === 'retry-confirm') emit({ type: 'RETRY_CONFIRM' });
  }

  dom.card.addEventListener('click', handleClick);

  return Object.freeze({
    render(state) {
      const visible = state && state.status !== 'idle';
      dom.card.hidden = !visible;
      if (!visible) return;
      dom.card.dataset.actionStatus = state.status;
      const action = state.preview?.action || state.proposal?.action;
      dom.eyebrow.textContent = state.status === 'success' ? 'LIGHT SETTLED' : 'ACTION REFRACTION';
      dom.title.textContent = state.status === 'proposal' || state.status === 'previewing'
        ? '正在折一枚光签'
        : state.status === 'success' ? '这束光已经落定'
          : state.status === 'cancelled' ? '光签已经收起'
            : ACTION_LABELS[action] || '一项需要你确认的行动';
      renderSummary(dom, state);

      const pending = state.status === 'confirming';
      const previewError = state.status === 'preview_error';
      const confirmError = state.status === 'confirm_error';
      dom.status.textContent = state.status === 'previewing' || state.status === 'proposal'
        ? '正在把建议折成只包含必要信息的光签。'
        : pending ? '正在让这项行动发生，请不要重复确认。'
          : state.status === 'success' ? '已根据真实结果更新。'
            : state.status === 'cancelled' ? '没有发送确认请求。'
              : state.error?.message || '';

      const actions = [];
      if (state.status === 'preview_ready' || pending) {
        const cancel = button('婉拒', 'cancel', 'today-secondary-button');
        const confirm = button(pending ? '正在落定……' : '确认让它发生', 'confirm', 'life-flow-primary-action');
        cancel.disabled = pending;
        confirm.disabled = pending;
        actions.push(cancel, confirm);
      } else if (previewError) {
        actions.push(
          button('忽略这项建议', 'cancel', 'today-secondary-button'),
          button('重新展开', 'retry-preview', 'life-flow-primary-action'),
        );
      } else if (confirmError) {
        actions.push(
          button('收起光签', 'cancel', 'today-secondary-button'),
          button('用同一内容重试', 'retry-confirm', 'life-flow-primary-action'),
        );
      }
      dom.actions.replaceChildren(...actions);
      dom.actions.hidden = actions.length === 0;
      dom.card.setAttribute('aria-busy', String(
        state.status === 'previewing' || state.status === 'confirming',
      ));
    },
    focus() {
      const target = dom.actions.querySelector('.life-flow-primary-action') || dom.card;
      requestAnimationFrame(() => {
        if (target && !target.hidden) target.focus({ preventScroll: true });
        else announce('光签已经展开。');
      });
    },
    destroy() {
      dom.card.removeEventListener('click', handleClick);
    },
  });
}
