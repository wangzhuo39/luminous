const SESSION_PATH = '/api/auth/session';
const LOGIN_PATH = '/api/auth/login';
const LOGOUT_PATH = '/api/auth/logout';

export function initAuthGate({
  runtimeMode,
  documentRef = document,
  windowRef = window,
  fetchImpl = (...args) => windowRef.fetch(...args),
} = {}) {
  const body = documentRef.body;
  const gate = documentRef.querySelector('[data-hook="auth-gate"]');
  const form = documentRef.querySelector('[data-hook="auth-form"]');
  const input = documentRef.querySelector('[data-hook="auth-code"]');
  const submit = documentRef.querySelector('[data-hook="auth-submit"]');
  const error = documentRef.querySelector('[data-hook="auth-error"]');
  const logoutSection = documentRef.querySelector('[data-hook="auth-logout-section"]');
  const logoutButton = documentRef.querySelector('[data-hook="auth-logout"]');
  const logoutStatus = documentRef.querySelector('[data-hook="auth-logout-status"]');
  let started = false;
  let destroyed = false;
  let resolveReady;
  let rejectReady;
  const apiUrl = (path) => {
    const base = typeof windowRef.__LUMINOUS_API_BASE__ === 'string'
      ? windowRef.__LUMINOUS_API_BASE__.trim().replace(/\/$/, '')
      : '';
    return base ? `${base}${path}` : path;
  };

  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });

  const setGateState = (state, message = '') => {
    body.dataset.authStatus = state;
    if (gate) gate.hidden = state !== 'required';
    if (error) {
      error.textContent = message;
      error.hidden = !message;
    }
  };

  const focusInput = () => {
    windowRef.setTimeout(() => input?.focus({ preventScroll: true }), 0);
  };

  const showRequired = (message = '') => {
    setGateState('required', message);
    focusInput();
  };

  const complete = () => {
    if (destroyed) return;
    setGateState('authenticated');
    resolveReady({ authenticated: true });
  };

  const submitLogin = async (event) => {
    event?.preventDefault();
    if (!input || !submit) return;
    const accessCode = input.value.trim();
    if (!accessCode) {
      showRequired('请输入进入邀请码。');
      return;
    }
    submit.disabled = true;
    setGateState('required');
    try {
      const loginUrl = apiUrl(LOGIN_PATH);
      const response = await fetchImpl(loginUrl, {
        method: 'POST',
        credentials: loginUrl === LOGIN_PATH ? 'same-origin' : 'include',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_code: accessCode }),
      });
      if (!response.ok) {
        showRequired(response.status === 401 ? '这个邀请码暂时无法进入。' : '连接暂时不稳定，请稍后再试。');
        return;
      }
      input.value = '';
      if (started) {
        windowRef.location.reload();
      } else {
        complete();
      }
    } catch {
      showRequired('暂时无法连接，请检查网络后重试。');
    } finally {
      submit.disabled = false;
    }
  };

  const onAuthRequired = () => {
    if (!started || destroyed) return;
    showRequired('登录已过期，请再次输入邀请码。');
  };

  const logout = async (event) => {
    event?.preventDefault?.();
    if (runtimeMode === 'fixture' || destroyed || logoutButton?.disabled) return false;
    if (windowRef.navigator?.onLine === false) {
      if (logoutStatus) logoutStatus.textContent = '需要联网后才能安全退出此设备。';
      return false;
    }
    if (logoutButton) logoutButton.disabled = true;
    if (logoutStatus) logoutStatus.textContent = '正在关闭此设备上的会话…';
    try {
      const logoutUrl = apiUrl(LOGOUT_PATH);
      const response = await fetchImpl(logoutUrl, {
        method: 'POST',
        credentials: logoutUrl === LOGOUT_PATH ? 'same-origin' : 'include',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok && response.status !== 401) throw new Error(`logout failed: ${response.status}`);
      try { await windowRef.LuminousNative?.disableRealtime?.(); } catch { /* Server logout still takes precedence. */ }
      try { windowRef.sessionStorage?.clear?.(); } catch { /* Storage can be unavailable. */ }
      setGateState('checking');
      windowRef.location.reload();
      return true;
    } catch {
      if (logoutStatus) logoutStatus.textContent = '暂时无法安全退出，请检查网络后重试。';
      return false;
    } finally {
      if (logoutButton) logoutButton.disabled = false;
    }
  };

  form?.addEventListener('submit', submitLogin);
  logoutButton?.addEventListener('click', logout);
  windowRef.addEventListener?.('luminous:auth-required', onAuthRequired);
  if (logoutSection) logoutSection.hidden = runtimeMode === 'fixture';

  const bootstrap = async () => {
    if (runtimeMode === 'fixture') {
      setGateState('bypassed');
      complete();
      return;
    }
    setGateState('checking');
    if (windowRef.navigator?.onLine === false) {
      complete();
      return;
    }
    try {
      const sessionUrl = apiUrl(SESSION_PATH);
      const response = await fetchImpl(sessionUrl, {
        credentials: sessionUrl === SESSION_PATH ? 'same-origin' : 'include',
        headers: { Accept: 'application/json' },
      });
      if (response.ok) {
        complete();
        return;
      }
      if (response.status === 401) {
        showRequired();
        return;
      }
      if (windowRef.navigator?.onLine === false) {
        complete();
        return;
      }
      showRequired('暂时无法确认登录状态，请稍后重试。');
    } catch {
      complete();
    }
  };

  const destroy = () => {
    destroyed = true;
    form?.removeEventListener('submit', submitLogin);
    logoutButton?.removeEventListener('click', logout);
    windowRef.removeEventListener?.('luminous:auth-required', onAuthRequired);
    rejectReady?.(new Error('auth gate destroyed'));
  };

  void bootstrap();
  return {
    ready,
    markStarted() { started = true; },
    logout,
    destroy,
  };
}
