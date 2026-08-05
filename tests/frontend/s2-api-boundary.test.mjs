import assert from 'node:assert/strict';
import test from 'node:test';

import {
  adaptChatResponse,
  adaptStateResponse,
  sanitizeChatHistory,
  sendChatMessage,
} from '../../apps/companion-web/companion-ui/js/adapters/api-adapter.js';
import { requestJson } from '../../apps/companion-web/companion-ui/js/services/api-client.js';
import { AppError } from '../../apps/companion-web/companion-ui/js/shared/errors.js';

function response({ status = 200, body = '{}' } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async text() {
      return body;
    },
  };
}

function dependencies(fetchImpl, overrides = {}) {
  return {
    fetchImpl,
    isOnline: () => true,
    setTimer: () => 1,
    clearTimer: () => {},
    ...overrides,
  };
}

async function expectKind(promise, kind) {
  await assert.rejects(promise, (error) => error instanceof AppError && error.kind === kind);
}

test('requestJson parses JSON and handles empty success responses', async () => {
  const payload = await requestJson('/api/state', {
    dependencies: dependencies(async () => response({ body: '{"state":{}}' })),
  });
  assert.deepEqual(payload, { state: {} });

  const empty = await requestJson('/api/state', {
    dependencies: dependencies(async () => response({ status: 204, body: '' })),
  });
  assert.equal(empty, null);
});

test('mutation requests get one stable idempotency key across a transport retry', async () => {
  const calls = [];
  const payload = await requestJson('/api/tasks', {
    method: 'POST',
    body: { title: '只创建一次' },
    dependencies: dependencies(async (_url, options) => {
      calls.push(options);
      if (calls.length === 1) throw new TypeError('connection reset');
      return response({ status: 201, body: '{"ok":true}' });
    }, { randomUUID: () => 'test-operation-id' }),
  });
  assert.deepEqual(payload, { ok: true });
  assert.equal(calls.length, 2);
  assert.equal(calls[0].headers['Idempotency-Key'], 'luminous-test-operation-id');
  assert.equal(calls[1].headers['Idempotency-Key'], 'luminous-test-operation-id');
  assert.equal(calls[0].body, calls[1].body);
});

test('requestJson safely maps HTTP, malformed JSON and offline failures', async () => {
  await expectKind(requestJson('/api/chat', {
    dependencies: dependencies(async () => response({ status: 503 })),
  }), 'model-unavailable');
  await expectKind(requestJson('/api/chat', {
    dependencies: dependencies(async () => response({ status: 400 })),
  }), 'validation');
  await expectKind(requestJson('/api/state', {
    dependencies: dependencies(async () => response({ body: '{bad json' })),
  }), 'server');
  await expectKind(requestJson('/api/state', {
    dependencies: dependencies(async () => response(), { isOnline: () => false }),
  }), 'offline');
});

test('requestJson distinguishes timeout and caller cancellation', async () => {
  const abortingFetch = async (_path, options) => new Promise((_resolve, reject) => {
    if (options.signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  });

  await expectKind(requestJson('/api/state', {
    dependencies: dependencies(abortingFetch, {
      setTimer: (callback) => {
        callback();
        return 1;
      },
    }),
  }), 'timeout');

  const controller = new AbortController();
  const pending = requestJson('/api/state', {
    signal: controller.signal,
    dependencies: dependencies(abortingFetch),
  });
  controller.abort();
  await expectKind(pending, 'cancelled');
});

test('requestJson rejects paths outside the same-origin API namespace', async () => {
  await expectKind(requestJson('https://example.com/api/state', {
    dependencies: dependencies(async () => response()),
  }), 'validation');
  await expectKind(requestJson('//example.com/api/state', {
    dependencies: dependencies(async () => response()),
  }), 'validation');
});

test('state adapter reads only state and maps it to restrained presentation', () => {
  const adapted = adaptStateResponse({
    state: { mood: 'steady', energy: 0.8, risk_level: 'low' },
    recent_events: [{ role_thinking: 'secret' }],
    recent_memories: [{ text: 'secret' }],
    job_count: 99,
  });
  assert.deepEqual(adapted, {
    caption: '我在这里。',
    tone: 'calm',
    status: {
      heartLabel: '心跳平稳', heartDetail: '72 次/分',
      activityLabel: '正在看雨', activityDetail: '窗边 · 安静等你',
      moodLabel: '有点安静', moodDetail: '心情平静',
    },
  });
  assert.doesNotMatch(JSON.stringify(adapted), /secret|thinking|memory|job/i);

  assert.equal(adaptStateResponse({
    state: { mood: 'steady', support_need: 0.9, risk_level: 'high' },
  }).tone, 'concerned');
});

test('chat adapter keeps only final reply and safe scene presentation', () => {
  const adapted = adaptChatResponse({
    reply: '  我在，先陪你慢一点。  ',
    presence: { caption: '  静静听你说。  ', thought: 'secret thought' },
    state: { mood: 'warm' },
    role_thinking: 'secret thinking',
    role_action: 'secret action',
    ledger: { trace_id: 'secret trace' },
    prompt: { raw: 'secret prompt' },
    analysis: { raw: 'secret analysis' },
  }, { messageId: 'assistant-safe-1' });

  assert.deepEqual(adapted, {
    assistantMessage: {
      id: 'assistant-safe-1',
      role: 'assistant',
      text: '我在，先陪你慢一点。',
    },
    scene: {
      caption: '静静听你说。',
      tone: 'warm',
      status: {
        heartLabel: '心跳平稳', heartDetail: '72 次/分',
        activityLabel: '正在看雨', activityDetail: '窗边 · 安静等你',
        moodLabel: '有些温柔', moodDetail: '心里暖着',
      },
    },
  });
  assert.doesNotMatch(JSON.stringify(adapted), /secret|thinking|action|ledger|prompt|analysis/i);
});

test('history sanitizer filters unknown roles and caps successful final messages', () => {
  const history = [
    { role: 'system', content: 'secret' },
    { role: 'user', content: '   ' },
    ...Array.from({ length: 12 }, (_, index) => ({
      role: index % 2 === 0 ? 'user' : 'assistant',
      content: ` message ${index + 1} `,
    })),
  ];
  const safe = sanitizeChatHistory(history);
  assert.equal(safe.length, 10);
  assert.deepEqual(safe[0], { role: 'user', content: 'message 3' });
  assert.equal(safe.at(-1).content, 'message 12');
});

test('sendChatMessage emits the exact safe request shape', async () => {
  let captured;
  const result = await sendChatMessage(' 今天有点累。 ', [
    { role: 'system', content: 'secret' },
    { role: 'assistant', content: '上一次最终回复' },
  ], {
    messageId: 'assistant-safe-2',
    dependencies: dependencies(async (path, options) => {
      captured = { path, options };
      return response({
        body: JSON.stringify({
          reply: '我在。',
          presence: { caption: '我正听着。' },
          state: { mood: 'steady' },
          role_thinking: 'must not escape',
        }),
      });
    }),
  });

  assert.equal(captured.path, '/api/chat');
  assert.deepEqual(JSON.parse(captured.options.body), {
    message: '今天有点累。',
    history: [{ role: 'assistant', content: '上一次最终回复' }],
  });
  assert.equal(result.assistantMessage.id, 'assistant-safe-2');
  assert.doesNotMatch(JSON.stringify(result), /must not escape/);
});
