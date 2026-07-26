export const ALLOWED_ACTIONS = Object.freeze([
  'create_task',
  'complete_task',
  'start_focus_session',
  'checkin_routine',
  'draft_diary',
]);

const ALLOWED_SET = new Set(ALLOWED_ACTIONS);
const TRANSITIONS = {
  proposal: { PREVIEW: 'previewing' },
  previewing: {
    READY: 'preview_ready',
    ERROR: 'preview_error',
    CANCEL: 'cancelled',
  },
  preview_error: { RETRY: 'previewing', CANCEL: 'cancelled' },
  preview_ready: { CONFIRM: 'confirming', CANCEL: 'cancelled' },
  confirming: { SUCCESS: 'success', ERROR: 'confirm_error' },
  confirm_error: { RETRY: 'confirming', DISMISS: 'cancelled' },
};

/** @param {unknown} action */
export function isAllowedAction(action) {
  return typeof action === 'string' && ALLOWED_SET.has(action);
}

/**
 * Returns the next safe state, or null for an illegal transition.
 * @param {string} currentState
 * @param {string} event
 */
export function transitionActionState(currentState, event) {
  const branch = TRANSITIONS[currentState];
  if (!branch) return null;
  return Object.hasOwn(branch, event) ? branch[event] : null;
}

function requiredTitle(value) {
  return normalizeBoundedText(value, 160, { required: true });
}

/**
 * Normalizes an already-gated proposal before any network request.
 * Unknown fields are dropped and opaque lookup keys remain memory-only.
 * @param {unknown} value
 * @returns {{action:string,payload:object}|null}
 */
export function normalizeActionProposal(value) {
  if (!isPlainObject(value) || !isAllowedAction(value.action) || !isPlainObject(value.payload)) {
    return null;
  }
  const payload = {};
  if (value.action === 'create_task') {
    const title = requiredTitle(value.payload.title);
    if (!title) return null;
    payload.title = title;
    if (['low', 'normal', 'high'].includes(value.payload.priority)) {
      payload.priority = value.payload.priority;
    }
    if (value.payload.due_at !== undefined && value.payload.due_at !== null
      && value.payload.due_at !== '') {
      if (!isISOInstant(value.payload.due_at)) return null;
      payload.due_at = value.payload.due_at;
    }
  } else if (value.action === 'complete_task') {
    const key = normalizeOpaqueKey(value.payload.task_id);
    if (!key) return null;
    payload.task_id = key;
  } else if (value.action === 'start_focus_session') {
    const title = requiredTitle(value.payload.title);
    if (!title) return null;
    payload.title = title;
  } else if (value.action === 'checkin_routine') {
    const key = normalizeOpaqueKey(value.payload.routine_id);
    if (!key) return null;
    payload.routine_id = key;
    const note = normalizeBoundedText(value.payload.note, 1000, {
      preserveOuterWhitespace: true,
    });
    if (note) payload.note = note;
  } else if (value.payload.date !== undefined && value.payload.date !== '') {
    if (typeof value.payload.date !== 'string' || !parseLocalAllDayToISO(value.payload.date)) {
      return null;
    }
    payload.date = value.payload.date;
  }
  return deepCloneAndFreeze({ action: value.action, payload });
}

export function createActionProposalState() {
  return {
    status: 'idle',
    proposal: null,
    preview: null,
    result: null,
    error: null,
  };
}

const ERROR_MESSAGES = Object.freeze({
  offline: '连接暂时远了一些，这枚光签还没有展开。',
  timeout: '这次等待有些久，光签仍为你保留。',
  validation: '这项建议目前无法安全确认。',
  'not-found': '建议指向的内容已经不在这里。',
  server: '光签暂时没有落定，可以稍后再试。',
  cancelled: '',
  unknown: '光签暂时没有落定，可以稍后再试。',
});

export function safeActionError(error) {
  const kind = Object.hasOwn(ERROR_MESSAGES, error?.kind) ? error.kind : 'unknown';
  return Object.freeze({
    kind,
    message: ERROR_MESSAGES[kind],
    retryable: !['validation', 'not-found', 'cancelled'].includes(kind),
  });
}
import { isISOInstant, parseLocalAllDayToISO } from '../../shared/time.js';
import {
  deepCloneAndFreeze,
  isPlainObject,
  normalizeBoundedText,
  normalizeOpaqueKey,
} from '../../shared/validation.js';
