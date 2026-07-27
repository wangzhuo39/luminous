const headerMarkup = `
  <header class="top-scene-header" aria-label="场景与陪伴者状态">
    <div class="scene-clock-block">
      <div class="scene-clock-line">
        <time class="scene-clock" datetime="20:41">20:41</time>
        <span class="scene-crescent" aria-hidden="true"></span>
        <span class="scene-period">夜晚</span>
      </div>
      <p class="scene-weather">外面有点凉，记得添衣</p>
    </div>
    <div class="companion-identity">
      <div>
        <p class="companion-name">叶筝</p>
        <p class="companion-presence"><span aria-hidden="true"></span>在这里</p>
      </div>
      <button type="button" class="scene-more" aria-label="更多选项">
        <span></span><span></span><span></span>
      </button>
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
        <span class="status-copy"><strong>心跳平稳</strong><small>72 次/分</small></span>
      </article>
      <article class="companion-status-item">
        <span class="status-orb status-orb-rain" aria-hidden="true"><img class="status-orb-art" src="assets/generated/status-rain-orb.png" alt=""></span>
        <span class="status-copy"><strong>正在看雨</strong><small>窗边 · 雨声轻轻</small></span>
      </article>
      <article class="companion-status-item">
        <span class="status-orb status-orb-moon" aria-hidden="true"><img class="status-orb-art" src="assets/generated/status-quiet-orb.png" alt=""></span>
        <span class="status-copy"><strong>有点安静</strong><small>心情平静</small></span>
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
  if (!scene) return;

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
}
