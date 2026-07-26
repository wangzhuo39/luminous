import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL(
  '../../docs/front_design/acceptance/activities-s3-b5/',
  import.meta.url,
);

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

async function openToday(page) {
  await page.locator('body[data-app-status]').waitFor();
  await page.getByRole('button', { name: '打开今日摘要' }).click();
  await page.locator('#today-overlay[open]').waitFor();
}

async function expandLifeFlow(page) {
  const toggle = page.getByRole('button', { name: '展开', exact: true });
  if (await toggle.isVisible()) {
    await toggle.click();
  }
  await page.locator('[data-hook="resource-nav"]:visible').waitFor();
}

function collectErrors(page, allowed = () => false) {
  const errors = [];
  page.on('console', (entry) => {
    if (entry.type() === 'error' && !allowed(entry.text())) errors.push(entry.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function assertNoForbiddenActivityUi(page) {
  const text = await page.locator('[data-hook="activity-panel"]').innerText();
  assert.doesNotMatch(text, /计时|秒|进度|预计时长|删除|归档/);
  assert.equal(await page.locator('[data-hook="activity-panel"] progress').count(), 0);
}

async function fixtureLifecycleDesktop() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = collectErrors(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  assert.equal(await page.locator('body').getAttribute('data-activity-presence'), 'active');
  await expandLifeFlow(page);
  await page.getByRole('button', { name: '活动', exact: true }).click();
  await page.locator('[data-hook="activity-list"] .activity-list-entry').waitFor();
  assert.equal(await page.locator('[data-hook="activity-panel"]').isVisible(), true);
  assert.equal(await page.locator('[data-hook="today-panel"]').isVisible(), false);
  await assertNoForbiddenActivityUi(page);
  await page.screenshot({
    path: new URL('desktop-activity-list.png', outputDir).pathname,
    fullPage: true,
  });

  await page.locator('[data-hook="activity-list"] .activity-list-entry').first().click();
  await page.locator('[data-hook="activity-crystal"].is-active').waitFor();
  assert.equal(await page.locator('[data-hook="activity-list"]').isVisible(), false);
  assert.equal(await page.getByRole('button', { name: '暂停', exact: true }).count(), 1);
  assert.equal(await page.getByRole('button', { name: '完成', exact: true }).count(), 1);
  assert.equal(await page.getByRole('button', { name: '取消', exact: true }).count(), 1);
  assert.equal(await page.getByRole('button', { name: '开始', exact: true }).count(), 0);
  await page.screenshot({
    path: new URL('desktop-activity-active.png', outputDir).pathname,
    fullPage: true,
  });

  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await page.locator('[data-hook="activity-crystal"].is-paused').waitFor();
  assert.equal(await page.locator('body').getAttribute('data-activity-presence'), 'paused');
  assert.equal(await page.getByRole('button', { name: '继续', exact: true }).count(), 1);
  assert.equal(await page.getByRole('button', { name: '暂停', exact: true }).count(), 0);
  await page.screenshot({
    path: new URL('desktop-activity-paused.png', outputDir).pathname,
    fullPage: true,
  });

  await page.getByRole('button', { name: '继续', exact: true }).click();
  await page.locator('[data-hook="activity-crystal"].is-active').waitFor();
  await page.getByRole('button', { name: '完成', exact: true }).click();
  await page.locator('[data-hook="activity-crystal"].is-completed').waitFor();
  assert.equal(await page.locator('[data-hook="activity-status-actions"] button').count(), 0);
  await page.screenshot({
    path: new URL('desktop-activity-completed.png', outputDir).pathname,
    fullPage: true,
  });

  await page.locator('[data-hook="activity-back"]').click();
  await page.getByRole('button', { name: '计划一次活动' }).click();
  await page.locator('[data-hook="activity-title"]').fill('一起整理今天的光影');
  await page.locator('[data-hook="activity-kind"]').selectOption('reflection');
  await page.getByRole('button', { name: '计划活动' }).click();
  await page.locator('[data-hook="activity-crystal"].is-planned').waitFor();
  assert.equal(await page.getByRole('button', { name: '开始', exact: true }).count(), 1);
  assert.equal(await page.getByRole('button', { name: '取消', exact: true }).count(), 1);
  assert.equal(await page.getByRole('button', { name: '暂停', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: '完成', exact: true }).count(), 0);
  await page.screenshot({
    path: new URL('desktop-activity-planned.png', outputDir).pathname,
    fullPage: true,
  });
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await page.locator('[data-hook="activity-crystal"].is-cancelled').waitFor();
  assert.equal(await page.locator('[data-hook="activity-status-actions"] button').count(), 0);
  await page.screenshot({
    path: new URL('desktop-activity-cancelled.png', outputDir).pathname,
    fullPage: true,
  });

  const html = await page.locator('body').evaluate((body) => body.outerHTML);
  assert.doesNotMatch(html, /fixture-activity-rest/);
  await assertNoForbiddenActivityUi(page);
  assert.deepEqual(errors, []);
  results.push({ name: 'fixture-lifecycle-desktop', passed: true, screenshots: 6 });
  await context.close();
}

async function fixtureCreateMobileReducedMotion() {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  const errors = collectErrors(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  await expandLifeFlow(page);
  await page.getByRole('button', { name: '活动', exact: true }).click();
  await page.getByRole('button', { name: '计划一次活动' }).click();
  await page.waitForFunction(() => (
    document.activeElement === document.querySelector('[data-hook="activity-title"]')
  ));
  await page.locator('[data-hook="activity-title"]').fill('一起把今天发生的事慢慢梳理清楚');
  await page.locator('[data-hook="activity-kind"]').selectOption('planning');
  await page.evaluate(() => { document.body.dataset.keyboardVisible = 'true'; });
  await page.locator('[data-hook="activity-title"]').focus();
  assert.equal(
    await page.locator('.activity-form-actions').evaluate((node) => getComputedStyle(node).position),
    'static',
  );

  const layout = await page.locator('#today-overlay').evaluate((node) => ({
    scrollWidth: node.scrollWidth,
    clientWidth: node.clientWidth,
  }));
  assert.ok(layout.scrollWidth <= layout.clientWidth + 1, JSON.stringify(layout));
  const targets = await page.locator('[data-hook="activity-form"] :is(input, select, button)').evaluateAll(
    (nodes) => nodes.map((node) => node.getBoundingClientRect().height),
  );
  assert.ok(targets.every((height) => height >= 44), JSON.stringify(targets));
  await page.locator('[data-hook="activity-submit"]').evaluate((node) => {
    node.scrollIntoView({ block: 'nearest' });
    node.focus();
  });
  assert.equal(
    await page.locator('[data-hook="activity-submit"]').evaluate((node) => node === document.activeElement),
    true,
  );
  const animationNames = await page.locator('[data-hook="activity-panel"] *').evaluateAll(
    (nodes) => [...new Set(nodes.map((node) => getComputedStyle(node).animationName))],
  );
  assert.deepEqual(animationNames.filter((name) => name !== 'none'), []);
  await page.screenshot({
    path: new URL('mobile-activity-create-reduced-motion.png', outputDir).pathname,
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'fixture-create-mobile-reduced', passed: true, screenshots: 1 });
  await context.close();
}

async function apiCreateErrorAndExactContract() {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  const page = await context.newPage();
  const errors = collectErrors(page, (text) => /503 \(Service Unavailable\)/.test(text));
  const requests = [];
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === '/api/state') {
      await route.fulfill({
        status: 200, contentType: 'application/json', body: '{"state":{"mood":"calm"}}',
      });
    } else if (url.pathname === '/api/today') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          date: '2026-07-26', active_activities: [], calendar_events: [], due_tasks: [],
          routines: [], overdue_tasks: [], open_tasks: [], completed_tasks: [],
        }),
      });
    } else if (url.pathname === '/api/activities' && request.method() === 'GET') {
      requests.push({ method: request.method(), path: `${url.pathname}${url.search}` });
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' });
    } else if (url.pathname === '/api/activities' && request.method() === 'POST') {
      requests.push({ method: request.method(), path: url.pathname, body: request.postDataJSON() });
      await new Promise((resolve) => setTimeout(resolve, 180));
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: '{"detail":"opaque internal failure and session_id must not render"}',
      });
    } else await route.abort();
  });

  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  await openToday(page);
  assert.equal(await page.locator('body').getAttribute('data-activity-presence'), 'none');
  await expandLifeFlow(page);
  await page.getByRole('button', { name: '活动', exact: true }).click();
  await page.getByText('还没有共同度过的活动').waitFor();
  await page.getByRole('button', { name: '计划一次活动' }).click();
  await page.locator('[data-hook="activity-title"]').fill('不会重复提交');
  await page.locator('[data-hook="activity-kind"]').selectOption('reflection');
  await page.locator('[data-hook="activity-submit"]').evaluate((button) => {
    button.click();
    button.click();
  });
  await page.locator('[data-hook="activity-error"]:visible').waitFor();
  assert.deepEqual(requests, [
    { method: 'GET', path: '/api/activities?limit=100' },
    { method: 'POST', path: '/api/activities', body: {
      title: '不会重复提交', kind: 'reflection',
    } },
  ]);
  assert.equal(await page.locator('[data-hook="activity-title"]').inputValue(), '不会重复提交');
  assert.equal(await page.locator('[data-hook="activity-kind"]').inputValue(), 'reflection');
  const pageText = await page.locator('body').innerText();
  assert.doesNotMatch(pageText, /opaque internal failure|session_id/);
  await page.screenshot({
    path: new URL('desktop-activity-api-error.png', outputDir).pathname,
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'api-create-error-exact-contract', passed: true, screenshots: 1 });
  await context.close();
}

try {
  await fixtureLifecycleDesktop();
  await fixtureCreateMobileReducedMotion();
  await apiCreateErrorAndExactContract();
  await writeFile(
    new URL('browser-acceptance.json', outputDir),
    `${JSON.stringify({ passed: true, results }, null, 2)}\n`,
  );
  console.log('B5_BROWSER_ACCEPTANCE_OK scenarios=3 screenshots=8');
} finally {
  await browser.close();
}
