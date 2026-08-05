export function initNativeNotifications({ documentRef = document, windowRef = window } = {}) {
  const section = documentRef.querySelector('[data-hook="native-notification-section"]');
  const button = documentRef.querySelector('[data-hook="native-notification-button"]');
  const status = documentRef.querySelector('[data-hook="native-notification-status"]');
  const native = windowRef.__LUMINOUS_NATIVE__ === true;
  if (section) section.hidden = !native;
  if (!native || !button) return Object.freeze({ destroy() {} });

  let destroyed = false;
  let currentState = null;
  const render = (state) => {
    if (destroyed) return;
    currentState = state;
    const localGranted = state?.local === 'granted';
    const realtimeEnabled = state?.realtime?.enabled === true;
    const realtimeStatus = state?.realtime?.status || 'stopped';
    button.disabled = false;
    button.textContent = !localGranted
      ? '开启 Android 通知'
      : realtimeEnabled ? '暂停实时陪伴' : '开启实时陪伴';
    if (status) {
      if (realtimeStatus === 'connected') status.textContent = '实时连接已建立；主动来信会立即抵达，后台同步负责漏信恢复。';
      else if (realtimeStatus === 'login_required') status.textContent = '实时连接正在等待登录；后台同步仍会保留来信。';
      else if (realtimeEnabled) status.textContent = '实时陪伴正在连接；系统会显示一条常驻状态通知。';
      else if (localGranted) status.textContent = '本地提醒已开启；主动来信由 App 后台定期同步到通知栏。';
      else status.textContent = '需要系统通知权限；提醒和主动来信会先保存在 App 内。';
    }
  };
  const refresh = () => windowRef.LuminousNativeReady
    ?.then(() => windowRef.LuminousNative?.permissionState())
    .then(render)
    .catch(() => render({ local: 'denied' }));
  const onClick = async () => {
    button.disabled = true;
    try {
      const operation = currentState?.realtime?.enabled
        ? windowRef.LuminousNative?.disableRealtime()
        : windowRef.LuminousNative?.enableNotifications();
      render(await operation);
    } catch {
      render({ local: 'denied', realtime: { enabled: false, status: 'stopped' } });
    }
  };
  button.addEventListener('click', onClick);
  const onNativeState = () => { void refresh(); };
  windowRef.addEventListener?.('luminous:native-notification-state', onNativeState);
  void refresh();
  return Object.freeze({
    destroy() {
      destroyed = true;
      button.removeEventListener('click', onClick);
      windowRef.removeEventListener?.('luminous:native-notification-state', onNativeState);
    },
  });
}
