import { requestJson } from '../../services/api-client.js';

export function initVoiceCall(button, {
  enabled = true,
  announce = () => {},
  onTurn = () => {},
  dependencies = {},
} = {}) {
  const progress = button?.parentElement?.querySelector?.('[data-hook="voice-call-progress"]') ?? null;
  const progressText = progress?.querySelector?.('[data-hook="voice-call-progress-text"]') ?? null;
  const nativeVoice = dependencies.nativeVoice
    ?? (typeof window !== 'undefined' && window.__LUMINOUS_NATIVE__ ? window.LuminousNative?.voice : null);
  const createSession = dependencies.createSession
    ?? (() => requestJson('/api/voice/livekit/session', { method: 'POST', body: { client: 'android' } }));
  const endSession = dependencies.endSession
    ?? ((sessionId) => requestJson(`/api/voice/livekit/session/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    }));

  let state = 'idle';
  let closing = false;
  let stateListener = null;
  let transcriptionListener = null;
  let audioDevicesListener = null;
  let userTranscript = '';
  let assistantTranscript = '';
  let callSessionId = '';

  const setState = (next, message = '', { showProgress = next !== 'idle' } = {}) => {
    state = next;
    if (button) {
      button.dataset.state = next;
      button.dataset.active = String(next !== 'idle');
      button.disabled = !enabled || next === 'connecting';
      const label = next === 'idle' ? '开始实时通话' : next === 'connecting' ? '正在连接实时通话' : '结束实时通话';
      button.setAttribute('aria-label', label);
      button.title = label;
    }
    if (progress) progress.hidden = !showProgress;
    if (progressText) progressText.textContent = message;
    if (message) announce(message);
  };

  const clearListeners = () => {
    stateListener?.remove?.();
    transcriptionListener?.remove?.();
    audioDevicesListener?.remove?.();
    stateListener = null;
    transcriptionListener = null;
    audioDevicesListener = null;
  };

  const close = async ({ message = '实时通话已结束。', notifyNative = true } = {}) => {
    if (closing) return;
    closing = true;
    const endingSessionId = callSessionId;
    if (notifyNative) await nativeVoice?.closeCall?.().catch(() => {});
    if (endingSessionId) await endSession(endingSessionId).catch(() => {});
    clearListeners();
    userTranscript = '';
    assistantTranscript = '';
    callSessionId = '';
    setState('idle', message, { showProgress: Boolean(message) });
    closing = false;
  };

  const handleNativeState = ({ status, message = '', muted = false, callSessionId: nativeSessionId = '' } = {}) => {
    if (nativeSessionId) callSessionId = nativeSessionId;
    if (status === 'connected') setState('connected', muted ? '麦克风已静音。' : '实时通话已连接，正在聆听。');
    else if (status === 'reconnecting') setState('reconnecting', '网络切换，正在恢复通话…');
    else if (status === 'connecting') setState('connecting', '正在建立安全语音房间…');
    else if (status === 'failed') void close({ message: message || '实时通话连接失败，请重试。', notifyNative: false });
    else if (status === 'disconnected' && state !== 'idle') void close({ message: '实时通话已断开。', notifyNative: false });
  };

  const handleTranscription = ({
    text = '', final = false, participantIdentity = '', assistant = false,
  } = {}) => {
    const clean = String(text).trim();
    if (!clean) return;
    const isAssistant = assistant === true || participantIdentity.includes('agent');
    if (isAssistant) assistantTranscript = clean;
    else userTranscript = clean;
    setState('connected', isAssistant ? `叶筝：${clean.slice(0, 36)}` : `你：${clean.slice(0, 36)}`);
    if (isAssistant && final && userTranscript) {
      onTurn(userTranscript, assistantTranscript);
      userTranscript = '';
      assistantTranscript = '';
    }
  };

  const ensureListeners = async () => {
    if (!stateListener) {
      stateListener = await nativeVoice.addCallListener(handleNativeState);
    }
    if (!transcriptionListener && nativeVoice.addTranscriptionListener) {
      transcriptionListener = await nativeVoice.addTranscriptionListener(handleTranscription);
    }
    if (!audioDevicesListener && nativeVoice.addAudioDevicesListener) {
      audioDevicesListener = await nativeVoice.addAudioDevicesListener(() => {});
    }
  };

  const connect = async () => {
    if (!enabled || !nativeVoice?.connectCall || !nativeVoice?.addCallListener) {
      setState('idle', '实时通话仅支持 Luminous Android 应用。', { showProgress: true });
      return;
    }
    setState('connecting', '正在建立安全语音房间…');
    try {
      await ensureListeners();
      const connection = await createSession();
      callSessionId = String(connection.callSessionId || '');
      await nativeVoice.connectCall(connection);
    } catch (error) {
      await close({ message: '无法开始实时通话，请重试。' });
    }
  };

  const click = () => { if (state === 'idle') void connect(); else void close(); };
  button?.addEventListener('click', click);
  setState('idle');
  if (nativeVoice?.addCallListener && nativeVoice?.getCallState) {
    void ensureListeners()
      .then(() => nativeVoice.getCallState())
      .then(handleNativeState)
      .catch(() => {});
  }

  return Object.freeze({
    setEnabled(value) {
      enabled = value !== false;
      if (!enabled) void close({ message: '' });
      else setState(state);
    },
    destroy() {
      clearListeners();
      button?.removeEventListener('click', click);
    },
  });
}
