import test from 'node:test';
import assert from 'node:assert/strict';

import {
  beginResourceLoad,
  beginResourceWrite,
  completeResourceLoad,
  completeResourceWrite,
  failResourceWrite,
  getState,
  initializeState,
  openResourceEditor,
  selectResourceItem,
  setResourceConfirmation,
  updateResourceDraft,
} from '../../apps/companion-web/companion-ui/js/app-state.js';
import { initLifeFlow } from '../../apps/companion-web/companion-ui/js/features/life-flow/life-flow-controller.js';

const flush = () => new Promise((resolve) => setImmediate(resolve));

const diary = (overrides = {}) => ({
  key: 'diary-safe-1',
  date: '2026-07-26',
  title: '今天的一束光',
  body: '下午的光线很安静。',
  status: 'saved',
  updatedAt: '2026-07-26T08:00:00Z',
  ...overrides,
});

function load(items) {
  assert.equal(beginResourceLoad('diaries'), true);
  assert.equal(completeResourceLoad('diaries', items), true);
}

test('Diary AppState filters deleted, sorts dates and drops unsafe fields', () => {
  initializeState(null);
  load([
    diary({ key: 'older', date: '2026-07-24', diagnosis: 'drop' }),
    diary({ key: 'unknown-date', date: null, metadata: { private: true } }),
    diary({ key: 'deleted', status: 'deleted' }),
    diary({ key: 'newer', date: '2026-07-27' }),
  ]);
  const items = getState().lifeFlow.diaries.items;
  assert.deepEqual(items.map((item) => item.key), ['newer', 'older', 'unknown-date']);
  assert.doesNotMatch(JSON.stringify(items), /diagnosis|metadata|private|deleted/);
  assert.equal(items[2].date, null);
});

test('Diary generated draft becomes an edit and saving never creates a second item', () => {
  initializeState(null);
  load([]);
  assert.deepEqual(beginResourceWrite('diaries', 'draft'), {});
  assert.equal(completeResourceWrite('diaries', diary({
    key: 'generated-key', title: '今日回顾', body: '- 安静地休息', status: 'draft',
  })), true);
  let state = getState().lifeFlow;
  assert.equal(state.view, 'diary-edit');
  assert.equal(state.diaries.items.length, 1);
  assert.equal(state.diaries.selectedIndex, 0);
  assert.equal(state.diaries.editor.mode, 'edit');
  assert.equal(updateResourceDraft('diaries', 'body', '  保留开头空白\n新的正文  '), true);
  const snapshot = beginResourceWrite('diaries', 'edit');
  assert.equal(snapshot.body, '  保留开头空白\n新的正文  ');
  assert.equal(completeResourceWrite('diaries', diary({
    key: 'generated-key', title: '今日回顾', body: snapshot.body, status: 'saved',
  })), true);
  state = getState().lifeFlow;
  assert.equal(state.view, 'diary-detail');
  assert.equal(state.diaries.items.length, 1);
  assert.equal(state.diaries.items[0].status, 'saved');
});

test('Diary manual draft restores exactly and remove waits for deleted response', () => {
  initializeState(null);
  load([diary()]);
  assert.equal(openResourceEditor('diaries', 'create'), true);
  updateResourceDraft('diaries', 'title', '  不丢标题空白  ');
  updateResourceDraft('diaries', 'body', '  第一行\n\t第二行  ');
  assert.ok(beginResourceWrite('diaries', 'create'));
  assert.equal(updateResourceDraft('diaries', 'body', '不能覆盖'), false);
  assert.equal(failResourceWrite('diaries', { kind: 'offline', raw: 'drop' }), true);
  assert.deepEqual(getState().lifeFlow.diaries.editor.draft, {
    date: null,
    title: '  不丢标题空白  ',
    body: '  第一行\n\t第二行  ',
    status: 'saved',
  });

  assert.equal(selectResourceItem('diaries', 'diary-safe-1'), true);
  assert.equal(beginResourceWrite('diaries', 'remove'), null);
  assert.equal(setResourceConfirmation('diaries', 'remove', true), true);
  assert.deepEqual(beginResourceWrite('diaries', 'remove'), {});
  assert.equal(completeResourceWrite('diaries', diary({ status: 'saved' })), false);
  assert.equal(getState().lifeFlow.diaries.items.length, 1);
  assert.equal(failResourceWrite('diaries', { kind: 'server' }), true);
  assert.deepEqual(beginResourceWrite('diaries', 'remove'), {});
  assert.equal(completeResourceWrite('diaries', diary({ status: 'deleted' })), true);
  assert.equal(getState().lifeFlow.view, 'diaries');
  assert.deepEqual(getState().lifeFlow.diaries.items, []);
});

