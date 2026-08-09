import test from 'node:test';
import assert from 'node:assert/strict';

import { adaptCompanionSettings } from '../../apps/companion-web/companion-ui/js/adapters/silent-spaces-adapter.js';
import { initSilentSpaces } from '../../apps/companion-web/companion-ui/js/features/silent-spaces/silent-spaces-controller.js';
import { createSilentSpacesApi } from '../../apps/companion-web/companion-ui/js/services/silent-spaces-api.js';

test('companion settings adapter keeps user instructions and never expects an API key value', () => {
  const result = adaptCompanionSettings({
    llm: {
      base_url: 'https://gateway.example/v1', model: 'model-v2', temperature: 0.4,
      max_tokens: 1200, api_key_configured: true, configured: true,
    },
    companion: { instructions: '叫我阿澈。\n不要替我做决定。', customized: true },
    tts: {
      provider: 'openai-compatible', base_url: 'https://tts.example/v1', model: 'tts-v2',
      api_key_configured: true, configured: true,
    },
    updated_at: '2026-08-05T08:00:00Z',
  });
  assert.deepEqual(result, {
    baseUrl: 'https://gateway.example/v1', model: 'model-v2', temperature: 0.4,
    maxTokens: 1200, apiKeyConfigured: true, configured: true,
    instructions: '叫我阿澈。\n不要替我做决定。', customized: true,
    ttsBaseUrl: 'https://tts.example/v1', ttsModel: 'tts-v2', ttsApiKeyConfigured: true,
    voiceEnabled: true, autoPlay: false, voiceId: 'alloy', speakingRate: 1,
    outputVolume: 1, sttProvider: 'openai-compatible', sttConfigured: false,
    ttsProvider: 'openai-compatible', ttsConfigured: true,
    updatedAt: '2026-08-05T08:00:00Z',
  });
  assert.equal(Object.hasOwn(result, 'apiKey'), false);
  assert.equal(Object.hasOwn(result, 'ttsApiKey'), false);
});

test('silent spaces API loads and saves companion settings through the dedicated endpoint', async () => {
  const calls = [];
  const request = async (path, options = {}) => {
    calls.push({ path, options });
    if (path === '/api/settings/notifications') return {};
    if (path === '/api/state') return {};
    return {
      llm: { base_url: '', model: '', temperature: 0.7, max_tokens: 768, api_key_configured: false, configured: false },
      companion: { instructions: '', customized: false }, updated_at: '',
    };
  };
  const api = createSilentSpacesApi({ request });
  await api.loadPrivacy();
  await api.saveCompanionSettings({ changes: { model: 'model-v2', api_key: 'secret' } });

  assert.deepEqual(calls.map(({ path }) => path), [
    '/api/settings/notifications', '/api/state', '/api/settings/companion', '/api/settings/companion',
  ]);
  assert.equal(calls.at(-1).options.method, 'PATCH');
  assert.deepEqual(calls.at(-1).options.body, { model: 'model-v2', api_key: 'secret' });
});

test('companion inputs remain available when the settings endpoint is temporarily unavailable', async () => {
  const api = createSilentSpacesApi({
    request: async (path) => {
      if (path === '/api/settings/notifications') return {};
      if (path === '/api/state') return {};
      throw new Error('endpoint unavailable');
    },
  });

  const result = await api.loadPrivacy();

  assert.equal(result.companionUnavailable, true);
  assert.equal(result.companion.llm.base_url, '');
  assert.equal(result.companion.companion.instructions, '');
});

test('activating a deep-linked privacy space loads companion settings without a portal click', async () => {
  let privacyLoads = 0;
  const controller = initSilentSpaces({
    portals: {}, outbox: {}, memory: {}, privacy: {},
  }, {
    dataSource: {
      async loadPrivacy() {
        privacyLoads += 1;
        return {
          notifications: {}, state: {},
          companion: {
            llm: { base_url: '', model: '', temperature: 0.7, max_tokens: 768 },
            companion: { instructions: '' },
          },
        };
      },
    },
    onStateChange() {},
  });

  await controller.activate('privacy');
  await controller.activate('privacy');

  assert.equal(privacyLoads, 1);
  controller.destroy();
});

