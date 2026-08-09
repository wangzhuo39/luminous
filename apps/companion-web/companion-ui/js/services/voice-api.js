import { resolveApiUrl } from './api-client.js';

const VOICE_TIMEOUT_MS = 65_000;

export class VoiceApiError extends Error {
  constructor(code = 'voice_failed', message = '语音处理失败，请重试。', retryable = true) {
    super(message);
    this.name = 'VoiceApiError';
    this.code = code;
    this.retryable = retryable;
  }
}

function authHeaders() {
  const headers = {};
  const token = typeof window !== 'undefined' && typeof window.__LUMINOUS_API_TOKEN__ === 'string'
    ? window.__LUMINOUS_API_TOKEN__.trim() : '';
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

function nativeVoiceBridge(dependencies) {
  if (dependencies.nativeBridge !== undefined) return dependencies.nativeBridge;
  if (typeof window === 'undefined' || window.__LUMINOUS_NATIVE__ !== true) return null;
  return window.LuminousNative ?? null;
}

function base64AudioBlob(value, contentType = 'audio/mpeg') {
  if (typeof value !== 'string' || !value) {
    throw new VoiceApiError('invalid_audio', '语音服务返回了无效音频。', false);
  }
  try {
    const binary = globalThis.atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return new Blob([bytes], { type: contentType || 'audio/mpeg' });
  } catch (error) {
    throw new VoiceApiError('invalid_audio', '语音服务返回了无效音频。', false, { cause: error });
  }
}

async function voiceFetch(path, options = {}, dependencies = {}) {
  const fetchImpl = dependencies.fetchImpl ?? ((...args) => window.fetch(...args));
  const controller = new AbortController();
  const timeout = (dependencies.setTimer ?? window.setTimeout)(() => controller.abort(), VOICE_TIMEOUT_MS);
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  try {
    const url = resolveApiUrl(path);
    const response = await fetchImpl(url, {
      ...options,
      credentials: url === path ? 'same-origin' : 'include',
      headers: { ...authHeaders(), ...(options.headers ?? {}) },
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = {};
      try { detail = await response.json(); } catch { detail = {}; }
      const error = detail?.error ?? {};
      throw new VoiceApiError(error.code, error.message, error.retryable !== false);
    }
    return response;
  } catch (error) {
    if (error instanceof VoiceApiError) throw error;
    if (options.signal?.aborted) throw new VoiceApiError('cancelled', '请求已取消。', false);
    if (controller.signal.aborted) throw new VoiceApiError('timeout', '语音处理超时，请重试。');
    throw new VoiceApiError('offline', '暂时无法连接语音服务。');
  } finally {
    (dependencies.clearTimer ?? window.clearTimeout)(timeout);
    options.signal?.removeEventListener('abort', abort);
  }
}

export function createVoiceApi(dependencies = {}) {
  return Object.freeze({
    async transcribe(blob, { durationMs, filename = 'recording.wav', signal } = {}) {
      const nativeBridge = nativeVoiceBridge(dependencies);
      if (nativeBridge?.voice?.transcribeMessage) {
        if (signal?.aborted) throw new VoiceApiError('cancelled', '请求已取消。', false);
        try {
          return await nativeBridge.voice.transcribeMessage();
        } catch (error) {
          throw new VoiceApiError('voice_failed', error?.message || '语音处理失败，请重试。');
        }
      }
      const response = await voiceFetch('/api/voice/transcriptions', {
        method: 'POST', body: blob, signal,
        headers: {
          'Content-Type': blob.type || 'audio/wav',
          'X-Audio-Duration-Ms': String(Math.round(durationMs || 0)),
          'X-Audio-Filename': filename,
        },
      }, dependencies);
      return response.json();
    },
    async synthesize(text, { voiceId, speakingRate, signal } = {}) {
      const nativeBridge = nativeVoiceBridge(dependencies);
      if (nativeBridge?.synthesizeVoice) {
        if (signal?.aborted) throw new VoiceApiError('cancelled', '请求已取消。', false);
        const response = await nativeBridge.synthesizeVoice({ text, voiceId, speakingRate });
        if (signal?.aborted) throw new VoiceApiError('cancelled', '请求已取消。', false);
        return base64AudioBlob(response?.data, response?.contentType);
      }
      const response = await voiceFetch('/api/voice/speech', {
        method: 'POST', signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice_id: voiceId, speaking_rate: speakingRate }),
      }, dependencies);
      return response.blob();
    },
  });
}

export const voiceApi = createVoiceApi();
