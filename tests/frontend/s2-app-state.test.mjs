import assert from 'node:assert/strict';
import test from 'node:test';

import {
  beginChatSubmission,
  completeChatSubmission,
  completeInitialLoad,
  failChatSubmission,
  failInitialLoad,
  getState,
  initializeState,
  submitLocalConversation,
  updateDraft,
} from '../../apps/companion-web/companion-ui/js/app-state.js';

function viewModels(messageCount = 2) {
  return {
    scene: { caption: '静静地陪伴着你。', tone: 'calm' },
    conversation: {
      messages: Array.from({ length: messageCount }, (_, index) => ({
        id: `old-${index + 1}`,
        role: index % 2 === 0 ? 'user' : 'assistant',
        text: `旧消息 ${index + 1}`,
      })),
      localReply: { idPrefix: 'local-reply', text: '我在这里。' },
      sceneAfterLocalSend: { caption: '正专注地倾听你。', tone: 'warm' },
    },
    today: { date: '', summaryItems: [] },
    outbox: { arrivals: [], unreadCount: 0 },
    memoryPrivacy: { memoryPrompt: '', privacyCaption: '', boundaryStatus: '' },
  };
}

test('API mode blocks chat until a safe initial scene is ready', () => {
  initializeState(viewModels(), { runtimeMode: 'api' });
  updateDraft('今天有点累');
  assert.equal(getState().appStatus, 'loading');
  assert.equal(beginChatSubmission(), null);

  assert.equal(completeInitialLoad({ caption: '我在。', tone: 'warm', secret: 'drop me' }), true);
  const state = getState();
  assert.equal(state.appStatus, 'ready');
  assert.deepEqual(state.viewModels.scene, { caption: '我在。', tone: 'warm' });
  assert.doesNotMatch(JSON.stringify(state), /drop me/);
});

test('initial load stores only finite safe error descriptors', () => {
  initializeState(viewModels(), { runtimeMode: 'api' });
  failInitialLoad({
    kind: 'server',
    status: 500,
    retryable: true,
    message: 'raw backend secret',
    cause: { prompt: 'secret prompt' },
  });
  const state = getState();
  assert.equal(state.appStatus, 'offline');
  assert.deepEqual(state.appError, {
    kind: 'server',
    status: 500,
    message: '连接暂时不稳定。',
    retryable: true,
  });
  assert.doesNotMatch(JSON.stringify(state), /raw backend|secret prompt/);
});

test('submission is non-optimistic, immutable and duplicate-safe', () => {
  initializeState(viewModels(), { runtimeMode: 'api', initialDraft: '  请陪陪我  ' });
  completeInitialLoad({ caption: '我在。', tone: 'calm' });
  const before = getState().viewModels.conversation.messages;
  const payload = beginChatSubmission();

  assert.equal(payload.message, '请陪陪我');
  assert.equal(payload.draft, '  请陪陪我  ');
  assert.equal(Object.isFrozen(payload), true);
  assert.equal(getState().viewModels.conversation.messages.length, before.length);
  assert.equal(beginChatSubmission(), null);
  assert.equal(updateDraft('不应覆盖'), false);
  assert.equal(getState().conversation.draft, '  请陪陪我  ');
});

test('a direct voice submission keeps the text input draft empty', () => {
  initializeState(viewModels(), { runtimeMode: 'api' });
  completeInitialLoad({ caption: '我在。', tone: 'calm' });

  const payload = beginChatSubmission('语音转写文本');

  assert.equal(payload?.message, '语音转写文本');
  assert.equal(payload?.draft, '');
  assert.equal(getState().conversation.draft, '');
});

test('failed submission restores exact draft and discards unsafe error fields', () => {
  initializeState(viewModels(), { runtimeMode: 'api', initialDraft: '  原样草稿\n第二行  ' });
  completeInitialLoad({ caption: '我在。', tone: 'calm' });
  beginChatSubmission();
  failChatSubmission({
    kind: 'model-unavailable',
    status: 503,
    retryable: true,
    message: 'model raw secret',
    response: { role_thinking: 'secret' },
  });

  let state = getState();
  assert.equal(state.conversation.draft, '  原样草稿\n第二行  ');
  assert.equal(state.conversation.chatStatus, 'error');
  assert.equal(state.conversation.pendingSubmissionId, null);
  assert.equal(state.conversation.chatError.message, '栖光暂时无法回应。');
  assert.doesNotMatch(JSON.stringify(state), /raw secret|role_thinking/);

  updateDraft('修改后的草稿');
  state = getState();
  assert.equal(state.conversation.chatStatus, 'idle');
  assert.equal(state.conversation.chatError, null);
});

test('only the current successful submission appends a final pair and safe scene', () => {
  initializeState(viewModels(9), { runtimeMode: 'api', initialDraft: '新的消息' });
  completeInitialLoad({ caption: '我在。', tone: 'calm' });
  const payload = beginChatSubmission();

  assert.equal(completeChatSubmission({ ...payload, submissionId: 'stale' }, {
    assistantMessage: { id: 'bad', role: 'assistant', text: '不应出现' },
    scene: { caption: 'bad', tone: 'warm' },
  }), false);

  assert.equal(completeChatSubmission(payload, {
    assistantMessage: { id: payload.assistantMessageId, role: 'assistant', text: '我在这里。' },
    scene: { caption: '正听着。', tone: 'warm', secret: 'drop me' },
  }), true);

  const state = getState();
  assert.equal(state.viewModels.conversation.messages.length, 10);
  assert.deepEqual(state.viewModels.conversation.messages.slice(-2).map((item) => item.text), [
    '新的消息',
    '我在这里。',
  ]);
  assert.deepEqual(state.viewModels.scene, { caption: '正听着。', tone: 'warm' });
  assert.equal(state.conversation.draft, '');
  assert.equal(state.conversation.chatStatus, 'idle');
  assert.doesNotMatch(JSON.stringify(state), /drop me|不应出现/);
});

test('cancelled submission returns to idle without visible error', () => {
  initializeState(viewModels(), { runtimeMode: 'api', initialDraft: '保留我' });
  completeInitialLoad({ caption: '我在。', tone: 'calm' });
  beginChatSubmission();
  failChatSubmission({ kind: 'cancelled', retryable: false, cause: 'secret' });
  const state = getState();
  assert.equal(state.conversation.chatStatus, 'idle');
  assert.equal(state.conversation.chatError, null);
  assert.equal(state.conversation.draft, '保留我');
  assert.equal(state.conversation.pendingSubmissionId, null);
});

test('fixture compatibility remains synchronous for S1', () => {
  initializeState(viewModels(), { runtimeMode: 'fixture' });
  assert.equal(submitLocalConversation('本地消息'), true);
  const state = getState();
  assert.deepEqual(state.viewModels.conversation.messages.slice(-2).map((item) => item.text), [
    '本地消息',
    '我在这里。',
  ]);
  assert.equal(state.viewModels.scene.tone, 'warm');
  assert.equal(state.appStatus, 'fixture');
});