test('controller saves a user supplied TTS API without exposing the stored key', async () => {
  const control = (value = '') => {
    const listeners = {};
    return {
      value, checked: false, disabled: false, hidden: true, textContent: '', title: '', dataset: {},
      addEventListener(type, listener) { listeners[type] = listener; },
      listeners,
    };
  };
  const companionForm = control();
  const privacy = {
    form: control(), status: control(), retry: control(), dnd: control(),
    enabled: control(), limit: control('3'), quietStart: control(), quietEnd: control(), save: control(),
    companionForm, companionStatus: control(), companionConnectionState: control(),
    companionBaseUrl: control(), companionApiKey: control(), companionKeyState: control(),
    companionModel: control(), companionTemperature: control('0.7'), companionMaxTokens: control('768'),
    companionInstructions: control(), companionSave: control(),
    ttsBaseUrl: control(), ttsApiKey: control(), ttsKeyState: control(), ttsModel: control(),
    voiceEnabled: control(), voiceAutoPlay: control(), voiceId: control('alloy'),
    voiceRate: control('1'), voiceVolume: control('1'), voiceProviderSummary: control(),
    voiceTest: control(), voiceTestStatus: control(),
  };
  privacy.voiceEnabled.checked = true;
  let savedChanges;
  const companionResponse = (configured = false) => ({
    llm: { base_url: '', model: '', temperature: 0.7, max_tokens: 768, api_key_configured: false, configured: false },
    companion: { instructions: '', customized: false },
    tts: {
      provider: 'openai-compatible', base_url: configured ? 'https://tts.user.test/v1' : '',
      model: configured ? 'tts-user-v3' : '', api_key_configured: configured, configured,
    },
    voice: { voice_enabled: true, auto_play: false, voice_id: 'alloy', speaking_rate: 1, output_volume: 1 },
    providers: {
      stt: { provider: 'openai-compatible', configured: false },
      tts: { provider: 'openai-compatible', configured },
    },
    updated_at: '',
  });
  const controller = initSilentSpaces({ portals: {}, outbox: {}, memory: {}, privacy }, {
    dataSource: {
      async loadPrivacy() { return { notifications: {}, state: { state: {} }, companion: companionResponse() }; },
      async saveCompanionSettings({ changes }) {
        savedChanges = changes;
        return companionResponse(true);
      },
    },
    onStateChange() {},
  });

  await controller.activate('privacy');
  controller.render();
  privacy.ttsBaseUrl.value = 'https://tts.user.test/v1';
  privacy.ttsApiKey.value = 'tts-user-secret';
  privacy.ttsModel.value = 'tts-user-v3';
  companionForm.listeners.input();
  await companionForm.listeners.submit({ preventDefault() {} });

  assert.equal(savedChanges.tts_base_url, 'https://tts.user.test/v1');
  assert.equal(savedChanges.tts_api_key, 'tts-user-secret');
  assert.equal(savedChanges.tts_model, 'tts-user-v3');
  assert.equal(privacy.ttsApiKey.value, 'tts-user-secret');
  controller.render();
  assert.equal(privacy.ttsApiKey.value, '');
  assert.equal(privacy.ttsApiKey.placeholder, '已保存；留空表示不修改');
  controller.destroy();
});

test('controller shows editable Android fields when companion settings could not be loaded', async () => {
  const control = (value = '') => ({
    value, checked: false, disabled: false, hidden: true, textContent: '',
    dataset: {}, addEventListener() {},
  });
  const privacy = {
    form: control(), status: control(), retry: control(), dnd: control(),
    enabled: control(), limit: control('3'), quietStart: control(), quietEnd: control(), save: control(),
    companionForm: control(), companionStatus: control(), companionConnectionState: control(),
    companionBaseUrl: control(), companionApiKey: control(), companionKeyState: control(),
    companionModel: control(), companionTemperature: control(), companionMaxTokens: control(),
    companionInstructions: control(), companionSave: control(),
  };
  const controller = initSilentSpaces({ portals: {}, outbox: {}, memory: {}, privacy }, {
    dataSource: {
      async loadPrivacy() {
        return {
          notifications: {}, state: { state: {} }, companionUnavailable: true,
          companion: {
            llm: { base_url: '', model: '', temperature: 0.7, max_tokens: 768 },
            companion: { instructions: '' },
          },
        };
      },
    },
    onStateChange() {},
  });

  await controller.activate('privacy');
  controller.render();

  assert.equal(privacy.companionForm.hidden, false);
  assert.match(privacy.companionStatus.textContent, /仍可填写/);
  assert.equal(privacy.companionBaseUrl.value, '');
  assert.equal(privacy.companionApiKey.value, '');
  controller.destroy();
});
