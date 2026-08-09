const BARGE_IN_DELAY_MS = 450;

function pcmBuffer(base64) {
  const raw = globalThis.atob(base64 || '');
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes.buffer;
}

function nativeVoice(dependencies) {
  if (dependencies.nativeVoice !== undefined) return dependencies.nativeVoice;
  if (typeof window === 'undefined' || window.__LUMINOUS_NATIVE__ !== true) return null;
  return window.LuminousNative?.voice ?? null;
}

export function initVoiceCall(button, { enabled = true, announce = () => {}, onTurn = () => {}, dependencies = {} } = {}) {
  const AudioContextImpl = dependencies.AudioContext ?? globalThis.AudioContext ?? globalThis.webkitAudioContext;
  const recorder = nativeVoice(dependencies);
  const progress = button?.parentElement?.querySelector?.('[data-hook="voice-call-progress"]') ?? null;
  const progressText = progress?.querySelector?.('[data-hook="voice-call-progress-text"]') ?? null;
  let context = null; let callListener = null; let vadListener = null; let bargeTimer = null;
  let speechActive = false; let turnEndedBeforeReady = false; let activeTranscript = ''; let activeReply = ''; let nextPlaybackAt = 0;
  const playback = new Set();
  let state = 'idle';

  const setState = (next, message = '', { showProgress = next !== 'idle' } = {}) => {
    state = next;
    button.dataset.state = next;
    button.dataset.active = String(next !== 'idle');
    button.disabled = !enabled || next === 'connecting';
    const labels = { idle: '开始实时通话', connecting: '正在连接实时通话', listening: '正在聆听', thinking: '正在回应', speaking: '结束实时通话', ready: '结束实时通话' };
    button.setAttribute('aria-label', labels[next] || labels.idle); button.title = labels[next] || labels.idle;
    if (progress) {
      progress.dataset.state = next;
      progress.hidden = !showProgress;
    }
    if (progressText) progressText.textContent = message;
    if (message) announce(message);
  };
  const clearBargeTimer = () => { if (bargeTimer) clearTimeout(bargeTimer); bargeTimer = null; };
  const stopPlayback = () => {
    for (const node of playback) { try { node.stop(); } catch {} }
    playback.clear(); nextPlaybackAt = 0;
  };
  const close = ({ message = '', showProgress = false } = {}) => {
    clearBargeTimer(); stopPlayback(); speechActive = false;
    recorder?.stopStream?.().catch(() => {});
    recorder?.sendCallEvent?.(JSON.stringify({ type: 'call.end' })).catch(() => {});
    recorder?.closeCall?.().catch(() => {});
    callListener?.remove?.(); callListener = null; vadListener?.remove?.(); vadListener = null;
    context?.close?.(); context = null; turnEndedBeforeReady = false; activeTranscript = ''; activeReply = '';
    setState('idle', message, { showProgress });
  };
  const playPcm = (base64) => {
    if (!context || state === 'idle') return;
    const pcm = new Int16Array(pcmBuffer(base64)); const audio = context.createBuffer(1, pcm.length, 24_000); const data = audio.getChannelData(0);
    for (let index = 0; index < pcm.length; index += 1) data[index] = pcm[index] / 0x8000;
    const node = context.createBufferSource(); node.buffer = audio; node.connect(context.destination); playback.add(node);
    node.addEventListener('ended', () => playback.delete(node), { once: true });
    nextPlaybackAt = Math.max(nextPlaybackAt, context.currentTime); node.start(nextPlaybackAt); nextPlaybackAt += audio.duration;
  };
  const beginTurn = async ({ interrupt = false } = {}) => {
    if (!recorder || state === 'connecting' || state === 'listening' || state === 'thinking') return;
    clearBargeTimer(); turnEndedBeforeReady = false; activeTranscript = ''; activeReply = '';
    setState('connecting', interrupt ? '已打断，正在重新听你说。' : '正在准备识别…');
    if (interrupt) {
      stopPlayback();
      await recorder.sendCallEvent(JSON.stringify({ type: 'response.cancel' })).catch(() => {});
    }
    await recorder.setCallAudioEnabled(false);
    await recorder.sendCallEvent(JSON.stringify({ type: 'turn.start' }));
  };
  const finishTurn = async () => {
    if (state !== 'listening') return;
    await recorder.setCallAudioEnabled(false);
    await recorder.sendCallEvent(JSON.stringify({ type: 'turn.end' }));
    setState('thinking', '你说完了，正在识别与思考…');
  };
  const handleVad = ({ type }) => {
    if (type === 'speech_start') {
      speechActive = true;
      if (state === 'ready') void beginTurn();
      else if (state === 'speaking' || state === 'thinking') {
        clearBargeTimer();
        bargeTimer = setTimeout(() => { if (speechActive && (state === 'speaking' || state === 'thinking')) void beginTurn({ interrupt: true }); }, BARGE_IN_DELAY_MS);
      }
      return;
    }
    if (type === 'speech_end') {
      speechActive = false; clearBargeTimer();
      if (state === 'listening') void finishTurn();
      else if (state === 'connecting') turnEndedBeforeReady = true;
    }
  };
  const handleCallEvent = ({ kind, data }) => {
    if (kind === 'binary') { playPcm(data); return; }
    if (kind === 'error') { if (state !== 'idle') close({ message: data || '实时语音连接失败，请重试。', showProgress: true }); return; }
    if (kind === 'closed') { if (state !== 'idle') close({ message: '通话已断开，点击图标重试。', showProgress: true }); return; }
    if (kind !== 'text') return;
    let event; try { event = JSON.parse(data); } catch { return; }
    if (event.type === 'call.ready') {
      recorder.startStream().then(() => setState('ready', '已连接，正在等待你说话。'))
        .catch(() => close({ message: '无法启动麦克风，请检查权限。', showProgress: true }));
    }
    else if (event.type === 'turn.ready') recorder.setCallAudioEnabled(true).then(() => {
      setState('listening', '正在听你说。');
      if (turnEndedBeforeReady) {
        turnEndedBeforeReady = false;
        void finishTurn();
      }
    });
    else if (event.type === 'transcript.partial') {
      const text = String(event.text || '').trim();
      setState('listening', text ? `正在识别：${text.slice(0, 36)}` : '正在识别你说的话…');
    }
    else if (event.type === 'transcript.final') { activeTranscript = event.text || ''; setState('thinking', '已听到，正在思考怎么回答。'); }
    else if (event.type === 'response.text') { activeReply = event.text || ''; setState('thinking', '叶筝正在组织回答…'); }
    else if (event.type === 'response.audio.start') setState('speaking', '叶筝正在回答，你可以随时插话。');
    else if (event.type === 'response.done') { onTurn(activeTranscript, activeReply); setState('ready', '回答结束，正在等待你继续说话。'); }
    else if (event.type === 'error') setState('ready', event.message || '实时语音暂时不可用。');
  };
  const connect = async () => {
    if (!enabled || !AudioContextImpl || !recorder?.connectCall || !recorder?.addCallListener || !recorder?.addVadListener) { setState('idle', '实时语音仅支持 Luminous Android 应用。', { showProgress: true }); return; }
    setState('connecting', '正在连接实时通话…');
    try {
      context = new AudioContextImpl(); await context.resume?.();
      callListener = await recorder.addCallListener(handleCallEvent);
      vadListener = await recorder.addVadListener(handleVad);
      await recorder.connectCall();
    } catch (error) { close({ message: '无法开始实时语音，请重试。', showProgress: true }); }
  };
  const click = () => { if (state === 'idle') void connect(); else close({ message: '实时通话已结束。', showProgress: true }); };
  button?.addEventListener('click', click); setState('idle');
  return Object.freeze({ setEnabled(value) { enabled = value !== false; if (!enabled) close(); else setState(state); }, destroy() { close(); button?.removeEventListener('click', click); } });
}
