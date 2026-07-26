import test from 'node:test';
import assert from 'node:assert/strict';

import {
  beginResourceLoad,
  commitConfirmedActionResult,
  completeResourceLoad,
  getState,
  initializeState,
} from '../../apps/companion-web/companion-ui/js/app-state.js';
import { initActionProposal } from '../../apps/companion-web/companion-ui/js/features/action-proposal/action-controller.js';
import { normalizeActionProposal } from '../../apps/companion-web/companion-ui/js/features/action-proposal/action-state.js';

const flush = () => new Promise((resolve) => setImmediate(resolve));

const task = (overrides = {}) => ({
  key: 'task-safe-1', title: '给植物浇水', description: null, status: 'open',
  dueAt: null, priority: 'normal', steps: [], ...overrides,
});
const routine = (overrides = {}) => ({
  key: 'routine-safe-1', title: '晚间伸展', schedule: 'daily', active: true,
  reminderPolicy: 'none', checkinStatus: 'none', ...overrides,
});
const diary = (overrides = {}) => ({
  key: 'diary-safe-1', date: '2026-07-26', title: '今日回顾', body: '- 一束光',
  status: 'draft', updatedAt: '2026-07-26T08:00:00Z', ...overrides,
});

test('proposal normalization allowlists all five actions and drops unsafe fields', () => {
  assert.deepEqual(normalizeActionProposal({
    action: 'create_task',
    payload: {
      title: '  给植物浇水  ', priority: 'normal', due_at: '2026-07-27T09:00:00Z',
      metadata: { private: true }, task_id: 'must-drop',
    },
    internal: 'drop',
  }), {
    action: 'create_task',
    payload: { title: '给植物浇水', priority: 'normal', due_at: '2026-07-27T09:00:00Z' },
  });
  assert.deepEqual(normalizeActionProposal({
    action: 'start_focus_session', payload: { title: '专注片刻', kind: 'reflection' },
  }), { action: 'start_focus_session', payload: { title: '专注片刻' } });
  assert.deepEqual(normalizeActionProposal({
    action: 'checkin_routine', payload: { routine_id: 'routine-safe-1', note: '  轻轻完成  ' },
  }), {
    action: 'checkin_routine',
    payload: { routine_id: 'routine-safe-1', note: '  轻轻完成  ' },
  });
  assert.deepEqual(normalizeActionProposal({
    action: 'draft_diary', payload: { date: '2026-07-26', title: 'must-drop' },
  }), { action: 'draft_diary', payload: { date: '2026-07-26' } });
  assert.equal(normalizeActionProposal({ action: 'delete_task', payload: {} }), null);
  assert.equal(normalizeActionProposal({
    action: 'complete_task', payload: { task_id: '' },
  }), null);
});

function setup({ lookup = { tasks: [task()], routines: [routine()] }, commit = () => true } = {}) {
  const previewCalls = [];
  const confirmCalls = [];
  const dataSource = {
    previewAction(params) {
      return new Promise((resolve, reject) => previewCalls.push({ params, resolve, reject }));
    },
    confirmAction(params) {
      return new Promise((resolve, reject) => confirmCalls.push({ params, resolve, reject }));
    },
  };
  const controller = initActionProposal({
    dataSource,
    getLookup: () => lookup,
    commitResult: commit,
    dismissDelay: -1,
  });
  return { controller, previewCalls, confirmCalls };
}

test('preview and confirm use one frozen snapshot and reject duplicate submits', async (t) => {
  const committed = [];
  const { controller, previewCalls, confirmCalls } = setup({
    commit: (...args) => { committed.push(args); return true; },
  });
  t.after(() => controller.destroy());
  const proposal = {
    action: 'create_task', payload: { title: '给植物浇水', priority: 'normal' },
  };
  const previewing = controller.injectProposal(proposal);
  assert.equal(controller.getState().status, 'previewing');
  assert.equal(previewCalls.length, 1);
  assert.notEqual(previewCalls[0].params.proposal, proposal);
  const preview = Object.freeze({
    previewKey: 'opaque-preview',
    action: 'create_task',
    requestSnapshot: Object.freeze({ title: '给植物浇水', priority: 'normal' }),
    summaryLines: Object.freeze(['创建任务：给植物浇水', '优先级：普通']),
  });
  previewCalls[0].resolve(preview);
  assert.equal(await previewing, true);
  assert.equal(controller.getState().status, 'preview_ready');

  const confirming = controller.confirm();
  assert.equal(await controller.confirm(), false);
  assert.equal(confirmCalls.length, 1);
  assert.equal(confirmCalls[0].params.preview, preview);
  confirmCalls[0].resolve(task());
  assert.equal(await confirming, true);
  assert.equal(controller.getState().status, 'success');
  assert.equal(committed.length, 1);
  assert.equal(committed[0][1], preview.requestSnapshot);
});

