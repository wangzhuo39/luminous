import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL('../../docs/front_design/acceptance/reminder-calendar-s3-b7/', import.meta.url);
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

function collectErrors(page) {
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function desktopReminderFlow() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = collectErrors(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  await expandLifeFlow(page);
  await page.getByRole('button', { name: '提醒', exact: true }).click();
  await page.getByRole('button', { name: /给自己留一点时间休息/ }).waitFor();
  await page.screenshot({
    path: new URL('desktop-reminder-light-dust-list.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });

  await page.getByRole('button', { name: /给自己留一点时间休息/ }).click();
  await page.getByRole('heading', { name: '给自己留一点时间休息' }).waitFor();
  await page.getByRole('button', { name: '稍后提醒' }).click();
  await page.locator('[data-hook="reminder-snooze-at"]').fill('2026-07-26T18:30');
  await page.screenshot({
    path: new URL('desktop-reminder-exact-snooze.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  await page.getByRole('button', { name: '确认时间' }).click();
  await page.getByText('稍后再来', { exact: true }).waitFor();
  await page.getByRole('button', { name: '取消提醒' }).click();
  const confirmation = page.locator('[data-hook="reminder-confirmation"]');
  await confirmation.waitFor();
  assert.match(await confirmation.innerText(), /保留在已经落定的光尘中/);
  await page.getByRole('button', { name: '确认取消' }).click();
  await page.getByText('已经取消', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: '稍后提醒' }).count(), 0);
  assert.deepEqual(errors, []);
  results.push({ name: 'desktop-reminder-flow', passed: true, screenshots: 2 });
  await context.close();
}

async function desktopCalendarFlow() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = collectErrors(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  await expandLifeFlow(page);
  await page.getByRole('button', { name: '日历', exact: true }).click();
  await page.getByRole('button', { name: /上午有一次重要的会议提醒/ }).waitFor();
  await page.screenshot({
    path: new URL('desktop-calendar-window-scale.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });

  await page.getByRole('button', { name: /上午有一次重要的会议提醒/ }).click();
  await page.getByRole('button', { name: '编辑', exact: true }).click();
  await page.locator('[data-hook="calendar-all-day"]').check();
  await page.locator('[data-hook="calendar-start-date"]').fill('2026-07-26');
  await page.locator('[data-hook="calendar-end-date"]').fill('2026-07-27');
  assert.equal(await page.locator('[data-hook="calendar-timed-fields"]').isVisible(), false);
  assert.equal(await page.locator('[data-hook="calendar-date-fields"]').isVisible(), true);
  await page.screenshot({
    path: new URL('desktop-calendar-all-day-form.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  await page.getByRole('button', { name: '保存变化' }).click();
  await page.getByText(/全天/).first().waitFor();
  await page.getByRole('button', { name: '移出窗框' }).click();
  const confirmation = page.locator('[data-hook="calendar-confirmation"]');
  await confirmation.waitFor();
  assert.match(await confirmation.innerText(), /从日历窗框移出这个刻度/);
  assert.doesNotMatch(await confirmation.innerText(), /恢复|撤销|永久/);
  await page.screenshot({
    path: new URL('desktop-calendar-remove-confirmation.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  await page.getByRole('button', { name: '确认移出' }).click();
  await page.getByText('窗框上还没有落下时间刻度。').waitFor();
  assert.deepEqual(errors, []);
  results.push({ name: 'desktop-calendar-flow', passed: true, screenshots: 3 });
  await context.close();
}

async function mobileFormsAndReducedMotion() {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  const errors = collectErrors(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'domcontentloaded' });
  await openToday(page);
  await expandLifeFlow(page);
  await page.getByRole('button', { name: '提醒', exact: true }).click();
  await page.getByRole('button', { name: '留下一粒提醒' }).click();
  await page.locator('[data-hook="reminder-title"]').fill('这是一条很长的提醒标题，用来确认移动端会自然换行而不会从晶格温室的雾面边界溢出');
  await page.locator('[data-hook="reminder-due-at"]').fill('2026-07-29T09:00');
  await page.evaluate(() => { document.body.dataset.keyboardVisible = 'true'; });
  const reminderLayout = await page.locator('#today-overlay').evaluate((node) => ({
    scrollWidth: node.scrollWidth, clientWidth: node.clientWidth,
  }));
  assert.ok(reminderLayout.scrollWidth <= reminderLayout.clientWidth + 1, JSON.stringify(reminderLayout));
  await page.screenshot({
    path: new URL('mobile-reminder-form-keyboard.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  await page.getByRole('button', { name: '取消' }).click();
  await page.getByRole('button', { name: '← 返回' }).click();
  await expandLifeFlow(page);
  await page.getByRole('button', { name: '日历', exact: true }).click();
  await page.getByRole('button', { name: '落下一段时间' }).click();
  await page.locator('[data-hook="calendar-title"]').fill('全天休息');
  await page.locator('[data-hook="calendar-all-day"]').check();
  await page.locator('[data-hook="calendar-start-date"]').fill('2026-07-30');
  const heights = await page.locator('[data-hook="calendar-form"] :is(input, button)').evaluateAll(
    (nodes) => nodes
      .filter((entry) => entry.getClientRects().length > 0)
      .map((entry) => entry.getBoundingClientRect().height),
  );
  assert.ok(heights.every((height) => height >= 44), JSON.stringify(heights));
  const animations = await page.locator('[data-hook="calendar-panel"] *').evaluateAll(
    (nodes) => [...new Set(nodes.map((entry) => getComputedStyle(entry).animationName))],
  );
  assert.deepEqual(animations.filter((name) => name !== 'none'), []);
  await page.screenshot({
    path: new URL('mobile-calendar-all-day-reduced-motion.png', outputDir).pathname,
    fullPage: true, animations: 'disabled',
  });
  assert.deepEqual(errors, []);
  results.push({ name: 'mobile-forms-reduced-motion', passed: true, screenshots: 2 });
  await context.close();
}

try {
  await desktopReminderFlow();
  await desktopCalendarFlow();
  await mobileFormsAndReducedMotion();
  console.log(JSON.stringify({ passed: true, results }, null, 2));
} finally {
  await browser.close();
}
