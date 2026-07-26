import {
  beginInitialLoad,
  completeInitialLoad,
  failInitialLoad,
  getState,
} from './app-state.js';
import { loadCompanionState } from './adapters/api-adapter.js';

export function resolveRuntimeMode(locationLike) {
  const params = new URLSearchParams(locationLike?.search ?? '');
  return params.get('mode') === 'fixture' ? 'fixture' : 'api';
}

export function initCoreRuntime({
  mode,
  announce,
  onStateChange,
  dependencies,
  eventTarget = window,
  isOnline = () => navigator.onLine,
}) {
  let activeController = null;
  let requestVersion = 0;
  let destroyed = false;
  let hasReachedReady = false;
  let lastAnnouncement = '';

  function announceOnce(key, message) {
    if (lastAnnouncement === key) return;
    lastAnnouncement = key;
    announce(message);
  }

  async function retryStateLoad() {
    if (mode !== 'api' || destroyed) return false;

    requestVersion += 1;
    const currentVersion = requestVersion;
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;

    beginInitialLoad();
    announceOnce('loading', '正在靠近栖光。');
    onStateChange();

    try {
      const scene = await loadCompanionState({
        signal: controller.signal,
        dependencies,
      });
      if (destroyed || currentVersion !== requestVersion) return false;
      if (completeInitialLoad(scene)) {
        announceOnce('ready', hasReachedReady ? '连接已经恢复。' : '栖光已经在这里。');
        hasReachedReady = true;
        onStateChange();
        return true;
      }
    } catch (error) {
      if (destroyed || currentVersion !== requestVersion || error?.kind === 'cancelled') return false;
      failInitialLoad(error);
      const current = getState();
      announceOnce(
        current.appStatus,
        current.appError?.message ?? '连接暂时远了一些。',
      );
      onStateChange();
    } finally {
      if (currentVersion === requestVersion) activeController = null;
    }
    return false;
  }

  function handleOnline() {
    const current = getState();
    if (current.appStatus === 'offline' || current.appError?.retryable) {
      retryStateLoad();
    }
  }

  function handleOffline() {
    if (mode !== 'api' || destroyed) return;
    requestVersion += 1;
    activeController?.abort();
    activeController = null;
    failInitialLoad({ kind: 'offline', retryable: true });
    announceOnce('offline', '连接暂时远了一些。');
    onStateChange();
  }

  if (mode === 'api') {
    eventTarget.addEventListener('online', handleOnline);
    eventTarget.addEventListener('offline', handleOffline);
    if (isOnline() === false) handleOffline();
    else retryStateLoad();
  }

  return {
    retryStateLoad,
    destroy() {
      destroyed = true;
      requestVersion += 1;
      activeController?.abort();
      activeController = null;
      eventTarget.removeEventListener('online', handleOnline);
      eventTarget.removeEventListener('offline', handleOffline);
    },
  };
}
