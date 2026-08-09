const MAX_DURATION_MS = 60_000;
const MIN_DURATION_MS = 500;

function formatDuration(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function recorderMessage(error) {
  if (/权限/.test(error?.message || '')) return '麦克风权限被拒绝，请在系统设置中允许后重试。';
  if (error?.code === 'recording_too_short') return '录音太短，请再说一次。';
  if (error?.code === 'timeout') return '语音处理等待过久，请重试。';
  return error?.message || '语音消息处理失败，录音仍可重试或取消。';
}

function nativeVoiceRecorder(dependencies) {
  if (dependencies.nativeVoice !== undefined) return dependencies.nativeVoice;
  if (typeof window === 'undefined' || window.__LUMINOUS_NATIVE__ !== true) return null;
  return window.LuminousNative?.voice ?? null;
}

export function initVoiceRecorder(dom, { api, onTranscript, announce = () => {}, dependencies = {} }) {
  const nativeVoice = nativeVoiceRecorder(dependencies);
  const now = dependencies.now ?? Date.now;
  let hasRecording = false;
  let startedAt = 0;
  let durationMs = 0;
  let timer = null;
  let controller = null;
  let enabled = true;
  let recording = false;

  const setState = (state, message) => {
    dom.capture.hidden = state === 'idle';
    dom.capture.dataset.state = state;
    dom.record.dataset.active = String(state === 'recording');
    dom.record.setAttribute('aria-label', state === 'recording' ? '结束录音' : '开始录音');
    dom.record.title = state === 'recording' ? '结束录音' : '开始录音';
    dom.record.disabled = !enabled || ['requesting', 'processing', 'sending'].includes(state);
    dom.status.textContent = message;
    dom.confirm.disabled = state !== 'review' && state !== 'error';
    dom.cancel.disabled = state === 'processing' || state === 'sending';
    announce(message);
  };

  const stopNativeRecording = () => {
    if (!recording) return;
    recording = false;
    nativeVoice?.stopMessage?.().catch(() => {});
    if (timer) clearInterval(timer);
    timer = null;
  };

  const clearRecording = () => {
    controller?.abort(); controller = null;
    stopNativeRecording();
    hasRecording = false; durationMs = 0;
    nativeVoice?.discardMessage?.().catch(() => {});
    dom.preview.pause?.(); dom.preview.removeAttribute('src'); dom.preview.hidden = true;
    dom.duration.textContent = '00:00';
    setState('idle', '');
  };

  const finishRecording = async () => {
    if (!recording) return;
    recording = false;
    if (timer) clearInterval(timer);
    timer = null;
    setState('processing', '正在整理录音…');
    let result;
    try {
      result = await nativeVoice.stopMessage();
      durationMs = Math.min(MAX_DURATION_MS, Number(result?.durationMs) || now() - startedAt);
      hasRecording = true;
    } catch (error) {
      setState('error', recorderMessage(error));
      return;
    }
    dom.duration.textContent = formatDuration(durationMs);
    if (durationMs < MIN_DURATION_MS) {
      setState('error', '录音太短，请再说一次。');
      return;
    }
    setState('review', '确认后准备发送。');
  };

  const start = async () => {
    if (!enabled) return;
    if (!nativeVoice?.startMessage || !nativeVoice?.stopMessage) {
      setState('error', '语音录制仅支持 Luminous Android 应用。');
      return;
    }
    clearRecording();
    setState('requesting', '正在请求麦克风权限…');
    try {
      await nativeVoice.startMessage();
      recording = true;
      startedAt = now();
      timer = setInterval(() => {
        durationMs = now() - startedAt;
        dom.duration.textContent = formatDuration(durationMs);
        if (durationMs >= MAX_DURATION_MS) void finishRecording();
      }, 200);
      setState('recording', '录音中，再次点击麦克风结束。');
    } catch (error) {
      setState('error', recorderMessage(error));
    }
  };

  const confirm = async () => {
    if (!hasRecording) { start(); return; }
    controller = new AbortController();
    setState('processing', '正在处理语音消息…');
    try {
      const result = await api.transcribe(null, { durationMs, signal: controller.signal });
      const text = typeof result?.text === 'string' ? result.text.trim() : '';
      if (!text) throw new Error('没有听清，请重试。');
      onTranscript(text);
      hasRecording = false;
      nativeVoice?.discardMessage?.().catch(() => {});
      setState('ready', '语音已准备好，可以发送。');
    } catch (error) {
      setState('error', recorderMessage(error));
    } finally { controller = null; }
  };

  const handleRecord = () => { if (recording) void finishRecording(); else void start(); };
  dom.record?.addEventListener('click', handleRecord);
  dom.cancel?.addEventListener('click', clearRecording);
  dom.confirm?.addEventListener('click', confirm);

  return Object.freeze({
    setEnabled(value) { enabled = value !== false; dom.record.disabled = !enabled; if (!enabled) clearRecording(); },
    setSending(value) {
      if (value && dom.capture.dataset.state === 'ready') setState('sending', '正在发送语音消息…');
      if (!value && dom.capture.dataset.state === 'sending') setState('ready', '发送未完成，可以修改后重试。');
    },
    resetAfterSend() { if (dom.capture.dataset.state === 'sending' || dom.capture.dataset.state === 'ready') clearRecording(); },
    destroy() { clearRecording(); dom.record?.removeEventListener('click', handleRecord); dom.cancel?.removeEventListener('click', clearRecording); dom.confirm?.removeEventListener('click', confirm); },
  });
}
