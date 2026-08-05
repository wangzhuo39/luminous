function installedDisplayMode(windowRef, navigatorRef) {
  return navigatorRef.standalone === true
    || windowRef.matchMedia?.('(display-mode: standalone)').matches === true;
}

export function initPwaExperience(dom, {
  windowRef = window,
  navigatorRef = navigator,
  onStateChange = () => {},
  isBusy = () => false,
  reload = () => windowRef.location.reload(),
} = {}) {
  let installPrompt = null;
  let waitingWorker = null;
  let updating = false;
  let reloading = false;
  let registration = null;
  let destroyed = false;
  let online = navigatorRef.onLine !== false;
  const cleanup = [];

  const listen = (target, type, handler, options) => {
    target?.addEventListener?.(type, handler, options);
    cleanup.push(() => target?.removeEventListener?.(type, handler, options));
  };

  const notify = () => {
    if (!destroyed) onStateChange();
  };

  const exposeWaitingWorker = (worker) => {
    if (!worker || !navigatorRef.serviceWorker?.controller) return;
    waitingWorker = worker;
    notify();
  };

  const observeInstallingWorker = (worker) => {
    if (!worker) return;
    const handleState = () => {
      if (worker.state === 'installed') exposeWaitingWorker(registration?.waiting || worker);
    };
    listen(worker, 'statechange', handleState);
    handleState();
  };

  const observeRegistration = (value) => {
    registration = value;
    if (value.waiting) exposeWaitingWorker(value.waiting);
    listen(value, 'updatefound', () => observeInstallingWorker(value.installing));
    observeInstallingWorker(value.installing);
  };

  const handleInstallAvailable = (event) => {
    event.preventDefault();
    if (installedDisplayMode(windowRef, navigatorRef)) return;
    installPrompt = event;
    notify();
  };
  const handleInstalled = () => {
    installPrompt = null;
    notify();
  };
  const handleControllerChange = () => {
    if (!updating || reloading) return;
    reloading = true;
    reload();
  };
  const handleOnline = () => { online = true; notify(); };
  const handleOffline = () => { online = false; notify(); };

  listen(windowRef, 'beforeinstallprompt', handleInstallAvailable);
  listen(windowRef, 'appinstalled', handleInstalled);
  listen(windowRef, 'online', handleOnline);
  listen(windowRef, 'offline', handleOffline);
  listen(navigatorRef.serviceWorker, 'controllerchange', handleControllerChange);

  dom.installButton?.addEventListener('click', async () => {
    const prompt = installPrompt;
    if (!prompt) return;
    installPrompt = null;
    notify();
    try {
      await prompt.prompt();
      await prompt.userChoice;
    } catch { /* Browser owns install failures; no permission or retry loop. */ }
    notify();
  });

  dom.updateButton?.addEventListener('click', () => {
    if (!waitingWorker || updating || isBusy()) return;
    updating = true;
    waitingWorker.postMessage({ type: 'SKIP_WAITING' });
    notify();
  });

  const nativeRuntime = windowRef.__LUMINOUS_NATIVE__ === true;
  const ready = !nativeRuntime && navigatorRef.serviceWorker?.register
    ? navigatorRef.serviceWorker.register('./service-worker.js', { scope: './' })
      .then((value) => { observeRegistration(value); return value; })
      .catch(() => null)
    : Promise.resolve(null);

  return Object.freeze({
    ready,
    render() {
      if (dom.body) dom.body.dataset.network = online ? 'online' : 'offline';
      const installVisible = Boolean(installPrompt) && !installedDisplayMode(windowRef, navigatorRef);
      if (dom.installSection) dom.installSection.hidden = !installVisible;
      if (dom.installButton) dom.installButton.disabled = !installVisible;
      const updateVisible = Boolean(waitingWorker);
      if (dom.updateButton) {
        dom.updateButton.hidden = !updateVisible;
        dom.updateButton.disabled = updating || isBusy();
        dom.updateButton.dataset.state = updating ? 'updating' : updateVisible ? 'ready' : 'hidden';
      }
      if (dom.updateText) dom.updateText.textContent = updating ? '正在推开窗...' : '窗外有新的晨光';
    },
    getState() {
      return Object.freeze({ installAvailable: Boolean(installPrompt), updateAvailable: Boolean(waitingWorker), updating });
    },
    destroy() {
      destroyed = true;
      cleanup.splice(0).forEach((dispose) => dispose());
    },
  });
}
