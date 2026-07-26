import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL('../../docs/front_design/acceptance/diary-s3-b6/', import.meta.url);
await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

async function openToday(page) {
  await page.locator('body[data-app-status]').waitFor();
  await page.getByRole('button', { name: '打开今日摘要' }).click();
  await page.locator('#today-overlay[open]').waitFor();
}

function errorsFor(page, allowed = () => false) {
  const errors = [];
  page.on('console', (entry) => {
    if (entry.type() === 'error' && !allowed(entry.text())) errors.push(entry.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function fixtureDesktop() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = errorsFor(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  await page.getByRole('button', { name: '日记', exact: true }).click();
  await page.getByRole('button', { name: /今天的一束光/ }).waitFor();
  assert.equal(await page.locator('[data-hook="today-panel"]').isVisible(), false);
  await page.screenshot({
    path: new URL('desktop-diary-list.png', outputDir).pathname,
    fullPage: true,
    animations: 'disabled',
  });

  await page.getByRole('button', { name: /今天的一束光/ }).click();
  await page.getByRole('heading', { name: '今天的一束光' }).waitFor();
  assert.match(await page.locator('[data-hook="diary-detail"]').innerText(), /下午的光线很安静/);
  await page.getByRole('button', { name: '编辑', exact: true }).click();
  await page.locator('[data-hook="diary-body"]').fill('下午的光线很安静。\n我也愿意把脚步放慢一点。');
  await page.getByRole('button', { name: '保存到 Luminous' }).click();
  await page.getByText('我也愿意把脚步放慢一点。').waitFor();
  await page.screenshot({
    path: new URL('desktop-diary-detail.png', outputDir).pathname,
    fullPage: true,
    animations: 'disabled',
  });

  await page.getByRole('button', { name: '移出日记' }).click();
  const confirmation = page.locator('[data-hook="diary-confirmation"]');
  await confirmation.waitFor();
  assert.match(await confirmation.innerText(), /从时间流中移出这篇日记/);
  assert.doesNotMatch(await confirmation.innerText(), /永久|不可撤销|可恢复/);
  await page.screenshot({
    path: new URL('desktop-diary-remove-confirmation.png', outputDir).pathname,
    fullPage: true,
    animations: 'disabled',
  });
  await page.getByRole('button', { name: '保留' }).click();
  assert.equal(await confirmation.isVisible(), false);
  await page.getByRole('button', { name: '移出日记' }).click();
  await page.getByRole('button', { name: '确认移出' }).click();
  await page.getByText('今天的思绪，也可以在这里安放').waitFor();
  assert.deepEqual(errors, []);
  results.push({ name: 'fixture-desktop', passed: true, screenshots: 3 });
  await context.close();
}

async function fixtureMobileLongBody() {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  const errors = errorsFor(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  await page.getByRole('button', { name: '日记', exact: true }).click();
  await page.getByRole('button', { name: '生成今日回顾' }).click();
  await page.locator('[data-hook="diary-form"][data-editor-kind="generated"]').waitFor();
  await page.locator('[data-hook="diary-title"]').fill('今天很长的一段回顾');
  await page.locator('[data-hook="diary-body"]').fill(
    '我想保留这一段很长的中文正文，用来确认它会自然换行，不会从温室纸面横向溢出。\n'.repeat(12),
  );
  await page.evaluate(() => { document.body.dataset.keyboardVisible = 'true'; });
  assert.equal(
    await page.locator('.diary-form-actions').evaluate((node) => getComputedStyle(node).position),
    'static',
  );
  await page.locator('[data-hook="diary-submit"]').evaluate((node) => {
    node.scrollIntoView({ block: 'nearest' });
    node.focus();
  });
  const layout = await page.locator('#today-overlay').evaluate((node) => ({
    scrollWidth: node.scrollWidth, clientWidth: node.clientWidth,
  }));
  assert.ok(layout.scrollWidth <= layout.clientWidth + 1, JSON.stringify(layout));
  const targets = await page.locator('[data-hook="diary-form"] :is(input, textarea, button)').evaluateAll(
    (nodes) => nodes.map((node) => node.getBoundingClientRect().height),
  );
  assert.ok(targets.every((height) => height >= 44), JSON.stringify(targets));
  const animations = await page.locator('[data-hook="diary-panel"] *').evaluateAll(
    (nodes) => [...new Set(nodes.map((node) => getComputedStyle(node).animationName))],
  );
  assert.deepEqual(animations.filter((name) => name !== 'none'), []);
  await page.screenshot({
    path: new URL('mobile-generated-diary-long-body.png', outputDir).pathname,
    fullPage: true,
    animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'fixture-mobile-long-body', passed: true, screenshots: 1 });
  await context.close();
}

async function installBaseApiRoutes(page, handler) {
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
    } else await handler(route, request, url);
  });
}

async function apiGeneratedPatchAndDelete() {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  const page = await context.newPage();
  const errors = errorsFor(page);
  const requests = [];
  await installBaseApiRoutes(page, async (route, request, url) => {
    if (url.pathname === '/api/diary-entries' && request.method() === 'GET') {
      requests.push({ method: 'GET', path: `${url.pathname}${url.search}` });
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' });
    } else if (url.pathname === '/api/diary-entries/draft' && request.method() === 'POST') {
      requests.push({ method: 'POST_DRAFT', path: url.pathname, body: request.postDataJSON() });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ diary_entry: {
          entry_id: 'server-secret-diary-42', date: '2026-07-26', title: '今日回顾',
          body: '- 一件安静的小事', status: 'draft', updated_at: '2026-07-26T08:00:00Z',
        } }),
      });
    } else if (url.pathname === '/api/diary-entries/server-secret-diary-42'
      && request.method() === 'PATCH') {
      requests.push({ method: 'PATCH', path: url.pathname, body: request.postDataJSON() });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ diary_entry: {
          entry_id: 'server-secret-diary-42', date: '2026-07-26', title: '今日回顾',
          body: '- 一件安静的小事\n- 一束光', status: 'saved', updated_at: '2026-07-26T09:00:00Z',
        } }),
      });
    } else if (url.pathname === '/api/diary-entries/server-secret-diary-42'
      && request.method() === 'DELETE') {
      requests.push({ method: 'DELETE', path: url.pathname });
      await new Promise((resolve) => setTimeout(resolve, 120));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ diary_entry: {
          entry_id: 'server-secret-diary-42', date: '2026-07-26', title: '今日回顾',
          body: '- 一件安静的小事\n- 一束光', status: 'deleted', updated_at: '2026-07-26T10:00:00Z',
        } }),
      });
    } else await route.abort();
  });

  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  await openToday(page);
  await page.getByRole('button', { name: '日记', exact: true }).click();
  await page.getByText('今天的思绪，也可以在这里安放').waitFor();
  await page.getByRole('button', { name: '生成今日回顾' }).click();
  await page.locator('[data-hook="diary-body"]').fill('- 一件安静的小事\n- 一束光');
  await page.getByRole('button', { name: '保存到 Luminous' }).click();
  await page.getByText('- 一束光').waitFor();
  assert.equal(requests.filter(({ method }) => method === 'POST_DRAFT').length, 1);
  assert.equal(requests.filter(({ method }) => method === 'PATCH').length, 1);
  assert.equal(requests.filter(({ method }) => method === 'POST').length, 0);
  await page.getByRole('button', { name: '移出日记' }).click();
  await page.screenshot({
    path: new URL('desktop-generated-diary-before-remove.png', outputDir).pathname,
    fullPage: true,
    animations: 'disabled',
  });
  await page.getByRole('button', { name: '确认移出' }).click();
  assert.equal(await page.getByRole('button', { name: '确认移出' }).isDisabled(), true);
  await page.getByText('今天的思绪，也可以在这里安放').waitFor();
  assert.deepEqual(requests, [
    { method: 'GET', path: '/api/diary-entries?limit=100' },
    { method: 'POST_DRAFT', path: '/api/diary-entries/draft', body: { date: '2026-07-26' } },
    { method: 'PATCH', path: '/api/diary-entries/server-secret-diary-42', body: {
      date: '2026-07-26', title: '今日回顾', body: '- 一件安静的小事\n- 一束光', status: 'saved',
    } },
    { method: 'DELETE', path: '/api/diary-entries/server-secret-diary-42' },
  ]);
  assert.doesNotMatch(await page.locator('body').evaluate((body) => body.outerHTML), /server-secret-diary-42/);
  assert.deepEqual(errors, []);
  results.push({ name: 'api-generated-patch-delete', passed: true, screenshots: 1 });
  await context.close();
}

