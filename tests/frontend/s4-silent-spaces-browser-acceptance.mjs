import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL('../../docs/front_design/acceptance/silent-spaces-s4-b1/', import.meta.url);
await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

function errorsFor(page) {
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function pageFor(context) {
  const page = await context.newPage();
  const errors = errorsFor(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status]:not([data-js-loading])').waitFor();
  return { page, errors };
}

async function outboxDesktop() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const { page, errors } = await pageFor(context);
  await page.locator('#outbox-portal').click();
  await page.locator('#outbox-overlay[open] .outbox-item').waitFor();
  assert.match(await page.locator('.outbox-item').innerText(), /晨光刚落进窗里/);
  await page.getByRole('button', { name: '轻轻收下' }).click();
  await page.getByText('已轻轻收下。').waitFor();
  await page.getByRole('button', { name: '对我有帮助' }).click();
  await page.getByText('我会记得。').waitFor();
  await page.screenshot({ path: new URL('desktop-outbox-read-feedback.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  assert.deepEqual(errors, []);
  results.push({ name: 'desktop-outbox', passed: true, screenshots: 1 });
  await context.close();
}

async function memoryDesktop() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const { page, errors } = await pageFor(context);
  await page.locator('#memory-portal').click();
  await page.locator('[data-hook="memory-search-input"]').fill('雨');
  await page.locator('[data-hook="memory-search-form"]').press('Enter');
  await page.locator('.memory-facet').waitFor();
  assert.doesNotMatch(await page.locator('.memory-facet').innerText(), /confidence|score|evidence|source_excerpt/);
  await page.getByRole('button', { name: '修琢' }).click();
  const editor = page.locator('.crystal-textarea');
  await editor.fill('用户喜欢雨停以后，偏冷而安静的晨光。');
  await page.getByRole('button', { name: '保存修订' }).click();
  await page.getByText('用户喜欢雨停以后，偏冷而安静的晨光。').waitFor();
  await page.getByRole('button', { name: '忘却' }).click();
  await page.getByText('忘却后，这段内容不会再参与平常的陪伴。').waitFor();
  await page.screenshot({ path: new URL('desktop-memory-forget-confirm.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: '确认忘却' }).click();
  await page.getByText('没有找到与这段文字相近的记忆。').waitFor();
  assert.deepEqual(errors, []);
  results.push({ name: 'desktop-memory', passed: true, screenshots: 1 });
  await context.close();
}

async function privacyAndMobile() {
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  let active = await pageFor(desktop);
  await active.page.locator('#privacy-portal').click();
  await active.page.locator('[data-hook="privacy-form"]:visible').waitFor();
  assert.match(await active.page.locator('#privacy-overlay').innerText(), /当前没有额外的免打扰时段/);
  assert.equal(await active.page.getByRole('button', { name: /免打扰/ }).count(), 0);
  await active.page.locator('[data-hook="privacy-limit"]').selectOption('2');
  await active.page.getByRole('button', { name: '保存边界' }).click();
  await active.page.getByText('边界已安静地放回原处。').waitFor();
  await active.page.screenshot({ path: new URL('desktop-privacy-saved.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  assert.deepEqual(active.errors, []);
  await desktop.close();

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  active = await pageFor(mobile);
  await active.page.locator('#outbox-portal').click();
  await active.page.locator('.outbox-item').waitFor();
  const box = await active.page.locator('#outbox-overlay').evaluate((entry) => ({ width: entry.getBoundingClientRect().width, viewport: innerWidth, scrollWidth: entry.scrollWidth, clientWidth: entry.clientWidth }));
  assert.ok(Math.abs(box.width - box.viewport) <= 1, JSON.stringify(box));
  assert.ok(box.scrollWidth <= box.clientWidth + 1, JSON.stringify(box));
  const heights = await active.page.locator('#outbox-overlay button:visible').evaluateAll((nodes) => nodes.map((entry) => entry.getBoundingClientRect().height));
  assert.ok(heights.every((height) => height >= 44), JSON.stringify(heights));
  const animations = await active.page.locator('#outbox-overlay *').evaluateAll((nodes) => [...new Set(nodes.map((entry) => getComputedStyle(entry).animationName))]);
  assert.deepEqual(animations.filter((name) => name !== 'none'), []);
  await active.page.screenshot({ path: new URL('mobile-outbox-reduced-motion.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  assert.deepEqual(active.errors, []);
  results.push({ name: 'privacy-mobile', passed: true, screenshots: 2 });
  await mobile.close();
}

async function apiErrorRetryAndNoLeak() {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  const page = await context.newPage();
  const errors = errorsFor(page);
  let outboxAttempts = 0;
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/state') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ state: { mood: 'steady', energy: 0.5, support_need: 0.4, risk_level: 'normal', conversation_mode: 'support', dnd_until: '' } }) });
      return;
    }
    if (url.pathname === '/api/outbox') {
      outboxAttempts += 1;
      if (outboxAttempts === 1) { await route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"temporary"}' }); return; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ message_id: 'safe-letter', draft_text: '等风停了，再慢慢回答也可以。', status: 'delivered', signal_type: 'checkin', created_at: '2026-07-26T08:00:00Z', trace_id: 'must-not-render', reason: 'must-not-render', score: 0.99, payload: { secret: true } }] }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
  });
  await page.goto(`${baseUrl}/?mode=api`, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status]:not([data-js-loading])').waitFor();
  await page.locator('#outbox-portal').click();
  await page.getByText('信笺暂时没有展开。').waitFor();
  await page.screenshot({ path: new URL('desktop-outbox-error-retry.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: '重新展开' }).click();
  await page.getByText('等风停了，再慢慢回答也可以。').waitFor();
  assert.doesNotMatch(await page.locator('#outbox-overlay').innerText(), /must-not-render|0\.99|secret/);
  assert.equal(outboxAttempts, 2);
  assert.deepEqual(errors.filter((message) => !message.includes('Failed to load resource')), []);
  results.push({ name: 'api-error-retry-no-leak', passed: true, screenshots: 1 });
  await context.close();
}

try {
  await outboxDesktop();
  await memoryDesktop();
  await privacyAndMobile();
  await apiErrorRetryAndNoLeak();
  console.log(JSON.stringify({ passed: true, results }, null, 2));
} finally {
  await browser.close();
}
