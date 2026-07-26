import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL(
  '../../docs/front_design/acceptance/tasks-routines-s3-b4/',
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

async function fixtureDesktop() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);

  await page.getByRole('button', { name: '任务', exact: true }).click();
  await page.getByText('这里还没有任务').waitFor();
  assert.equal(await page.locator('[data-hook="task-panel"]').isVisible(), true);
  assert.equal(await page.locator('[data-hook="today-panel"]').isVisible(), false);
  await page.screenshot({
    path: new URL('desktop-task-empty.png', outputDir).pathname,
    fullPage: true,
  });

  await page.getByRole('button', { name: '凝结新任务' }).click();
  await page.locator('[data-hook="task-form"]').waitFor();
  await page.locator('[data-hook="task-title"]').fill('给阳台的植物浇水');
  await page.locator('[data-hook="task-description"]').fill('只浇一点，看看叶子的颜色。');
  await page.locator('[data-hook="task-due-at"]').fill('2026-07-27T09:30');
  await page.locator('[data-hook="task-priority"]').selectOption('high');
  await page.getByRole('button', { name: '创建任务' }).click();
  await page.getByRole('heading', { name: '给阳台的植物浇水' }).waitFor();

  await page.locator('[data-hook="task-step-title"]').fill('先摸摸土壤');
  await page.getByRole('button', { name: '添加' }).click();
  await page.getByRole('button', { name: '先摸摸土壤' }).waitFor();
  await page.getByRole('button', { name: '开始进行' }).click();
  await page.getByText('进行中', { exact: true }).waitFor();
  await page.getByRole('button', { name: '先摸摸土壤' }).click();
  assert.equal(
    await page.getByRole('button', { name: '先摸摸土壤' }).getAttribute('aria-pressed'),
    'true',
  );
  await page.getByRole('button', { name: '归档任务' }).click();
  assert.equal(await page.locator('[data-hook="task-confirmation"]').isVisible(), true);
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await page.screenshot({
    path: new URL('desktop-task-detail.png', outputDir).pathname,
    fullPage: true,
  });

  await page.locator('[data-hook="task-back"]').click();
  await page.getByRole('button', { name: /给阳台的植物浇水/ }).waitFor();
  await page.locator('[data-hook="task-back"]').click();
  await page.locator('[data-hook="today-panel"]').waitFor();

  await page.getByRole('button', { name: '日常', exact: true }).click();
  await page.getByText('还没有固定日常').waitFor();
  await page.getByRole('button', { name: '培养新日常' }).click();
  await page.locator('[data-hook="routine-title"]').fill('睡前伸展');
  await page.locator('[data-hook="routine-schedule"]').selectOption('daily');
  await page.locator('[data-hook="routine-reminder-policy"]').selectOption('remind');
  await page.getByRole('button', { name: '创建日常' }).click();
  await page.getByRole('heading', { name: '睡前伸展' }).waitFor();
  await page.getByRole('button', { name: '照看今天' }).click();
  const checked = page.getByRole('button', { name: '今日已照看' });
  await checked.waitFor();
  assert.equal(await checked.isDisabled(), true);
  await page.screenshot({
    path: new URL('desktop-routine-checked.png', outputDir).pathname,
    fullPage: true,
  });

  await page.getByRole('button', { name: '停用习惯' }).click();
  await page.getByRole('button', { name: '确认停用' }).click();
  await page.getByText('已停用', { exact: true }).waitFor();
  assert.equal(await page.locator('[data-hook="routine-checkin"]').isVisible(), false);
  assert.equal(await page.locator('[data-hook="routine-deactivate"]').isVisible(), false);
  await page.screenshot({
    path: new URL('desktop-routine-inactive.png', outputDir).pathname,
    fullPage: true,
  });

  await page.getByRole('button', { name: '关闭今日光影' }).click();
  await page.getByRole('button', { name: '打开今日摘要' }).click();
  await page.locator('[data-hook="today-panel"]').waitFor();
  assert.equal(await page.locator('[data-hook="routine-panel"]').isVisible(), false);
  assert.deepEqual(errors, []);
  results.push({ name: 'fixture-desktop', passed: true, screenshots: 4 });
  await context.close();
}

