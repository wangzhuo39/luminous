export function initPresentation(onStateChange) {
  const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

  function updateReducedMotion() {
    onStateChange('isReducedMotion', reducedMotionQuery.matches);
  }

  function updateKeyboardVisibility() {
    if (!window.visualViewport) {
      onStateChange('isKeyboardVisible', false);
      return;
    }

    const occludedHeight = window.innerHeight - window.visualViewport.height;
    onStateChange('isKeyboardVisible', occludedHeight > 150);
  }

  updateReducedMotion();
  updateKeyboardVisibility();
  reducedMotionQuery.addEventListener('change', updateReducedMotion);
  window.visualViewport?.addEventListener('resize', updateKeyboardVisibility);
}
