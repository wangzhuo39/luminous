import { AppError, appErrorFromStatus } from '../shared/errors.js';

const DEFAULT_TIMEOUT_MS = 30_000;

const browserDependencies = {
  fetchImpl: (...args) => window.fetch(...args),
  isOnline: () => navigator.onLine,
  setTimer: (callback, delay) => window.setTimeout(callback, delay),
  clearTimer: (timerId) => window.clearTimeout(timerId),
  randomUUID: () => globalThis.crypto?.randomUUID?.()
    || `fallback-${Date.now()}-${Math.random().toString(16).slice(2)}`,
};

function assertRelativeApiPath(path) {
  if (typeof path !== 'string' || !path.startsWith('/api/') || path.startsWith('//')) {
    throw new AppError('validation');
  }
}

export function resolveApiUrl(path, windowRef = typeof window === 'undefined' ? null : window) {
  assertRelativeApiPath(path);
  const base = typeof windowRef?.__LUMINOUS_API_BASE__ === 'string'
    ? windowRef.__LUMINOUS_API_BASE__.trim().replace(/\/$/, '')
    : '';
  return base ? `${base}${path}` : path;
}

export async function requestJson(path, options = {}) {
  assertRelativeApiPath(path);

  const dependencies = { ...browserDependencies, ...(options.dependencies ?? {}) };
  if (typeof dependencies.fetchImpl !== 'function') {
    throw new AppError('unknown');
  }
  if (dependencies.isOnline() === false) {
    throw new AppError('offline');
  }

  const timeoutMs = Number.isFinite(options.timeoutMs) && options.timeoutMs > 0
    ? options.timeoutMs
    : DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  let timedOut = false;
  let callerCancelled = false;

  const handleCallerAbort = () => {
    callerCancelled = true;
    controller.abort();
  };

  if (options.signal?.aborted) {
    throw new AppError('cancelled');
  }
  options.signal?.addEventListener('abort', handleCallerAbort, { once: true });

  const timeoutId = dependencies.setTimer(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const headers = { Accept: 'application/json' };
  const apiToken = typeof window !== 'undefined' && typeof window.__LUMINOUS_API_TOKEN__ === 'string'
    ? window.__LUMINOUS_API_TOKEN__.trim()
    : '';
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
  const method = String(options.method ?? 'GET').toUpperCase();
  const mutation = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  const idempotencyKey = options.idempotencyKey
    || (mutation && typeof dependencies.randomUUID === 'function'
      ? `luminous-${dependencies.randomUUID()}` : '');
  if (idempotencyKey) headers['Idempotency-Key'] = String(idempotencyKey).slice(0, 128);
  const requestOptions = {
    method,
    headers,
    signal: controller.signal,
  };

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    requestOptions.body = JSON.stringify(options.body);
  }

  try {
    const requestUrl = resolveApiUrl(path);
    requestOptions.credentials = requestUrl === path ? 'same-origin' : 'include';
    let response;
    try {
      response = await dependencies.fetchImpl(requestUrl, requestOptions);
    } catch (firstError) {
      if (
        !mutation
        || timedOut
        || callerCancelled
        || options.signal?.aborted
        || dependencies.isOnline() === false
      ) throw firstError;
      response = await dependencies.fetchImpl(requestUrl, requestOptions);
    }
    if (!response.ok) {
      if (response.status === 401 && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('luminous:auth-required'));
      }
      throw appErrorFromStatus(response.status);
    }
    if (response.status === 204) {
      return null;
    }

    const responseText = await response.text();
    if (!responseText.trim()) {
      return null;
    }

    try {
      return JSON.parse(responseText);
    } catch (error) {
      throw new AppError('server', { status: response.status, cause: error });
    }
  } catch (error) {
    if (error instanceof AppError) {
      throw error;
    }
    if (timedOut) {
      throw new AppError('timeout', { cause: error });
    }
    if (callerCancelled || options.signal?.aborted) {
      throw new AppError('cancelled', { cause: error });
    }
    throw new AppError('offline', { cause: error instanceof Error ? error : undefined });
  } finally {
    dependencies.clearTimer(timeoutId);
    options.signal?.removeEventListener('abort', handleCallerAbort);
  }
}
