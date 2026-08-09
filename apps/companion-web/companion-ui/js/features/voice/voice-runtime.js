import { adaptCompanionSettings } from '../../adapters/silent-spaces-adapter.js';
import { requestJson } from '../../services/api-client.js';
import { voiceApi } from '../../services/voice-api.js';
import { initVoicePlayer } from './voice-player.js';
import { initVoiceRecorder } from './voice-recorder.js';
import { initVoiceCall } from './voice-call.js';

export function initVoiceRuntime(dom, { runtimeMode, announce, onRealtimeTurn = () => {}, onVoiceMessage = () => {} }) {
  const player = initVoicePlayer(dom.dialogueStream, { api: voiceApi, announce });
  const recorder = initVoiceRecorder(dom.voice, {
    api: voiceApi,
    announce,
    onTranscript: onVoiceMessage,
  });
  const call = initVoiceCall(dom.voice.call, { announce, onTurn: onRealtimeTurn });
  const setSettings = (settings) => {
    player.setSettings(settings);
    recorder.setEnabled(settings.voiceEnabled);
    call.setEnabled(settings.voiceEnabled);
  };
  if (runtimeMode === 'api') {
    requestJson('/api/settings/companion')
      .then(adaptCompanionSettings)
      .then(setSettings)
      .catch(() => announce('语音设置暂时无法读取，文字对话仍可使用。'));
  }
  return Object.freeze({
    setSettings,
    testVoice: (settings) => player.testVoice(settings),
    onReply: (message) => player.maybeAutoPlay(message),
    setSending: (value) => recorder.setSending(value),
    resetAfterSend: () => recorder.resetAfterSend(),
    destroy() { recorder.destroy(); player.destroy(); call.destroy(); },
  });
}
