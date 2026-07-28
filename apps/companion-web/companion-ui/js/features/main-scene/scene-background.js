export const SCENE_BACKGROUND_STORAGE_KEY = 'luminous.scene-background.v1';
export const DEFAULT_SCENE_BACKGROUND = 'quiet-night';
export const SCENE_BACKGROUND_IDS = Object.freeze([
  DEFAULT_SCENE_BACKGROUND,
  'crystal-sanctuary',
]);

export function normalizeSceneBackground(value) {
  return SCENE_BACKGROUND_IDS.includes(value) ? value : DEFAULT_SCENE_BACKGROUND;
}

export function loadSceneBackground(storage) {
  let storedValue = null;
  try {
    storedValue = storage?.getItem(SCENE_BACKGROUND_STORAGE_KEY) ?? null;
  } catch {
    return DEFAULT_SCENE_BACKGROUND;
  }

  const backgroundId = normalizeSceneBackground(storedValue);
  if (storedValue && storedValue !== backgroundId) {
    try { storage?.removeItem(SCENE_BACKGROUND_STORAGE_KEY); } catch { /* Storage can be unavailable. */ }
  }
  return backgroundId;
}

export function saveSceneBackground(storage, backgroundId) {
  const normalized = normalizeSceneBackground(backgroundId);
  try {
    storage?.setItem(SCENE_BACKGROUND_STORAGE_KEY, normalized);
    return true;
  } catch {
    return false;
  }
}

export function initSceneBackgroundMenu(scene, {
  root = document.documentElement,
  storage = window.localStorage,
  documentRef = document,
  windowRef = window,
} = {}) {
  const trigger = scene?.querySelector('[data-hook="scene-menu-trigger"]');
  const menu = scene?.querySelector('[data-hook="scene-menu"]');
  const options = [...(menu?.querySelectorAll('[data-background-id]') ?? [])];
  if (!trigger || !menu || options.length === 0) return { destroy() {} };

  const apply = (backgroundId, { persist = false } = {}) => {
    const normalized = normalizeSceneBackground(backgroundId);
    root.dataset.sceneBackground = normalized;
    options.forEach((option) => {
      option.setAttribute('aria-checked', String(option.dataset.backgroundId === normalized));
    });
    if (persist) saveSceneBackground(storage, normalized);
    return normalized;
  };

  const close = ({ restoreFocus = false } = {}) => {
    menu.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus) trigger.focus();
  };

  const open = () => {
    menu.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    options.find((option) => option.getAttribute('aria-checked') === 'true')?.focus();
  };

  const toggle = () => {
    if (menu.hidden) open();
    else close();
  };

  const handleMenuClick = (event) => {
    const option = event.target.closest('[data-background-id]');
    if (!option || !menu.contains(option)) return;
    apply(option.dataset.backgroundId, { persist: true });
    close({ restoreFocus: true });
  };

  const handleMenuKeydown = (event) => {
    const currentOption = event.target.closest('[data-background-id]');
    if (!currentOption || !menu.contains(currentOption)) return;
    const currentIndex = options.indexOf(currentOption);
    let nextIndex = null;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextIndex = (currentIndex + 1) % options.length;
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextIndex = (currentIndex - 1 + options.length) % options.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = options.length - 1;
    }
    if (nextIndex === null) return;
    event.preventDefault();
    const nextOption = options[nextIndex];
    apply(nextOption.dataset.backgroundId, { persist: true });
    nextOption.focus();
  };

  const handleDocumentClick = (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !trigger.contains(event.target)) close();
  };

  const handleKeydown = (event) => {
    if (event.key === 'Escape' && !menu.hidden) {
      event.preventDefault();
      close({ restoreFocus: true });
    }
  };

  const handleStorage = (event) => {
    if (event.key === SCENE_BACKGROUND_STORAGE_KEY) apply(event.newValue);
  };

  apply(loadSceneBackground(storage));
  trigger.addEventListener('click', toggle);
  menu.addEventListener('click', handleMenuClick);
  menu.addEventListener('keydown', handleMenuKeydown);
  documentRef.addEventListener('click', handleDocumentClick);
  documentRef.addEventListener('keydown', handleKeydown);
  windowRef.addEventListener('storage', handleStorage);

  return {
    apply,
    destroy() {
      trigger.removeEventListener('click', toggle);
      menu.removeEventListener('click', handleMenuClick);
      menu.removeEventListener('keydown', handleMenuKeydown);
      documentRef.removeEventListener('click', handleDocumentClick);
      documentRef.removeEventListener('keydown', handleKeydown);
      windowRef.removeEventListener('storage', handleStorage);
    },
  };
}
