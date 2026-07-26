import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL('../../docs/front_design/acceptance/s3-final-integration-b9/', import.meta.url);
await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

function errorsFor(page) {
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function productionGateAndChat() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 820 } });
  const page = await context.newPage();
  const errors = errorsFor(page);
  const requests = [];
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push({ method: request.method(), path: url.pathname });
    if (url.pathname === '/api/state') {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ state: { mood: 'calm' } }),
      });
    } else if (url.pathname === '/api/chat') {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ reply: '我在这里，听见你了。', state: { mood: 'calm' } }),
      });
    } else if (url.pathname === '/api/today') {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          date: '2026-07-26', active_activities: [], calendar_events: [], due_tasks: [],
          routines: [], overdue_tasks: [], open_tasks: [], completed_tasks: [],
        }),
      });
    } else await route.abort();
  });
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  assert.equal(await page.evaluate(() => '__luminousActionFixture' in window), false);
  assert.equal(await page.locator('[data-hook="action-card"]:visible').count(), 0);
  await page.locator('[data-hook="chat-input"]').fill('今天有点累');
  await page.locator('[data-hook="input-form"]').evaluate((form) => form.requestSubmit());
  await page.locator('[data-hook="dialogue-stream"]').getByText('我在这里，听见你了。').waitFor();
  assert.deepEqual(requests.slice(0, 2), [
    { method: 'GET', path: '/api/state' }, { method: 'POST', path: '/api/chat' },
  ]);
  assert.equal(requests.some(({ path }) => path.startsWith('/api/actions/')), false);
  await page.getByRole('button', { name: '打开今日摘要' }).click();
  await page.locator('#today-overlay[open]').waitFor();
  assert.equal(requests.some(({ path }) => path === '/api/today'), true);
  await page.screenshot({
    path: new URL('desktop-production-chat-today-no-action-trigger.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'production-gate-chat-today', passed: true, screenshots: 1 });
  await context.close();
}

async function extraSmallActionAndPortalRecovery() {
  const context = await browser.newContext({
    viewport: { width: 320, height: 568 }, reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  const errors = errorsFor(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.__luminousActionFixture?.propose === 'function');
  await page.evaluate(() => {
    void window.__luminousActionFixture.propose({
      action: 'create_task',
      payload: { title: '极小屏上的长行动建议也应该自然换行，并且完整保留婉拒和确认按钮' },
    });
  });
  const card = page.locator('[data-hook="action-card"][data-action-status="preview_ready"]');
  await card.waitFor();
  const box = await card.boundingBox();
  assert.ok(box && box.x >= 0 && box.x + box.width <= 321, JSON.stringify(box));
  assert.ok(box && box.y > 120 && box.y + box.height <= 568, JSON.stringify(box));
  assert.equal(
    await page.locator('[data-hook="resource-nav"] button:visible').count(), 0,
  );
  await page.screenshot({
    path: new URL('mobile-320-action-light-tag.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  await page.getByRole('button', { name: '婉拒' }).click();
  await page.waitForFunction(() => window.__luminousActionFixture.state() === 'idle');
  assert.equal(await page.getByRole('button', { name: '打开今日摘要' }).isEnabled(), true);
  await page.getByRole('button', { name: '打开今日摘要' }).click();
  await page.locator('#today-overlay[open]').waitFor();
  await page.screenshot({
    path: new URL('mobile-320-portal-recovers-after-action.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'mobile-320-action-portal-recovery', passed: true, screenshots: 2 });
  await context.close();
}

try {
  await productionGateAndChat();
  await extraSmallActionAndPortalRecovery();
  console.log(JSON.stringify({ passed: true, results }, null, 2));
} finally {
  await browser.close();
}
