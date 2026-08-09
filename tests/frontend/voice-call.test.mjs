import assert from 'node:assert/strict';
import test from 'node:test';

import { initVoiceCall } from '../../apps/companion-web/companion-ui/js/features/voice/voice-call.js';

function buttonFixture() {
  const progressText = { textContent: '' };
  const progress = {
    hidden: true,
    querySelector: () => progressText,
  };
  const listeners = new Map();
  const button = {
    dataset: {},
    disabled: false,
    parentElement: { querySelector: () => progress },
    setAttribute() {},
    addEventListener(type, listener) { listeners.set(type, listener); },
    removeEventListener(type) { listeners.delete(type); },
    click() { listeners.get('click')?.(); },
  };
  return { button, progress, progressText };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test('realtime voice obtains a short-lived session before native LiveKit connects', async () => {
  const { button } = buttonFixture();
  const calls = [];
  const ended = [];
  const listeners = [];
  const connection = {
    serverUrl: 'wss://voice.example',
    participantToken: 'token',
    callSessionId: 'voice_test',
  };
  const nativeVoice = {
    async addCallListener(listener) { listeners.push(listener); return { remove() {} }; },
    async addTranscriptionListener() { return { remove() {} }; },
    async connectCall(value) { calls.push(value); },
    async closeCall() {},
  };
  initVoiceCall(button, {
    dependencies: {
      nativeVoice,
      createSession: async () => connection,
      endSession: async (sessionId) => { ended.push(sessionId); },
    },
  });

  button.click();
  await tick();

  assert.deepEqual(calls, [connection]);
  assert.equal(button.dataset.state, 'connecting');
  listeners[0]({ status: 'connected' });
  assert.equal(button.dataset.state, 'connected');
  button.click();
  await tick();
  assert.deepEqual(ended, ['voice_test']);
  assert.equal(button.dataset.state, 'idle');
});

test('realtime voice restores an Android background call without creating another room', async () => {
  const { button } = buttonFixture();
  const calls = [];
  const nativeVoice = {
    async addCallListener() { return { remove() {} }; },
    async addTranscriptionListener() { return { remove() {} }; },
    async getCallState() { return { status: 'connected', muted: false }; },
    async connectCall(value) { calls.push(value); },
    async closeCall() {},
  };
  const controller = initVoiceCall(button, {
    dependencies: {
      nativeVoice,
      createSession: async () => ({ serverUrl: 'wss://unused.example', participantToken: 'unused' }),
      endSession: async () => {},
    },
  });

  await tick();
  await tick();
  assert.equal(button.dataset.state, 'connected');
  assert.deepEqual(calls, []);

  controller.destroy();
  assert.deepEqual(calls, []);
  assert.equal(button.dataset.state, 'connected');
});

test('realtime voice refuses browser media and reports Android-only availability', async () => {
  const { button, progressText } = buttonFixture();
  initVoiceCall(button, { dependencies: { nativeVoice: null } });

  button.click();
  await tick();

  assert.equal(button.dataset.state, 'idle');
  assert.match(progressText.textContent, /Android/);
});

test('realtime voice uses the native participant role for completed turns', async () => {
  const { button } = buttonFixture();
  const turns = [];
  let transcriptionListener;
  const nativeVoice = {
    async addCallListener() { return { remove() {} }; },
    async addTranscriptionListener(listener) {
      transcriptionListener = listener;
      return { remove() {} };
    },
    async getCallState() { return { status: 'connected' }; },
    async closeCall() {},
  };
  initVoiceCall(button, {
    onTurn: (user, assistant) => turns.push([user, assistant]),
    dependencies: { nativeVoice, endSession: async () => {} },
  });
  await tick();
  await tick();

  transcriptionListener({ text: '今天有点累', final: true, assistant: false, participantIdentity: 'opaque-user' });
  transcriptionListener({ text: '那今晚就早点休息。', final: true, assistant: true, participantIdentity: 'opaque-remote' });

  assert.deepEqual(turns, [['今天有点累', '那今晚就早点休息。']]);
});
