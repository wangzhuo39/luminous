import { initSceneBackgroundMenu } from './scene-background.js';

const headerMarkup = `
  <header class="top-scene-header" aria-label="场景与陪伴者状态">
    <div class="scene-clock-block">
      <div class="scene-clock-line">
        <time class="scene-clock" datetime="" data-hook="scene-clock">--:--</time>
        <span class="scene-crescent" aria-hidden="true"></span>
        <span class="scene-period" data-hook="scene-period">此刻</span>
      </div>
      <p class="scene-weather">外面有点凉，记得添衣</p>
    </div>
    <div class="companion-identity">
      <div>
        <p class="companion-name">叶筝</p>
        <p class="companion-presence"><span aria-hidden="true"></span>在这里</p>
      </div>
      <button type="button" class="scene-more" aria-label="更多选项" aria-haspopup="true" aria-expanded="false" aria-controls="scene-menu" data-hook="scene-menu-trigger">
        <span></span><span></span><span></span>
      </button>
      <div id="scene-menu" class="scene-menu" data-hook="scene-menu" hidden>
        <p class="scene-menu__title">场景背景</p>
        <div class="scene-background-options" role="radiogroup" aria-label="选择场景背景">
          <button type="button" class="scene-background-option scene-background-option--quiet" role="radio" aria-checked="true" data-background-id="quiet-night">
            <span class="scene-background-option__preview" aria-hidden="true"></span>
            <span>静夜窗前</span>
          </button>
          <button type="button" class="scene-background-option scene-background-option--crystal" role="radio" aria-checked="false" data-background-id="crystal-sanctuary">
            <span class="scene-background-option__preview" aria-hidden="true"></span>
            <span>冰晶圣殿</span>
          </button>
        </div>
      </div>
    </div>
  </header>
`;

const statusMarkup = `
  <section class="companion-status-panel" aria-label="叶筝此刻的状态">
    <div class="companion-status-frame" aria-hidden="true">
      <img class="status-frame-art" src="assets/generated/status-frame-ornate.png" alt="">
      <img class="status-frame-cap status-frame-cap-left" src="assets/frames/status-left.svg" alt="">
      <div class="status-frame-middle"></div>
      <img class="status-frame-cap status-frame-cap-right" src="assets/frames/status-right.svg" alt="">
      <img class="status-frame-jewel" src="assets/frames/status-center.svg" alt="">
    </div>
    <div class="companion-status-content">
      <article class="companion-status-item">
        <span class="status-orb status-orb-heart" aria-hidden="true"><img class="status-orb-art" src="assets/generated/status-heart-orb.png" alt=""></span>
        <span class="status-copy"><strong data-hook="companion-heart-label">心跳平稳</strong><small data-hook="companion-heart-detail">72 次/分</small></span>
      </article>
      <article class="companion-status-item">
        <span class="status-orb status-orb-rain" aria-hidden="true"><img class="status-orb-art" src="assets/generated/status-rain-orb.png" alt=""></span>
        <span class="status-copy"><strong data-hook="companion-activity-label">正在看雨</strong><small data-hook="companion-activity-detail">窗边 · 雨声轻轻</small></span>
      </article>
      <article class="companion-status-item">
        <span class="status-orb status-orb-moon" aria-hidden="true"><img class="status-orb-art" src="assets/generated/status-quiet-orb.png" alt=""></span>
        <span class="status-copy"><strong data-hook="companion-mood-label">有点安静</strong><small data-hook="companion-mood-detail">心情平静</small></span>
      </article>
    </div>
  </section>
`;

function elementFrom(markup) {
  const template = document.createElement('template');
  template.innerHTML = markup.trim();
  return template.content.firstElementChild;
}

function bindStatusArtworkFallback(scene) {
  const frame = scene.querySelector('.companion-status-frame');
  const artwork = frame?.querySelector('.status-frame-art');
  if (!frame || !artwork || frame.dataset.artworkBound === 'true') return;

  frame.dataset.artworkBound = 'true';
  const markReady = () => frame.classList.add('is-artwork-ready');
  if (artwork.complete && artwork.naturalWidth > 0) markReady();
  else artwork.addEventListener('load', markReady, { once: true });
}

function bindPortalArtworkFallback(scene) {
  scene.querySelectorAll('.portal-entry-art').forEach((artwork) => {
    const shape = artwork.closest('.portal-object__shape');
    if (!shape || artwork.dataset.artworkBound === 'true') return;

    artwork.dataset.artworkBound = 'true';
    const markReady = () => {
      if (artwork.dataset.fallbackApplied !== 'true') shape.classList.add('is-artwork-ready');
    };
    artwork.addEventListener('load', markReady, { once: true });
    artwork.addEventListener('error', () => {
      const fallback = artwork.dataset.fallbackSrc;
      if (!fallback || artwork.dataset.fallbackApplied === 'true') return;
      artwork.dataset.fallbackApplied = 'true';
      artwork.src = fallback;
      shape.classList.add('is-artwork-fallback');
    }, { once: true });
    if (artwork.complete && artwork.naturalWidth > 0) markReady();
  });
}

export function mountMainSceneShell(scene) {
  if (!scene) return { destroy() {} };

  if (!scene.querySelector('.top-scene-header')) {
    const background = scene.querySelector('.scene-background');
    background?.insertAdjacentElement('afterend', elementFrom(headerMarkup));
  }

  if (!scene.querySelector('.companion-status-panel')) {
    const dialogue = scene.querySelector('[data-hook="dialogue-stream"]');
    dialogue?.insertAdjacentElement('afterend', elementFrom(statusMarkup));
  }

  bindStatusArtworkFallback(scene);
  bindPortalArtworkFallback(scene);
  return initSceneBackgroundMenu(scene);
}
