import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL('../../docs/front_design/acceptance/action-light-tag-s3-b8/', import.meta.url);
await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

function collectErrors(page) {
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function fixturePage(context) {
  const page = await context.newPage();
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status]:not([data-js-loading])').waitFor();
  await page.waitForFunction(() => typeof window.__luminousActionFixture?.propose === 'function');
  return page;
}

async function propose(page, proposal) {
  await page.evaluate((value) => { void window.__luminousActionFixture.propose(value); }, proposal);
}

async function desktopPreviewConfirmCancel() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await fixturePage(context);
  const errors = collectErrors(page);
  await propose(page, {
    action: 'create_task',
    payload: {
      title: '给窗边的植物浇水', priority: 'normal',
      due_at: '2026-07-27T09:00:00Z', metadata: { private: true },
    },
  });
  const card = page.locator('[data-hook="action-card"]');
  await page.locator('[data-hook="action-card"][data-action-status="preview_ready"]').waitFor();
  await page.getByText('创建任务：给窗边的植物浇水').waitFor();
  assert.doesNotMatch(await card.innerText(), /metadata|private|create_task/);
  await page.screenshot({
    path: new URL('desktop-action-preview-ready.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });

  await page.getByRole('button', { name: '确认让它发生' }).click();
  await page.getByRole('heading', { name: '这束光已经落定' }).waitFor();
  await page.screenshot({
    path: new URL('desktop-action-success.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  await page.waitForFunction(() => window.__luminousActionFixture.state() === 'idle');

  await propose(page, { action: 'start_focus_session', payload: { title: '安静专注二十分钟' } });
  await page.getByRole('button', { name: '婉拒' }).waitFor();
  await page.getByRole('button', { name: '婉拒' }).click();
  await page.getByRole('heading', { name: '光签已经收起' }).waitFor();
  assert.match(await card.innerText(), /没有发送确认请求/);
  await page.screenshot({
    path: new URL('desktop-action-cancelled.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'desktop-preview-confirm-cancel', passed: true, screenshots: 3 });
  await context.close();
}

async function missingMappingNoLeak() {
  const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
  const page = await fixturePage(context);
  const errors = collectErrors(page);
  await propose(page, {
    action: 'complete_task', payload: { task_id: 'server-secret-task-should-never-render' },
  });
  const card = page.locator('[data-hook="action-card"][data-action-status="preview_error"]');
  await card.waitFor();
  assert.match(await card.innerText(), /已经不在这里/);
  assert.equal(await page.getByRole('button', { name: '确认让它发生' }).count(), 0);
  assert.doesNotMatch(await page.locator('body').evaluate((body) => body.outerHTML), /server-secret-task-should-never-render/);
  await page.screenshot({
    path: new URL('desktop-action-missing-mapping.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  await page.getByRole('button', { name: '忽略这项建议' }).click();
  assert.deepEqual(errors, []);
  results.push({ name: 'missing-mapping-no-leak', passed: true, screenshots: 1 });
  await context.close();
}

async function diaryAndMobileReducedMotion() {
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  let page = await fixturePage(desktop);
  let errors = collectErrors(page);
  await propose(page, { action: 'draft_diary', payload: { date: '2026-07-25', title: 'must-drop' } });
  await page.getByRole('button', { name: '确认让它发生' }).waitFor();
  assert.doesNotMatch(await page.locator('[data-hook="action-card"]').innerText(), /must-drop|标题/);
  await page.getByRole('button', { name: '确认让它发生' }).click();
  await page.locator('#today-overlay[open]').waitFor();
  await page.locator('[data-hook="diary-form"]:visible').waitFor();
  assert.equal(await page.locator('[data-hook="diary-title"]').inputValue(), '日记草稿');
  await page.screenshot({
    path: new URL('desktop-action-diary-enters-persisted-editor.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  await desktop.close();

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 }, reducedMotion: 'reduce',
  });
  page = await fixturePage(mobile);
  errors = collectErrors(page);
  await propose(page, {
    action: 'create_task',
    payload: { title: '这是一项很长的行动建议，用来确认移动端光签会自然换行并且不会遮住输入水面' },
  });
  const card = page.locator('[data-hook="action-card"][data-action-status="preview_ready"]');
  await card.waitFor();
  const layout = await card.evaluate((node) => ({
    scrollWidth: node.scrollWidth, clientWidth: node.clientWidth,
  }));
  assert.ok(layout.scrollWidth <= layout.clientWidth + 1, JSON.stringify(layout));
  const heights = await card.locator('button').evaluateAll(
    (nodes) => nodes.map((entry) => entry.getBoundingClientRect().height),
  );
  assert.ok(heights.every((height) => height >= 44), JSON.stringify(heights));
  const animations = await card.locator('*').evaluateAll(
    (nodes) => [...new Set(nodes.map((entry) => getComputedStyle(entry).animationName))],
  );
  assert.deepEqual(animations.filter((name) => name !== 'none'), []);
  await page.screenshot({
    path: new URL('mobile-action-preview-reduced-motion.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'diary-mobile-reduced-motion', passed: true, screenshots: 2 });
  await mobile.close();
}

try {
  await desktopPreviewConfirmCancel();
  await missingMappingNoLeak();
  await diaryAndMobileReducedMotion();
  console.log(JSON.stringify({ passed: true, results }, null, 2));
} finally {
  await browser.close();
}
