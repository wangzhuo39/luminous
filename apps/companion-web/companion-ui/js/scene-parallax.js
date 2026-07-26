const LAYERS = Object.freeze([
  { selector: '.solarium-architecture', x: -15, y: -10 },
  { selector: '.volumetric-rays', x: -30, y: -20 },
  { selector: '.companion-container', x: 10, y: 5 },
  { selector: '.crystal-prisms', x: 40, y: 20 },
]);

const LERP = 0.08;
const SETTLED_EPSILON = 0.002;

export function initSceneParallax(scene, body = document.body) {
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const layers = LAYERS.map((layer) => ({
    ...layer,
    node: scene?.querySelector(layer.selector) ?? null,
  })).filter((layer) => layer.node);

  let targetX = 0;
  let targetY = 0;
  let currentX = 0;
  let currentY = 0;
  let frameId = 0;
  let suspended = false;

  const motionBlocked = () => (
    suspended
    ||
    media.matches
    || body.dataset.reducedMotion === 'true'
    || window.matchMedia('(pointer: coarse)').matches
  );

  const paint = () => {
    frameId = 0;
    if (motionBlocked() || document.hidden) {
      currentX = 0;
      currentY = 0;
      targetX = 0;
      targetY = 0;
    } else {
      currentX += (targetX - currentX) * LERP;
      currentY += (targetY - currentY) * LERP;
    }

    for (const layer of layers) {
      layer.node.style.setProperty('--parallax-x', `${(currentX * layer.x).toFixed(2)}px`);
      layer.node.style.setProperty('--parallax-y', `${(currentY * layer.y).toFixed(2)}px`);
    }

    if (Math.abs(targetX - currentX) > SETTLED_EPSILON || Math.abs(targetY - currentY) > SETTLED_EPSILON) {
      frameId = requestAnimationFrame(paint);
    }
  };

  const schedulePaint = () => {
    if (!frameId) frameId = requestAnimationFrame(paint);
  };

  const reset = () => {
    targetX = 0;
    targetY = 0;
    schedulePaint();
  };

  const handlePointerMove = (event) => {
    if (motionBlocked()) {
      reset();
      return;
    }
    targetX = Math.max(-1, Math.min(1, (event.clientX / window.innerWidth) * 2 - 1));
    targetY = Math.max(-1, Math.min(1, (event.clientY / window.innerHeight) * 2 - 1));
    schedulePaint();
  };

  const handleVisibility = () => {
    if (document.hidden) reset();
  };

  const observer = new MutationObserver(reset);
  observer.observe(body, { attributes: true, attributeFilter: ['data-reduced-motion'] });
  window.addEventListener('pointermove', handlePointerMove, { passive: true });
  document.documentElement.addEventListener('pointerleave', reset);
  document.addEventListener('visibilitychange', handleVisibility);
  media.addEventListener?.('change', reset);

  return {
    setSuspended(nextSuspended) {
      suspended = Boolean(nextSuspended);
      reset();
    },
    destroy() {
      if (frameId) cancelAnimationFrame(frameId);
      observer.disconnect();
      window.removeEventListener('pointermove', handlePointerMove);
      document.documentElement.removeEventListener('pointerleave', reset);
      document.removeEventListener('visibilitychange', handleVisibility);
      media.removeEventListener?.('change', reset);
      for (const layer of layers) {
        layer.node.style.removeProperty('--parallax-x');
        layer.node.style.removeProperty('--parallax-y');
      }
    },
  };
}
