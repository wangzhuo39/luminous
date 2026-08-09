import assert from 'node:assert/strict';
import test from 'node:test';

import { initVoicePlayer } from '../../apps/companion-web/companion-ui/js/features/voice/voice-player.js';
import { initVoiceRecorder } from '../../apps/companion-web/companion-ui/js/features/voice/voice-recorder.js';
import { createVoiceApi, VoiceApiError } from '../../apps/companion-web/companion-ui/js/services/voice-api.js';

class Control extends EventTarget {
  constructor() {
    super();
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.textContent = '';
    this.attributes = {};
  }

  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
}

function recorderDom() {
  const preview = new Control();
  preview.pause = () => {};
  preview.src = '';
  return {
    capture: new Control(), record: new Control(), waveform: new Control(),
    duration: new Control(), status: new Control(), preview,
    cancel: new Control(), confirm: new Control(),
  };
}

test('voice API uploads raw audio and preserves structured provider errors', async () => {
  const calls = [];
  const api = createVoiceApi({
    setTimer: () => 1, clearTimer() {},
    async fetchImpl(path, options) {
      calls.push({ path, options });
      return path.endsWith('transcriptions')
        ? new Response(JSON.stringify({ text: '转写内容' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        : new Response(new Blob(['audio'], { type: 'audio/mpeg' }), { status: 200, headers: { 'Content-Type': 'audio/mpeg' } });
    },
  });
  const blob = new Blob(['binary'], { type: 'audio/wav' });
  const result = await api.transcribe(blob, { durationMs: 1200 });
  const speech = await api.synthesize('你好', { voiceId: 'warm', speakingRate: 1.1 });

  assert.equal(result.text, '转写内容');
  assert.equal(calls[0].options.body, blob);
  assert.equal(calls[0].options.headers['X-Audio-Duration-Ms'], '1200');
  assert.equal(speech.type, 'audio/mpeg');

  const failing = createVoiceApi({
    setTimer: () => 1, clearTimer() {},
    fetchImpl: async () => new Response(JSON.stringify({ error: { code: 'recording_too_short', message: '太短', retryable: true } }), { status: 422, headers: { 'Content-Type': 'application/json' } }),
  });
  await assert.rejects(() => failing.transcribe(blob, { durationMs: 100 }), (error) => (
    error instanceof VoiceApiError && error.code === 'recording_too_short' && error.message === '太短'
  ));
});

test('voice API decodes the Android native arraybuffer response without using patched fetch', async () => {
  let nativeRequest;
  const api = createVoiceApi({
    nativeBridge: {
      async synthesizeVoice(options) {
        nativeRequest = options;
        return {
          data: Buffer.from([0xff, 0xfb, 0x90, 0x64]).toString('base64'),
          contentType: 'audio/mpeg',
        };
      },
    },
    fetchImpl: async () => { throw new Error('patched fetch must not be used for native audio'); },
  });

  const speech = await api.synthesize('你好', { voiceId: 'alloy', speakingRate: 1.05 });

  assert.deepEqual(nativeRequest, { text: '你好', voiceId: 'alloy', speakingRate: 1.05 });
  assert.equal(speech.type, 'audio/mpeg');
  assert.deepEqual([...new Uint8Array(await speech.arrayBuffer())], [0xff, 0xfb, 0x90, 0x64]);
});

test('voice API sends Android recordings through the native transport', async () => {
  let calls = 0;
  const api = createVoiceApi({
    nativeBridge: {
      voice: {
        async transcribeMessage() { calls += 1; return { text: '原生转写结果' }; },
      },
    },
    fetchImpl: async () => { throw new Error('Blob upload must not be used for native audio'); },
  });

  const result = await api.transcribe(null, { durationMs: 1200 });

  assert.equal(calls, 1);
  assert.equal(result.text, '原生转写结果');
});

test('recorder uses the Android native WAV recorder before voice processing', async () => {
  const dom = recorderDom();
  const transitions = [];
  let transcript = '';
  let starts = 0;
  let stops = 0;
  let clock = 0;
  const recorder = initVoiceRecorder(dom, {
    api: { async transcribe() { transitions.push('transcribing'); return { text: '明天提醒我喝水' }; } },
    onTranscript(value) { transcript = value; },
    announce(value) { if (value) transitions.push(value); },
    dependencies: {
      nativeVoice: {
        async startMessage() { starts += 1; },
        async stopMessage() {
          stops += 1;
          return { durationMs: 1200 };
        },
      },
      now: () => { clock += 1200; return clock; },
    },
  });

  dom.record.dispatchEvent(new Event('click'));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(dom.capture.dataset.state, 'recording');
  dom.record.dispatchEvent(new Event('click'));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(dom.capture.dataset.state, 'review');
  assert.equal(dom.preview.hidden, true);
  assert.equal(starts, 1);
  assert.equal(stops, 1);
  dom.confirm.dispatchEvent(new Event('click'));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(dom.capture.dataset.state, 'ready');
  assert.equal(transcript, '明天提醒我喝水');
  assert.match(transitions.join(' '), /请求麦克风权限/);
  assert.match(transitions.join(' '), /语音已准备好，可以发送/);
  recorder.destroy();
});

test('player stops the previous audio and revokes every Blob URL', async () => {
  const revoked = [];
  const instances = [];
  let sequence = 0;
  class FakeAudio extends EventTarget {
    constructor(src) { super(); this.src = src; this.paused = true; this.muted = false; instances.push(this); }
    async play() { this.paused = false; }
    pause() { this.paused = true; }
  }
  const dialogue = new Control();
  dialogue.querySelectorAll = () => [];
  const player = initVoicePlayer(dialogue, {
    api: { async synthesize() { return new Blob(['audio'], { type: 'audio/mpeg' }); } },
    dependencies: {
      Audio: FakeAudio,
      createObjectURL: () => `blob:${++sequence}`,
      revokeObjectURL: (url) => revoked.push(url),
    },
  });

  await player.testVoice({ voiceId: 'one' });
  await player.testVoice({ voiceId: 'two' });
  assert.equal(instances.length, 2);
  assert.equal(instances[0].paused, true);
  assert.deepEqual(revoked, ['blob:1']);
  player.destroy();
  assert.deepEqual(revoked, ['blob:1', 'blob:2']);
});