async function apiManualError() {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  const page = await context.newPage();
  const errors = errorsFor(page, (text) => /503 \(Service Unavailable\)/.test(text));
  const requests = [];
  await installBaseApiRoutes(page, async (route, request, url) => {
    if (url.pathname === '/api/diary-entries' && request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' });
    } else if (url.pathname === '/api/diary-entries' && request.method() === 'POST') {
      requests.push(request.postDataJSON());
      await new Promise((resolve) => setTimeout(resolve, 180));
      await route.fulfill({
        status: 503, contentType: 'application/json', body: '{"detail":"private diary failure"}',
      });
    } else await route.abort();
  });
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  await openToday(page);
  await page.getByRole('button', { name: '日记', exact: true }).click();
  await page.getByRole('button', { name: '写一篇' }).click();
  await page.locator('[data-hook="diary-title"]').fill('  保留标题空白  ');
  await page.locator('[data-hook="diary-body"]').fill('  保留正文空白  ');
  await page.locator('[data-hook="diary-submit"]').evaluate((button) => {
    button.click();
    button.click();
  });
  await page.locator('[data-hook="diary-error"]:visible').waitFor();
  await page.locator('[data-hook="diary-error"]').evaluate((node) => {
    node.scrollIntoView({ block: 'nearest' });
  });
  assert.deepEqual(requests, [{
    date: '2026-07-26', title: '  保留标题空白  ', body: '  保留正文空白  ', status: 'saved',
  }]);
  assert.equal(await page.locator('[data-hook="diary-title"]').inputValue(), '  保留标题空白  ');
  assert.equal(await page.locator('[data-hook="diary-body"]').inputValue(), '  保留正文空白  ');
  assert.doesNotMatch(await page.locator('body').innerText(), /private diary failure/);
  await page.screenshot({
    path: new URL('desktop-diary-api-error.png', outputDir).pathname,
    fullPage: true,
    animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'api-manual-error', passed: true, screenshots: 1 });
  await context.close();
}

try {
  await fixtureDesktop();
  await fixtureMobileLongBody();
  await apiGeneratedPatchAndDelete();
  await apiManualError();
  await writeFile(
    new URL('browser-acceptance.json', outputDir),
    `${JSON.stringify({ passed: true, results }, null, 2)}\n`,
  );
  console.log('B6_BROWSER_ACCEPTANCE_OK scenarios=4 screenshots=6');
} finally {
  await browser.close();
}
