import { getState, setActiveSpace } from './app-state.js';

export function initOverlays(dom, onStateChange, { onSpaceChange = setActiveSpace } = {}) {
  let lastFocusedPortal = null;
  const synchronizedClosures = new WeakSet();

  function restorePortalFocus() {
    lastFocusedPortal?.focus();
    lastFocusedPortal = null;
  }

  Object.values(dom.portals).forEach((portal) => {
    portal?.addEventListener('click', () => {
      lastFocusedPortal = portal;
      onSpaceChange(portal.dataset.space);
      onStateChange();
    });
  });

  Object.values(dom.dialogs).forEach((dialog) => {
    if (!dialog) {
      return;
    }

    dialog.querySelector('.dialog-close-btn')?.addEventListener('click', () => {
      dialog.close();
    });
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
    dialog.addEventListener('close', () => {
      if (synchronizedClosures.has(dialog)) {
        synchronizedClosures.delete(dialog);
        return;
      }
      if (getState().activeSpace !== null) {
        onSpaceChange(null);
        onStateChange();
      }
      restorePortalFocus();
    });
  });

  return function renderOverlays(activeSpace) {
    if (dom.body) {
      dom.body.dataset.activeSpace = activeSpace ?? 'none';
    }
    Object.entries(dom.portals).forEach(([space, portal]) => {
      const expanded = space === activeSpace;
      portal?.classList?.toggle('is-open', expanded);
      portal?.setAttribute?.('aria-expanded', String(expanded));
    });
    const targetDialog = dom.dialogs[activeSpace] ?? null;
    Object.values(dom.dialogs).forEach((dialog) => {
      if (dialog?.open && dialog !== targetDialog) {
        synchronizedClosures.add(dialog);
        dialog.close();
      }
    });
    if (targetDialog && !targetDialog.open) {
      targetDialog.showModal();
      const initialFocus = targetDialog.querySelector('.dialog-close-btn')
        ?? targetDialog.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      initialFocus?.focus({ preventScroll: true });
    }
  };
}