test('missing task mapping refuses preview without a network request or confirm path', async (t) => {
  const { controller, previewCalls, confirmCalls } = setup({ lookup: { tasks: [], routines: [] } });
  t.after(() => controller.destroy());
  assert.equal(await controller.injectProposal({
    action: 'complete_task', payload: { task_id: 'opaque-secret-task' },
  }), false);
  assert.equal(controller.getState().status, 'preview_error');
  assert.equal(controller.getState().error.kind, 'not-found');
  assert.equal(previewCalls.length, 0);
  assert.equal(await controller.confirm(), false);
  assert.equal(confirmCalls.length, 0);
});

test('confirm retry preserves the byte-equivalent preview snapshot', async (t) => {
  const { controller, previewCalls, confirmCalls } = setup();
  t.after(() => controller.destroy());
  const previewing = controller.injectProposal({
    action: 'start_focus_session', payload: { title: '安静专注' },
  });
  const preview = Object.freeze({
    previewKey: 'opaque-preview-focus', action: 'start_focus_session',
    requestSnapshot: Object.freeze({ title: '安静专注' }),
    summaryLines: Object.freeze(['开始专注：安静专注']),
  });
  previewCalls[0].resolve(preview);
  await previewing;
  const first = controller.confirm();
  confirmCalls[0].reject({ kind: 'server' });
  assert.equal(await first, false);
  assert.equal(controller.getState().status, 'confirm_error');
  const retry = controller.retryConfirm();
  assert.equal(confirmCalls[1].params.preview, preview);
  confirmCalls[1].resolve({
    key: 'activity-safe-1', kind: 'focus', title: '安静专注', status: 'active',
    startedAt: '2026-07-26T08:00:00Z', endedAt: null, summary: null,
  });
  assert.equal(await retry, true);
});

test('cancelled preview never confirms and confirmed draft diary enters persisted editor', async (t) => {
  const { controller, previewCalls, confirmCalls } = setup({ commit: commitConfirmedActionResult });
  t.after(() => controller.destroy());
  let previewing = controller.injectProposal({ action: 'draft_diary', payload: { date: '2026-07-26' } });
  let preview = Object.freeze({
    previewKey: 'preview-diary-cancel', action: 'draft_diary',
    requestSnapshot: Object.freeze({ date: '2026-07-26' }),
    summaryLines: Object.freeze(['为 2026-07-26 生成一份可编辑日记草稿']),
  });
  previewCalls[0].resolve(preview);
  await previewing;
  assert.equal(controller.cancel(), true);
  assert.equal(controller.getState().status, 'cancelled');
  assert.equal(confirmCalls.length, 0);
  assert.equal(controller.reset(), true);

  initializeState(null);
  previewing = controller.injectProposal({ action: 'draft_diary', payload: { date: '2026-07-26' } });
  preview = Object.freeze({
    previewKey: 'preview-diary-confirm', action: 'draft_diary',
    requestSnapshot: Object.freeze({ date: '2026-07-26' }),
    summaryLines: Object.freeze(['为 2026-07-26 生成一份可编辑日记草稿']),
  });
  previewCalls[1].resolve(preview);
  await previewing;
  const confirming = controller.confirm();
  confirmCalls[0].resolve(diary());
  assert.equal(await confirming, true);
  assert.equal(getState().activeSpace, 'today');
  assert.equal(getState().lifeFlow.view, 'diary-edit');
  assert.equal(getState().lifeFlow.diaries.editor.mode, 'edit');
  assert.equal(getState().lifeFlow.diaries.items[0].key, 'diary-safe-1');
});

test('confirmed task and routine results update only existing safe stores', () => {
  initializeState(null);
  beginResourceLoad('tasks');
  completeResourceLoad('tasks', [task()]);
  beginResourceLoad('routines');
  completeResourceLoad('routines', [routine()]);
  assert.equal(commitConfirmedActionResult(
    'complete_task', { task_id: 'task-safe-1' }, task({ status: 'completed' }),
  ), true);
  assert.equal(getState().lifeFlow.tasks.items[0].status, 'completed');
  assert.equal(commitConfirmedActionResult(
    'checkin_routine', { routine_id: 'routine-safe-1' },
    { key: 'checkin-safe-1', periodKey: '2026-07-26', status: 'completed' },
  ), true);
  assert.equal(getState().lifeFlow.routines.items[0].checkinStatus, 'completed');
  assert.equal(commitConfirmedActionResult(
    'complete_task', { task_id: 'wrong' }, task({ status: 'completed' }),
  ), false);
});
