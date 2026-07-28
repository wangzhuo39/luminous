const SESSION_PATH = '/api/auth/session';
const LOGIN_PATH = '/api/auth/login';

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
  let started = false;
  let destroyed = false;
  let resolveReady;
  let rejectReady;

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
      const response = await fetchImpl(LOGIN_PATH, {
        method: 'POST',
        credentials: 'same-origin',
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

  form?.addEventListener('submit', submitLogin);
  windowRef.addEventListener?.('luminous:auth-required', onAuthRequired);

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
      const response = await fetchImpl(SESSION_PATH, {
        credentials: 'same-origin',
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
    windowRef.removeEventListener?.('luminous:auth-required', onAuthRequired);
    rejectReady?.(new Error('auth gate destroyed'));
  };

  void bootstrap();
  return {
    ready,
    markStarted() { started = true; },
    destroy,
  };
}
