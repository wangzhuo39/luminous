import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL(
  '../../docs/front_design/acceptance/today-timeline-s3-b3/',
  import.meta.url,
);

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

async function verifyViewport(name, viewport, reducedMotion = 'no-preference') {
  const context = await browser.newContext({ viewport, reducedMotion });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  const errors = [];
  const apiRequests = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url());
  });

  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await page.locator('body:not([data-js-loading])').waitFor();
  assert.equal(apiRequests.length, 0, `${name}: fixture mode must not request APIs`);
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
    `${name}: page must not overflow horizontally`,
  );

  const portal = page.getByRole('button', { name: '打开今日摘要' });
  await portal.focus();
  await portal.click();
  const dialog = page.getByRole('dialog', { name: '今日光影' });
  await dialog.waitFor({ state: 'visible' });
  await page.locator('#today-overlay[data-today-status="ready"]').waitFor();
  assert.equal(await page.evaluate(() => document.activeElement?.closest('dialog')?.id), 'today-overlay');

  const todayText = await dialog.locator('[data-hook="today-panel"]').innerText();
  assert.match(todayText, /正在发生/);
  assert.match(todayText, /时间落点/);
  assert.match(todayText, /下午三点，记得留一点时间休息。/);
  assert.match(todayText, /上午有一次重要的会议提醒。/);
  assert.match(await dialog.locator('[data-hook="today-date"]').innerText(), /7月25日/);
  await page.screenshot({
    path: new URL(`${name}-today.png`, outputDir).pathname,
    fullPage: true,
  });

  await page.getByRole('button', { name: '回顾时间线' }).click();
  await page.locator('#today-overlay[data-today-status="ready"] [data-hook="timeline-panel"]')
    .waitFor({ state: 'visible' });
  const timelineItems = await page.locator('[data-hook="timeline-list"] li').allInnerTexts();
  assert.equal(timelineItems.length, 2);
  assert.match(timelineItems[0], /下午三点/);
  assert.match(timelineItems[1], /上午/);
  await page.screenshot({
    path: new URL(`${name}-timeline.png`, outputDir).pathname,
    fullPage: true,
  });

  await page.getByRole('button', { name: '返回今日摘要' }).click();
  assert.equal(await page.locator('[data-hook="today-panel"]').isVisible(), true);
  await page.getByRole('button', { name: '关闭今日光影' }).click();
  await dialog.waitFor({ state: 'hidden' });
  assert.equal(await portal.evaluate((node) => document.activeElement === node), true);
  assert.deepEqual(errors, [], `${name}: console and page errors`);

  results.push({
    name,
    viewport,
    reducedMotion,
    apiRequests: apiRequests.length,
    consoleErrors: errors.length,
    timelineItems: timelineItems.length,
    focusRestored: true,
  });
  await context.close();
}

async function verifyApiScenario(name, {
  todayStatus = 200, todayBody, expectedStatus, message, allowedConsolePattern = null,
}) {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('console', (entry) => {
    if (entry.type() === 'error') errors.push(entry.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/auth/session') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"authenticated":true}' });
      return;
    }
    if (path === '/api/state') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ state: { mood: 'calm' } }),
      });
      return;
    }
    if (path === '/api/today') {
      await route.fulfill({
        status: todayStatus,
        contentType: 'application/json',
        body: JSON.stringify(todayBody),
      });
      return;
    }
    await route.abort();
  });

  await page.goto(`${baseUrl}/?mode=api`, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  await page.getByRole('button', { name: '打开今日摘要' }).click();
  await page.locator(`#today-overlay[data-today-status="${expectedStatus}"]`).waitFor();
  const stateText = await page.locator('[data-hook="today-local-state"] p').innerText();
  assert.match(stateText, message);
  assert.doesNotMatch(await page.locator('body').innerText(), /internal detail must not render/);
  assert.equal(await page.locator('[data-hook="today-local-state"]').isVisible(), true);
  const unexpectedErrors = allowedConsolePattern
    ? errors.filter((entry) => !allowedConsolePattern.test(entry))
    : errors;
  assert.deepEqual(unexpectedErrors, [], `${name}: unexpected console and page errors`);
  await page.screenshot({
    path: new URL(`${name}.png`, outputDir).pathname,
    fullPage: true,
  });
  results.push({
    name,
    expectedStatus,
    expectedConsoleErrors: errors.length - unexpectedErrors.length,
    unexpectedConsoleErrors: unexpectedErrors.length,
  });
  await context.close();
}

try {
  await verifyViewport('desktop-1440x1000', { width: 1440, height: 1000 });
  await verifyViewport('mobile-390x844', { width: 390, height: 844 }, 'reduce');
  await verifyApiScenario('desktop-empty', {
    todayBody: {
      date: '2026-07-26',
      active_activities: [],
      calendar_events: [],
      due_tasks: [],
      routines: [],
      overdue_tasks: [],
      open_tasks: [],
      completed_tasks: [],
    },
    expectedStatus: 'ready',
    message: /今天还没有需要展开的事/,
  });
  await verifyApiScenario('desktop-error', {
    todayStatus: 503,
    todayBody: { detail: 'internal detail must not render' },
    expectedStatus: 'error',
    message: /栖光暂时无法回应/,
    allowedConsolePattern: /503 \(Service Unavailable\)/,
  });
  await writeFile(
    new URL('browser-acceptance.json', outputDir),
    `${JSON.stringify({ passed: true, results }, null, 2)}\n`,
  );
  console.log('B3_BROWSER_ACCEPTANCE_OK viewports=2 scenarios=2 screenshots=6');
} finally {
  await browser.close();
}
