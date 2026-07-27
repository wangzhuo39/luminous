import assert from 'node:assert/strict';
import { test } from 'node:test';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_BASE_URL ?? 'http://127.0.0.1:8000';
const chromiumPath = process.env.LUMINOUS_CHROMIUM_PATH
  ?? '/home/wz/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome';

async function inspectPage(page, viewport, screenshotPath) {
  const consoleErrors = [];
  const failedResponses = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => consoleErrors.push(String(error)));
  page.on('response', (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });
  await page.setViewportSize(viewport);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  await page.screenshot({ path: screenshotPath, fullPage: true });

  const metrics = await page.evaluate(() => {
    const selectors = [
      '#luminous-scene', '#companion-figure', '#dialogue-stream', '#input-surface',
      '.top-scene-header', '.companion-status-panel',
      '#today-portal', '#memory-portal', '#outbox-portal', '#privacy-portal',
    ];
    const result = Object.fromEntries(selectors.map((selector) => {
      const node = document.querySelector(selector);
      if (!node) return [selector, null];
      const rect = node.getBoundingClientRect();
      return [selector, {
        x: Math.round(rect.x), y: Math.round(rect.y),
        width: Math.round(rect.width), height: Math.round(rect.height),
        visible: getComputedStyle(node).visibility !== 'hidden',
      }];
    }));
    return {
      bodyWidth: document.body.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      image: getComputedStyle(document.querySelector('#companion-figure')).backgroundImage,
      artwork: Object.fromEntries([
        '.status-frame-art', '.input-frame-art', '#send-button .icon-send img',
      ].map((selector) => {
        const imageNode = document.querySelector(selector);
        return [selector, Boolean(imageNode?.complete && imageNode.naturalWidth > 0)];
      })),
      statusPanelWidth: document.querySelector('.companion-status-panel')?.getBoundingClientRect().width ?? 0,
      statusContentWidth: document.querySelector('.companion-status-content')?.getBoundingClientRect().width ?? 0,
      statusCopyWidth: document.querySelector('.status-copy')?.getBoundingClientRect().width ?? 0,
      visibleSendIconCount: [...document.querySelectorAll('#send-button .icon-container')]
        .filter((node) => getComputedStyle(node).display !== 'none').length,
      result,
    };
  });

  assert.equal(consoleErrors.length, 0, consoleErrors.join('\n'));
  assert.equal(failedResponses.length, 0, failedResponses.join('\n'));
  assert.ok(metrics.scrollWidth <= viewport.width, 'main page must not scroll horizontally');
  assert.match(metrics.image, /yezheng\.png/);
  for (const [selector, loaded] of Object.entries(metrics.artwork)) {
    assert.ok(loaded, `${selector} artwork should load`);
  }
  assert.ok(metrics.statusContentWidth >= metrics.statusPanelWidth * 0.8, 'status content should span the painted frame');
  assert.ok(metrics.statusCopyWidth > 0, 'status copy should remain visible above the painted frame');
  assert.equal(metrics.visibleSendIconCount, 1, 'exactly one send state icon should be visible');
  for (const selector of ['#companion-figure', '#dialogue-stream', '#input-surface', '.top-scene-header', '.companion-status-panel']) {
    assert.ok(metrics.result[selector]?.visible, `${selector} should be visible`);
  }
  for (const selector of ['#today-portal', '#memory-portal', '#outbox-portal', '#privacy-portal']) {
    assert.ok(metrics.result[selector]?.width > 0, `${selector} should have layout`);
  }
}

test('main scene matches the reconstructed desktop shell', async () => {
  const browser = await chromium.launch({ headless: true, executablePath: chromiumPath });
  try {
    await inspectPage(
      await browser.newPage({ viewport: { width: 941, height: 1672 } }),
      { width: 941, height: 1672 },
      '/tmp/luminous-main-page-941x1672.png',
    );
  } finally {
    await browser.close();
  }
});

test('main scene remains usable on a mobile viewport', async () => {
  const browser = await chromium.launch({ headless: true, executablePath: chromiumPath });
  try {
    await inspectPage(
      await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true }),
      { width: 390, height: 844 },
      '/tmp/luminous-main-page-390x844.png',
    );
  } finally {
    await browser.close();
  }
});
