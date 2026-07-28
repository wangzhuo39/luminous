import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:8000';
const outputDir = new URL(
  '../../docs/front_design/acceptance/crystal-solarium-v2/',
  import.meta.url,
);

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

async function collectErrors(page) {
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function openToday(page) {
  await page.getByRole('button', { name: '打开今日摘要' }).click();
  await page.locator('#today-overlay[open]').waitFor();
}

async function openSpace(page, buttonName, dialogSelector) {
  await page.getByRole('button', { name: buttonName }).click();
  await page.locator(`${dialogSelector}[open]`).waitFor();
  await page.waitForTimeout(620);
}

async function closeSpace(page, dialogSelector) {
  await page.locator(`${dialogSelector} .dialog-close-btn`).click();
  await page.locator(dialogSelector).waitFor({ state: 'hidden' });
}

async function desktopAcceptance() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = await collectErrors(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'networkidle' });

  const scene = await page.evaluate(() => {
    const architecture = document.querySelector('.solarium-architecture');
    const rays = document.querySelector('.volumetric-rays');
    const prism = document.querySelector('.prism-left');
    const input = document.querySelector('.input-wrapper');
    const inputArtwork = document.querySelector('.input-frame-art');
    const environment = document.querySelector('.solarium-environment');
    const vault = document.querySelector('.solarium-vault');
    const vaultFrame = document.querySelector('.vault-frame-major');
    const todayShape = document.querySelector('.portal-time-shard');
    const privacyShape = document.querySelector('.portal-frost-pull');
    const letterShape = document.querySelector('.portal-letter');
    const portalArtwork = [...document.querySelectorAll('.portal-entry-art')];
    return {
      solarPhase: document.querySelector('.scene-container')?.dataset.solarPhase,
      environmentTone: document.querySelector('.scene-container')?.dataset.environmentTone,
      sceneBackground: getComputedStyle(document.querySelector('.scene-background')).backgroundImage,
      rayFocus: getComputedStyle(document.querySelector('.scene-container')).getPropertyValue('--ray-focus').trim(),
      breathPeriod: getComputedStyle(document.querySelector('.scene-container')).getPropertyValue('--breath-period').trim(),
      decorationHidden: environment?.getAttribute('aria-hidden'),
      perspective: getComputedStyle(document.querySelector('.scene-container')).perspective,
      architectureImage: getComputedStyle(architecture).backgroundImage,
      architectureOpacity: Number(getComputedStyle(architecture).opacity),
      vaultPathCount: vault?.querySelectorAll('path').length ?? 0,
      vaultFrameStroke: getComputedStyle(vaultFrame).stroke,
      todayShapeBackground: getComputedStyle(todayShape).backgroundImage,
      todayShapeClip: getComputedStyle(todayShape).clipPath,
      portalArtwork: portalArtwork.map((image) => ({
        src: image.getAttribute('src'),
        width: image.naturalWidth,
        height: image.naturalHeight,
      })),
      privacyShapeFilter: getComputedStyle(privacyShape).backdropFilter,
      letterShapeClip: getComputedStyle(letterShape).clipPath,
      raysBlend: getComputedStyle(rays).mixBlendMode,
      prismFilter: getComputedStyle(prism).backdropFilter,
      prismClip: getComputedStyle(prism).clipPath,
      inputFilter: getComputedStyle(inputArtwork).filter,
      inputBorderTop: getComputedStyle(input).borderTopColor,
      horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    };
  });
  assert.equal(scene.solarPhase, 'dawn');
  assert.equal(scene.environmentTone, 'calm');
  assert.ok(Number(scene.rayFocus) > 0);
  assert.ok(scene.breathPeriod.endsWith('s'));
  assert.equal(scene.decorationHidden, 'true');
  assert.notEqual(scene.perspective, 'none');
  assert.equal(scene.architectureImage, 'none');
  assert.ok(scene.architectureOpacity > 0.8);
  assert.ok(scene.vaultPathCount >= 12, JSON.stringify(scene));
  assert.notEqual(scene.vaultFrameStroke, 'none');
  assert.notEqual(scene.vaultFrameStroke, 'rgba(0, 0, 0, 0)');
  assert.equal(scene.todayShapeBackground, 'none');
  assert.notEqual(scene.todayShapeClip, 'none');
  assert.deepEqual(scene.portalArtwork, [
    { src: 'assets/generated/today.png', width: 1024, height: 1024 },
    { src: 'assets/generated/memory.png', width: 1024, height: 1024 },
    { src: 'assets/generated/heart.png', width: 1024, height: 1024 },
    { src: 'assets/generated/letter.png', width: 1024, height: 1024 },
  ]);
  assert.notEqual(scene.privacyShapeFilter, 'none');
  assert.notEqual(scene.letterShapeClip, 'none');
  assert.equal(scene.raysBlend, 'screen');
  assert.notEqual(scene.prismFilter, 'none');
  assert.notEqual(scene.prismClip, 'none');
  assert.notEqual(scene.inputFilter, 'none');
  assert.notEqual(scene.inputBorderTop, 'rgba(0, 0, 0, 0)');
  assert.ok(scene.horizontalOverflow <= 1, JSON.stringify(scene));

  await page.mouse.move(1360, 120);
  await page.waitForTimeout(260);
  const parallaxX = await page.locator('.crystal-prisms').evaluate((node) => (
    getComputedStyle(node).getPropertyValue('--parallax-x').trim()
  ));
  assert.notEqual(parallaxX, '0.00px');
  await page.screenshot({
    path: new URL('desktop-scene.png', outputDir).pathname,
    fullPage: true,
  });

  const nightEnvironment = await page.evaluate(async () => {
    const { applyEnvironment, deriveEnvironment, renderMemoryCrystals } = await import('./js/scene-environment.js');
    const environment = deriveEnvironment(
      { tone: 'quiet', activityPresence: 'none', memoryCount: 9, outboxUnread: true },
      new Date(2026, 6, 26, 22, 15),
    );
    applyEnvironment(document.querySelector('#luminous-scene'), environment);
    renderMemoryCrystals(document.querySelector('[data-hook="memory-crystal-field"]'), environment.crystalCount);
    return {
      ...environment,
      background: getComputedStyle(document.querySelector('.scene-background')).backgroundImage,
      companionFilter: getComputedStyle(document.querySelector('.companion-container')).filter,
      portalsFilter: getComputedStyle(document.querySelector('.portals-container')).filter,
      portalsOpacity: getComputedStyle(document.querySelector('.portals-container')).opacity,
    };
  });
  assert.equal(nightEnvironment.phase, 'night');
  assert.equal(nightEnvironment.crystalCount, 12);
  assert.match(nightEnvironment.companionFilter, /brightness\(0\.94\)/);
  assert.equal(nightEnvironment.portalsFilter, 'none');
  assert.equal(nightEnvironment.portalsOpacity, '1');
  await page.waitForTimeout(1800);
  await page.screenshot({
    path: new URL('desktop-night-environment.png', outputDir).pathname,
    fullPage: true,
  });
  await page.reload({ waitUntil: 'networkidle' });

  await openToday(page);
  assert.equal(await page.locator('#today-portal').getAttribute('aria-expanded'), 'true');
  const suspendedParallax = await page.locator('.crystal-prisms').evaluate((node) => (
    getComputedStyle(node).getPropertyValue('--parallax-x').trim()
  ));
  assert.equal(suspendedParallax, '0.00px');
  const dialogMaterial = await page.locator('#today-overlay').evaluate((node) => {
    const dialog = getComputedStyle(node);
    const material = getComputedStyle(node, '::before');
    return {
      background: dialog.backgroundColor,
      borderTopWidth: dialog.borderTopWidth,
      materialBackground: material.backgroundImage,
      materialFilter: material.backdropFilter,
      radius: material.borderRadius,
    };
  });
  assert.equal(dialogMaterial.background, 'rgba(0, 0, 0, 0)');
  assert.equal(dialogMaterial.borderTopWidth, '0px');
  assert.notEqual(dialogMaterial.materialBackground, 'none');
  assert.notEqual(dialogMaterial.materialFilter, 'none');
  await page.screenshot({
    path: new URL('desktop-today-material.png', outputDir).pathname,
    fullPage: true,
  });
  await closeSpace(page, '#today-overlay');

  await openSpace(page, '探索记忆', '#memory-overlay');
  const memoryMaterial = await page.locator('#memory-overlay').evaluate((node) => ({
    width: Math.round(node.getBoundingClientRect().width),
    clip: getComputedStyle(node, '::before').clipPath,
  }));
  assert.ok(memoryMaterial.width >= 560, JSON.stringify(memoryMaterial));
  assert.notEqual(memoryMaterial.clip, 'none');
  await page.screenshot({
    path: new URL('desktop-memory-crystal-space.png', outputDir).pathname,
    fullPage: true,
  });
  await closeSpace(page, '#memory-overlay');

  await openSpace(page, '查看来信', '#outbox-overlay');
  const outboxMaterial = await page.locator('#outbox-overlay').evaluate((node) => ({
    right: Math.round(window.innerWidth - node.getBoundingClientRect().right),
    clip: getComputedStyle(node, '::before').clipPath,
  }));
  assert.ok(outboxMaterial.right > 40, JSON.stringify(outboxMaterial));
  assert.notEqual(outboxMaterial.clip, 'none');
  await page.screenshot({
    path: new URL('desktop-outbox-letter-space.png', outputDir).pathname,
    fullPage: true,
  });
  await closeSpace(page, '#outbox-overlay');

  await openSpace(page, '打开隐私与设置', '#privacy-overlay');
  const privacyMaterial = await page.locator('#privacy-overlay').evaluate((node) => ({
    width: Math.round(node.getBoundingClientRect().width),
    viewportWidth: window.innerWidth,
    filter: getComputedStyle(node, '::before').backdropFilter,
    contentCenterY: Math.round(node.querySelector('.dialog-content').getBoundingClientRect().y
      + node.querySelector('.dialog-content').getBoundingClientRect().height / 2),
    viewportCenterY: Math.round(window.innerHeight / 2),
  }));
  assert.ok(Math.abs(privacyMaterial.width - privacyMaterial.viewportWidth) <= 1, JSON.stringify(privacyMaterial));
  assert.ok(Math.abs(privacyMaterial.contentCenterY - privacyMaterial.viewportCenterY) <= 4, JSON.stringify(privacyMaterial));
  assert.notEqual(privacyMaterial.filter, 'none');
  await page.screenshot({
    path: new URL('desktop-privacy-frost-curtain.png', outputDir).pathname,
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  results.push({
    name: 'desktop',
    passed: true,
    screenshots: 6,
    scene,
    dialogMaterial,
    memoryMaterial,
    outboxMaterial,
    privacyMaterial,
  });
  await context.close();
}

async function mobileAcceptance() {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
  const page = await context.newPage();
  const errors = await collectErrors(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'networkidle' });

  await page.getByRole('button', { name: '更多选项' }).click();
  const backgroundMenu = page.locator('[data-hook="scene-menu"]');
  await backgroundMenu.waitFor({ state: 'visible' });
  const menuLayout = await backgroundMenu.evaluate((node) => ({
    right: Math.round(node.getBoundingClientRect().right),
    viewportWidth: window.innerWidth,
    optionCount: node.querySelectorAll('[data-background-id]').length,
  }));
  assert.ok(menuLayout.right <= menuLayout.viewportWidth, JSON.stringify(menuLayout));
  assert.equal(menuLayout.optionCount, 2);
  await page.screenshot({
    path: new URL('mobile-background-menu.png', outputDir).pathname,
    fullPage: true,
  });

  await page.keyboard.press('ArrowRight');
  assert.equal(await page.getByRole('radio', { name: '冰晶圣殿' }).getAttribute('aria-checked'), 'true');
  await page.keyboard.press('Escape');
  const selectedBackground = await page.evaluate(() => ({
    id: document.documentElement.dataset.sceneBackground,
    stored: localStorage.getItem('luminous.scene-background.v1'),
    image: getComputedStyle(document.querySelector('.companion-container')).backgroundImage,
  }));
  assert.equal(selectedBackground.id, 'crystal-sanctuary');
  assert.equal(selectedBackground.stored, 'crystal-sanctuary');
  assert.match(selectedBackground.image, /backgroundv2\.png/);
  await page.screenshot({
    path: new URL('mobile-background-v2.png', outputDir).pathname,
    fullPage: true,
  });

  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(
    await page.locator('html').getAttribute('data-scene-background'),
    'crystal-sanctuary',
  );
  await page.getByRole('button', { name: '更多选项' }).click();
  await page.getByRole('radio', { name: '静夜窗前' }).click();
  await page.screenshot({
    path: new URL('mobile-scene.png', outputDir).pathname,
    fullPage: true,
  });
  await openToday(page);
  await page.locator('[data-hook="resource-nav-toggle"]').click();
  await page.locator('[data-hook="resource-nav"]').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: '任务', exact: true }).click();
  await page.getByRole('button', { name: '凝结新任务' }).click();
  await page.locator('[data-hook="task-title"]').focus();
  await page.waitForTimeout(120);
  const mobile = await page.evaluate(() => {
    const dialog = document.querySelector('#today-overlay');
    const prismRight = document.querySelector('.prism-right');
    const input = document.querySelector('.input-wrapper');
    const dialogue = document.querySelector('#dialogue-stream');
    const statusPanel = document.querySelector('.companion-status-panel');
    const inputSurface = document.querySelector('.input-surface-container');
    const bodyStyle = getComputedStyle(document.body);
    const dialogueRect = dialogue.getBoundingClientRect();
    const statusRect = statusPanel.getBoundingClientRect();
    const inputRect = inputSurface.getBoundingClientRect();
    return {
      dialogBottom: Math.round(dialog.getBoundingClientRect().bottom),
      viewportHeight: window.innerHeight,
      dialogRadius: getComputedStyle(dialog, '::before').borderTopLeftRadius,
      prismRightDisplay: getComputedStyle(prismRight).display,
      inputRadius: getComputedStyle(input).borderTopLeftRadius,
      keyboardState: bodyStyle.getPropertyValue('--unused'),
      horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      portalTops: [...document.querySelectorAll('.portal-btn')].map((node) => Math.round(node.getBoundingClientRect().top)),
      dialogueStatusGap: Math.round(statusRect.top - dialogueRect.bottom),
      statusInputGap: Math.round(inputRect.top - statusRect.bottom),
      inputHeight: Math.round(inputRect.height),
      dialogueLeft: Math.round(dialogueRect.left),
      dialogueBackground: getComputedStyle(dialogue).backgroundImage,
      dialogueBackgroundSize: getComputedStyle(dialogue).backgroundSize,
      dialogueScrollbarWidth: getComputedStyle(dialogue).scrollbarWidth,
      dialogueMaskImage: getComputedStyle(dialogue).maskImage,
      assistantFontSize: Number.parseFloat(getComputedStyle(dialogue.querySelector('.assistant-message')).fontSize),
    };
  });
  assert.ok(Math.abs(mobile.dialogBottom - mobile.viewportHeight) <= 1, JSON.stringify(mobile));
  assert.equal(mobile.dialogRadius, '24px');
  assert.equal(mobile.prismRightDisplay, 'none');
  assert.notEqual(mobile.inputRadius, '0px');
  assert.ok(mobile.horizontalOverflow <= 1, JSON.stringify(mobile));
  assert.equal(mobile.portalTops[0], mobile.portalTops[3], JSON.stringify(mobile));
  assert.equal(mobile.portalTops[1], mobile.portalTops[2], JSON.stringify(mobile));
  assert.ok(mobile.portalTops[0] < mobile.portalTops[1], JSON.stringify(mobile));
  assert.ok(mobile.dialogueStatusGap >= 0 && mobile.dialogueStatusGap <= 2, JSON.stringify(mobile));
  assert.ok(mobile.statusInputGap >= 18, JSON.stringify(mobile));
  assert.ok(mobile.inputHeight <= 54, JSON.stringify(mobile));
  assert.ok(mobile.dialogueLeft <= 20, JSON.stringify(mobile));
  assert.match(mobile.dialogueBackgroundSize, /3px 100%/);
  assert.match(mobile.dialogueBackgroundSize, /11px 100%/);
  assert.doesNotMatch(mobile.dialogueBackgroundSize, /100% 100%/);
  assert.equal(mobile.dialogueScrollbarWidth, 'none');
  assert.match(mobile.dialogueMaskImage, /62%/);
  assert.ok(mobile.assistantFontSize <= 18, JSON.stringify(mobile));
  await page.screenshot({
    path: new URL('mobile-task-condensation-form.png', outputDir).pathname,
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'mobile', passed: true, screenshots: 4, menuLayout, selectedBackground, mobile });
  await context.close();
}

async function reducedMotionAcceptance() {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'networkidle' });
  await page.mouse.move(1360, 120);
  await page.waitForTimeout(100);
  const translation = await page.locator('.crystal-prisms').evaluate((node) => (
    getComputedStyle(node).translate
  ));
  assert.ok(translation === 'none' || translation === '0px', translation);
  results.push({ name: 'reduced-motion', passed: true, translation });
  await context.close();
}

try {
  await desktopAcceptance();
  await mobileAcceptance();
  await reducedMotionAcceptance();
  await writeFile(
    new URL('browser-acceptance.json', outputDir),
    `${JSON.stringify({ generatedAt: new Date().toISOString(), results }, null, 2)}\n`,
  );
  console.log(`CRYSTAL_SOLARIUM_V2_BROWSER_OK scenarios=${results.length} screenshots=10`);
} finally {
  await browser.close();
}
