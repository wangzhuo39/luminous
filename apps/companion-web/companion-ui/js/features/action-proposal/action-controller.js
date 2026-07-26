import { createOperationGate } from '../../shared/operation.js';
import {
  createActionProposalState,
  normalizeActionProposal,
  safeActionError,
  transitionActionState,
} from './action-state.js';

function snapshotsMatch(proposal, preview) {
  return preview?.action === proposal?.action
    && JSON.stringify(preview?.requestSnapshot) === JSON.stringify(proposal?.payload);
}

function targetIsAvailable(proposal, lookup) {
  if (proposal?.action === 'complete_task') {
    return Array.isArray(lookup?.tasks)
      && lookup.tasks.some((item) => item?.key === proposal.payload.task_id);
  }
  if (proposal?.action === 'checkin_routine') {
    return Array.isArray(lookup?.routines)
      && lookup.routines.some((item) => item?.key === proposal.payload.routine_id);
  }
  return true;
}

export function initActionProposal({
  dataSource,
  getLookup = () => ({}),
  commitResult = () => true,
  onStateChange = () => {},
  announce = () => {},
  dismissDelay = 1600,
}) {
  const state = createActionProposalState();
  const previewGate = createOperationGate('action-preview');
  const confirmGate = createOperationGate('action-confirm');
  let previewOperation = null;
  let confirmOperation = null;
  let dismissTimer = null;
  let destroyed = false;

  const notify = () => { if (!destroyed) onStateChange(); };

  function clearDismissTimer() {
    if (dismissTimer !== null) clearTimeout(dismissTimer);
    dismissTimer = null;
  }

  function scheduleDismiss() {
    clearDismissTimer();
    if (!Number.isFinite(dismissDelay) || dismissDelay < 0) return;
    dismissTimer = setTimeout(() => {
      dismissTimer = null;
      if (!destroyed && (state.status === 'success' || state.status === 'cancelled')) {
        reset();
      }
    }, dismissDelay);
  }

  function reset() {
    if (state.status === 'previewing' || state.status === 'confirming') return false;
    clearDismissTimer();
    Object.assign(state, createActionProposalState());
    notify();
    return true;
  }

  async function preview() {
    if (destroyed || !state.proposal) return false;
    const event = state.status === 'proposal' ? 'PREVIEW'
      : state.status === 'preview_error' ? 'RETRY' : null;
    const next = event ? transitionActionState(state.status, event) : null;
    if (!next) return false;
    const lookup = getLookup();
    if (!targetIsAvailable(state.proposal, lookup)) {
      state.status = 'preview_error';
      state.error = safeActionError({ kind: 'not-found' });
      announce(state.error.message);
      notify();
      return false;
    }
    const token = previewGate.begin();
    if (!token) return false;
    const controller = new AbortController();
    previewOperation = { token, controller };
    state.status = next;
    state.error = null;
    notify();
    try {
      const result = await dataSource.previewAction({
        proposal: state.proposal,
        lookup,
        signal: controller.signal,
      });
      if (destroyed || !previewGate.isCurrent(token)) return false;
      if (!snapshotsMatch(state.proposal, result)) {
        throw { kind: 'validation', retryable: false };
      }
      previewGate.finish(token);
      state.preview = result;
      state.status = transitionActionState('previewing', 'READY');
      state.error = null;
      announce('光签已经展开，请确认是否让它发生。');
      notify();
      return true;
    } catch (error) {
      if (destroyed || !previewGate.isCurrent(token)) return false;
      previewGate.finish(token);
      if (error?.kind === 'cancelled') return false;
      state.status = transitionActionState('previewing', 'ERROR');
      state.error = safeActionError(error);
      announce(state.error.message);
      notify();
      return false;
    } finally {
      if (previewOperation?.token === token) previewOperation = null;
    }
  }

  function injectProposal(value) {
    if (destroyed || state.status !== 'idle') return Promise.resolve(false);
    const proposal = normalizeActionProposal(value);
    if (!proposal) return Promise.resolve(false);
    state.status = 'proposal';
    state.proposal = proposal;
    state.preview = null;
    state.result = null;
    state.error = null;
    notify();
    return preview();
  }

  async function confirm() {
    if (destroyed || !state.preview) return false;
    const event = state.status === 'preview_ready' ? 'CONFIRM'
      : state.status === 'confirm_error' ? 'RETRY' : null;
    const next = event ? transitionActionState(state.status, event) : null;
    if (!next) return false;
    const token = confirmGate.begin();
    if (!token) return false;
    const controller = new AbortController();
    confirmOperation = { token, controller };
    state.status = next;
    state.error = null;
    notify();
    try {
      const result = await dataSource.confirmAction({ preview: state.preview, signal: controller.signal });
      if (destroyed || !confirmGate.isCurrent(token)) return false;
      if (commitResult(state.preview.action, state.preview.requestSnapshot, result) !== true) {
        throw { kind: 'server', retryable: true };
      }
      confirmGate.finish(token);
      state.result = result;
      state.status = transitionActionState('confirming', 'SUCCESS');
      announce('这项行动已经落定。');
      notify();
      scheduleDismiss();
      return true;
    } catch (error) {
      if (destroyed || !confirmGate.isCurrent(token)) return false;
      confirmGate.finish(token);
      if (error?.kind === 'cancelled') return false;
      state.status = transitionActionState('confirming', 'ERROR');
      state.error = safeActionError(error);
      announce(state.error.message);
      notify();
      return false;
    } finally {
      if (confirmOperation?.token === token) confirmOperation = null;
    }
  }

  function cancel() {
    if (destroyed) return false;
    const next = state.status === 'preview_ready'
      ? transitionActionState('preview_ready', 'CANCEL')
      : state.status === 'preview_error'
        ? transitionActionState('preview_error', 'CANCEL')
        : state.status === 'confirm_error'
          ? transitionActionState('confirm_error', 'DISMISS')
          : null;
    if (!next) return false;
    state.status = next;
    state.error = null;
    announce('这项建议已经轻轻收起。');
    notify();
    scheduleDismiss();
    return true;
  }

  return Object.freeze({
    injectProposal,
    retryPreview: preview,
    confirm,
    retryConfirm: confirm,
    cancel,
    reset,
    getState: () => state,
    destroy() {
      destroyed = true;
      clearDismissTimer();
      for (const [gate, operation] of [
        [previewGate, previewOperation], [confirmGate, confirmOperation],
      ]) {
        operation?.controller.abort();
        if (operation && gate.isCurrent(operation.token)) gate.cancel(operation.token);
      }
      previewOperation = null;
      confirmOperation = null;
    },
  });
}