function setupController() {
  initializeState(null);
  const methodNames = [
    'loadToday', 'loadTimeline', 'loadTasks', 'createTask', 'updateTask',
    'addTaskStep', 'updateTaskStep', 'transitionTask', 'archiveTask',
    'loadRoutines', 'createRoutine', 'updateRoutine', 'checkinRoutine', 'deactivateRoutine',
    'loadActivities', 'createActivity', 'transitionActivity',
    'loadDiaryEntries', 'createDiaryEntry', 'draftDiaryEntry', 'updateDiaryEntry',
    'removeDiaryEntry',
  ];
  const pending = Object.fromEntries(methodNames.map((name) => [name, []]));
  const dataSource = Object.fromEntries(methodNames.map((name) => [name, (params = {}) => (
    new Promise((resolve, reject) => {
      pending[name].push({ params, resolve, reject });
      params.signal?.addEventListener(
        'abort', () => reject({ kind: 'cancelled', retryable: false }), { once: true },
      );
    })
  )]));
  const eventTarget = new EventTarget();
  const controller = initLifeFlow({ dialog: { open: true } }, {
    dataSource,
    eventTarget,
    announce: () => {},
    onStateChange: () => {},
    isOnline: () => true,
    localDate: () => '2026-07-26',
  });
  return { controller, pending, eventTarget };
}

test('Diary controller sends exact manual POST and restores invalid drafts without a request', async (t) => {
  const { controller, pending } = setupController();
  t.after(() => controller.destroy());
  controller.openDiaries();
  controller.openDiaries();
  assert.equal(pending.loadDiaryEntries.length, 1);
  assert.deepEqual(
    { ...pending.loadDiaryEntries[0].params, signal: undefined },
    { limit: 100, signal: undefined },
  );
  pending.loadDiaryEntries[0].resolve([]);
  await flush();

  controller.handleDiaryEvent({ type: 'CREATE' });
  controller.handleDiaryEvent({ type: 'FIELD', field: 'title', value: '只有标题' });
  assert.equal(await controller.handleDiaryEvent({ type: 'SUBMIT' }), false);
  assert.equal(pending.createDiaryEntry.length, 0);
  assert.equal(getState().lifeFlow.diaries.editor.draft.title, '只有标题');

  controller.handleDiaryEvent({ type: 'FIELD', field: 'body', value: '  正文保留空白  ' });
  const creating = controller.handleDiaryEvent({ type: 'SUBMIT' });
  assert.deepEqual(pending.createDiaryEntry[0].params.input, {
    date: '2026-07-26', title: '只有标题', body: '  正文保留空白  ', status: 'saved',
  });
  assert.equal(await controller.handleDiaryEvent({ type: 'SUBMIT' }), false);
  pending.createDiaryEntry[0].resolve(diary({ title: '只有标题', body: '  正文保留空白  ' }));
  assert.equal(await creating, true);
  assert.equal(getState().lifeFlow.view, 'diary-detail');
});

test('generated Diary is persisted once, then saved only through PATCH and removed conservatively', async (t) => {
  const { controller, pending } = setupController();
  t.after(() => controller.destroy());
  controller.openDiaries();
  pending.loadDiaryEntries[0].resolve([]);
  await flush();

  const generating = controller.handleDiaryEvent({ type: 'GENERATE' });
  assert.deepEqual(
    { ...pending.draftDiaryEntry[0].params, signal: undefined },
    { date: '2026-07-26', signal: undefined },
  );
  pending.draftDiaryEntry[0].resolve(diary({
    key: 'generated-key', title: '今日回顾', body: '- 一件小事', status: 'draft',
  }));
  assert.equal(await generating, true);
  assert.equal(getState().lifeFlow.view, 'diary-edit');

  controller.handleDiaryEvent({ type: 'FIELD', field: 'body', value: '- 一件小事\n- 一束光' });
  const saving = controller.handleDiaryEvent({ type: 'SUBMIT' });
  assert.equal(pending.createDiaryEntry.length, 0);
  assert.equal(pending.updateDiaryEntry.length, 1);
  assert.equal(pending.updateDiaryEntry[0].params.key, 'generated-key');
  assert.deepEqual(pending.updateDiaryEntry[0].params.changes, {
    date: '2026-07-26', title: '今日回顾', body: '- 一件小事\n- 一束光', status: 'saved',
  });
  pending.updateDiaryEntry[0].resolve(diary({
    key: 'generated-key', title: '今日回顾', body: '- 一件小事\n- 一束光', status: 'saved',
  }));
  assert.equal(await saving, true);

  controller.handleDiaryEvent({ type: 'REMOVE_INTENT' });
  const removing = controller.handleDiaryEvent({ type: 'REMOVE_CONFIRM' });
  assert.equal(pending.removeDiaryEntry[0].params.key, 'generated-key');
  assert.equal(getState().lifeFlow.diaries.items.length, 1);
  pending.removeDiaryEntry[0].resolve(diary({ key: 'generated-key', status: 'deleted' }));
  assert.equal(await removing, true);
  assert.equal(getState().lifeFlow.diaries.items.length, 0);
  assert.equal(getState().lifeFlow.view, 'diaries');
});