async function fixtureMobile() {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  await page.getByRole('button', { name: '任务', exact: true }).click();
  await page.getByText('这里还没有任务').waitFor();
  await page.getByRole('button', { name: '凝结新任务' }).click();
  await page.locator('[data-hook="task-title"]').fill('一段很长但仍然应该安静换行的任务标题'.repeat(3));
  await page.evaluate(() => { document.body.dataset.keyboardVisible = 'true'; });
  await page.locator('[data-hook="task-title"]').focus();
  assert.equal(await page.locator('[data-hook="task-title"]').evaluate((node) => node === document.activeElement), true);
  const layout = await page.locator('#today-overlay').evaluate((node) => ({
    scrollWidth: node.scrollWidth,
    clientWidth: node.clientWidth,
  }));
  assert.ok(layout.scrollWidth <= layout.clientWidth + 1, JSON.stringify(layout));
  const heights = await page.locator('[data-hook="task-form"] button:visible').evaluateAll(
    (nodes) => nodes.map((node) => node.getBoundingClientRect().height),
  );
  assert.ok(heights.every((height) => height >= 44), JSON.stringify(heights));
  await page.screenshot({
    path: new URL('mobile-task-form-keyboard.png', outputDir).pathname,
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'fixture-mobile', passed: true, screenshots: 1 });
  await context.close();
}

async function apiErrorAndDoubleSubmit() {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  const page = await context.newPage();
  const errors = [];
  let createRequests = 0;
  page.on('console', (entry) => {
    if (entry.type() === 'error' && !/503 \(Service Unavailable\)/.test(entry.text())) {
      errors.push(entry.text());
    }
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/state') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ state: { mood: 'calm' } }),
      });
    } else if (path === '/api/today') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          date: '2026-07-26', active_activities: [], calendar_events: [], due_tasks: [],
          routines: [], overdue_tasks: [], open_tasks: [], completed_tasks: [],
        }),
      });
    } else if (path === '/api/tasks' && request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' });
    } else if (path === '/api/tasks' && request.method() === 'POST') {
      createRequests += 1;
      await new Promise((resolve) => setTimeout(resolve, 250));
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'internal detail must never render' }),
      });
    } else {
      await route.abort();
    }
  });
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  await openToday(page);
  await page.getByRole('button', { name: '任务', exact: true }).click();
  await page.getByText('这里还没有任务').waitFor();
  await page.getByRole('button', { name: '凝结新任务' }).click();
  await page.locator('[data-hook="task-title"]').fill('不会重复提交');
  await page.locator('[data-hook="task-submit"]').evaluate((button) => {
    button.click();
    button.click();
  });
  await page.locator('[data-hook="task-error"]:visible').waitFor();
  assert.equal(createRequests, 1);
  assert.match(await page.locator('[data-hook="task-error"]').innerText(), /栖光暂时无法回应/);
  assert.doesNotMatch(await page.locator('body').innerText(), /internal detail must never render/);
  assert.deepEqual(errors, []);
  await page.screenshot({
    path: new URL('desktop-task-api-error.png', outputDir).pathname,
    fullPage: true,
  });
  results.push({ name: 'api-error-double-submit', passed: true, screenshots: 1 });
  await context.close();
}

try {
  await fixtureDesktop();
  await fixtureMobile();
  await apiErrorAndDoubleSubmit();
  await writeFile(
    new URL('browser-acceptance.json', outputDir),
    `${JSON.stringify({ passed: true, results }, null, 2)}\n`,
  );
  console.log('B4_BROWSER_ACCEPTANCE_OK scenarios=3 screenshots=6');
} finally {
  await browser.close();
}
