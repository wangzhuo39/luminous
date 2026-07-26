import { AppError, appErrorFromStatus } from '../shared/errors.js';

const DEFAULT_TIMEOUT_MS = 30_000;

const browserDependencies = {
  fetchImpl: (...args) => window.fetch(...args),
  isOnline: () => navigator.onLine,
  setTimer: (callback, delay) => window.setTimeout(callback, delay),
  clearTimer: (timerId) => window.clearTimeout(timerId),
};

function assertRelativeApiPath(path) {
  if (typeof path !== 'string' || !path.startsWith('/api/') || path.startsWith('//')) {
    throw new AppError('validation');
  }
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
  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = String(options.idempotencyKey).slice(0, 128);
  }
  const requestOptions = {
    method: options.method ?? 'GET',
    headers,
    signal: controller.signal,
  };

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    requestOptions.body = JSON.stringify(options.body);
  }

  try {
    const response = await dependencies.fetchImpl(path, requestOptions);
    if (!response.ok) {
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
