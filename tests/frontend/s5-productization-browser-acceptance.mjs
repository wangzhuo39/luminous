import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const baseUrl = process.env.LUMINOUS_FRONTEND_URL ?? 'http://127.0.0.1:4173';
const outputDir = new URL('../../docs/front_design/acceptance/productization-s5-b1/', import.meta.url);
await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];

function errorsFor(page) {
  const errors = [];
  page.on('console', (entry) => { if (entry.type() === 'error') errors.push(entry.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function waitForApp(page) {
  await page.locator('body[data-app-status]:not([data-js-loading])').waitFor();
}

async function deepLinkAndDraft() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await context.newPage();
  const errors = errorsFor(page);
  await page.goto(`${baseUrl}/?mode=fixture&space=privacy`, { waitUntil: 'domcontentloaded' });
  await waitForApp(page);
  await page.locator('#privacy-overlay[open]').waitFor();
  assert.match(page.url(), /mode=fixture&space=privacy/);
  await page.locator('#privacy-overlay .dialog-close-btn').click();
  await page.locator('#privacy-overlay').waitFor({ state: 'hidden' });
  await page.waitForFunction(() => !new URL(location.href).searchParams.has('space'));
  assert.doesNotMatch(page.url(), /space=/);
  await page.goBack();
  await page.locator('#privacy-overlay[open]').waitFor();
  await page.locator('#privacy-overlay .dialog-close-btn').click();

  const draft = '这段话先留在水面上，等我回来。';
  await page.locator('[data-hook="chat-input"]').fill(draft);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForApp(page);
  assert.equal(await page.locator('[data-hook="chat-input"]').inputValue(), draft);
  await page.locator('[data-hook="draft-notice"]:visible').waitFor();
  await page.screenshot({ path: new URL('desktop-deep-link-draft-recovered.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  assert.deepEqual(errors, []);
  results.push({ name: 'deep-link-draft', passed: true, screenshots: 1 });
  await context.close();
}

async function installEligibility() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await context.newPage();
  const errors = errorsFor(page);
  await page.goto(`${baseUrl}/?mode=fixture&space=privacy`, { waitUntil: 'domcontentloaded' });
  await waitForApp(page);
  assert.equal(await page.locator('[data-hook="install-section"]:visible').count(), 0);
  await page.evaluate(() => {
    const event = new Event('beforeinstallprompt', { cancelable: true });
    event.prompt = async () => {};
    event.userChoice = Promise.resolve({ outcome: 'dismissed' });
    window.dispatchEvent(event);
  });
  await page.locator('[data-hook="install-section"]:visible').waitFor();
  assert.match(await page.locator('[data-hook="install-section"]').innerText(), /回信仍需等待网络恢复/);
  await page.locator('[data-hook="install-section"]').scrollIntoViewIfNeeded();
  const installBox = await page.locator('[data-hook="install-section"]').boundingBox();
  assert.ok(installBox && installBox.y >= 0 && installBox.y + installBox.height <= 860, JSON.stringify(installBox));
  await page.screenshot({ path: new URL('desktop-install-eligible.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  assert.deepEqual(errors, []);
  results.push({ name: 'install-eligibility', passed: true, screenshots: 1 });
  await context.close();
}

async function offlineShell() {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = errorsFor(page);
  await page.goto(`${baseUrl}/?mode=fixture`, { waitUntil: 'networkidle' });
  await waitForApp(page);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.evaluate(() => Boolean(navigator.serviceWorker.controller)), true);
  await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="offline"]:not([data-js-loading])').waitFor();
  assert.equal(await page.locator('#luminous-scene').isVisible(), true);
  assert.equal(await page.locator('[data-hook="companion-figure"]').isVisible(), true);
  assert.equal(await page.locator('[data-hook="dialogue-stream"]').isHidden(), true);
  assert.equal(await page.locator('[data-hook="send-button"]').isDisabled(), true);
  assert.match(await page.locator('[data-hook="chat-input"]').getAttribute('placeholder'), /暂时无法寄出/);
  await page.screenshot({ path: new URL('mobile-offline-shell.png', outputDir).pathname, fullPage: true, animations: 'disabled' });
  assert.deepEqual(errors.filter((message) => !message.includes('ERR_INTERNET_DISCONNECTED')), []);
  results.push({ name: 'offline-shell', passed: true, screenshots: 1 });
  await context.close();
}

try {
  await deepLinkAndDraft();
  await installEligibility();
  await offlineShell();
  console.log(JSON.stringify({ scenarios: results.length, screenshots: results.reduce((sum, item) => sum + item.screenshots, 0), results }));
} finally {
  await browser.close();
}
