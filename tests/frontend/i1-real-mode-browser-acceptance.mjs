import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import net from 'node:net';
import { chromium } from 'playwright';

const repoRoot = resolve(new URL('../..', import.meta.url).pathname);
const frontendDir = join(repoRoot, 'apps/companion-web/companion-ui');
const forbidden = new Set([
  'trace_id', 'turn_id', 'role_thinking', 'role_action', 'system_thinking',
  'analysis', 'prompt', 'ledger', 'recent_events', 'raw_messages', 'jobs',
]);

function findForbidden(value, found = new Set()) {
  if (Array.isArray(value)) value.forEach((item) => findForbidden(item, found));
  else if (value && typeof value === 'object') {
    Object.keys(value).forEach((key) => { if (forbidden.has(key)) found.add(key); });
    Object.values(value).forEach((item) => findForbidden(item, found));
  }
  return found;
}

function freePort() {
  return new Promise((resolvePort, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolvePort(port));
    });
  });
}

async function waitForServer(child, port) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/health`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw new Error(`backend did not start: ${child.exitCode}`);
}

function progress(stage) {
  if (process.env.LUMINOUS_TEST_PROGRESS === '1') console.log(`I1_PROGRESS ${stage}`);
}

async function readResponseBody(response) {
  let timeoutId;
  try {
    return await Promise.race([
      response.json().catch(() => null),
      new Promise((resolve) => { timeoutId = setTimeout(() => resolve(null), 5_000); }),
    ]);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function stopChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once('exit', resolve));
  child.kill('SIGTERM');
  const stopped = await Promise.race([
    exited.then(() => true),
    new Promise((resolve) => setTimeout(() => resolve(false), 5_000)),
  ]);
  if (!stopped && child.exitCode === null && child.signalCode === null) {
    child.kill('SIGKILL');
    await exited;
  }
}

async function call(baseUrl, path, options = {}) {
  const response = await fetch(baseUrl + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const body = await response.json();
  assert.ok(response.ok, `${options.method ?? 'GET'} ${path}: ${JSON.stringify(body)}`);
  return body;
}

const dataRoot = await mkdtemp(join(tmpdir(), 'luminous-i1-browser-'));
const port = await freePort();
const baseUrl = `http://127.0.0.1:${port}`;
const child = spawn('python3', [
  '-m', 'luminous.runtime.infrastructure.http',
  '--project-root', dataRoot,
  '--frontend', frontendDir,
  '--env', join(dataRoot, '.env'),
  '--mock', '--host', '127.0.0.1', '--port', String(port),
], { cwd: repoRoot, env: { ...process.env, PYTHONPATH: repoRoot }, stdio: ['ignore', 'pipe', 'pipe'] });
let stderr = '';
child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

try {
  progress('server-starting');
  await waitForServer(child, port);
  progress('server-ready');
  await call(baseUrl, '/api/chat', { method: 'POST', body: { message: '先在这里留下一点真实历史。', history: [] } });
  await call(baseUrl, '/api/tasks', {
    method: 'POST',
    body: { title: '浏览器验收任务', due_at: new Date().toISOString(), priority: 'normal' },
    headers: { 'Idempotency-Key': 'browser-seed-task' },
  });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10_000);
  const errors = [];
  const apiBodies = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('response', (response) => {
    if (new URL(response.url()).pathname.startsWith('/api/')) {
      apiBodies.push(readResponseBody(response));
    }
  });

  await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  progress('browser-ready');
  assert.doesNotMatch(page.url(), /mode=fixture/);

  const browserFlow = await page.evaluate(async () => {
    let requestCounter = 0;
    async function request(path, method = 'GET', body = undefined) {
      requestCounter += 1;
      const response = await fetch(path, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': `browser-flow-${requestCounter}`,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(`${method} ${path}: ${JSON.stringify(payload)}`);
      return payload;
    }

    const task = await request('/api/tasks', 'POST', { title: '浏览器全栈任务', priority: 'normal' });
    const routine = await request('/api/routines', 'POST', { title: '浏览器全栈日常', schedule: 'daily' });
    await request(`/api/routines/${routine.routine.routine_id}/checkins`, 'POST', { period_key: new Date().toISOString().slice(0, 10) });
    const activity = await request('/api/activities', 'POST', { title: '浏览器全栈活动' });
    await request(`/api/activities/${activity.activity.session_id}/start`, 'POST', {});
    await request('/api/diary-entries', 'POST', { title: '浏览器全栈日记', body: '真实浏览器写入。', date: new Date().toISOString().slice(0, 10) });
    const future = new Date(Date.now() + 3_600_000).toISOString();
    await request('/api/reminders', 'POST', { title: '浏览器全栈提醒', due_at: future });
    await request('/api/calendar-events', 'POST', { title: '浏览器全栈日历', starts_at: future });
    await request('/api/settings/notifications', 'PATCH', { daily_limit: 2 });
    await request('/api/chat', 'POST', { message: '我喜欢夏夜散步，请记住。', history: [] });
    const memories = await request(`/api/memory?q=${encodeURIComponent('夏夜')}&limit=10`);
    const memoryId = memories.hits[0]?.memory_id;
    if (!memoryId) throw new Error('browser memory was not created');
    await request('/api/memory/update', 'POST', { memory_id: memoryId, updates: { text: '我喜欢安静的夏夜散步。' } });
    await request('/api/memory/forget', 'POST', { memory_id: memoryId, hard_delete: false });
    const preview = await request('/api/actions/preview', 'POST', { action: 'create_task', payload: { title: '浏览器确认任务' } });
    const confirmed = await request('/api/actions/confirm', 'POST', { action: preview.action, payload: preview.payload, confirmed: true });
    await request('/api/today');
    await request('/api/timeline');
    await request('/api/outbox');
    return {
      taskId: task.task.task_id,
      actionConfirmed: confirmed.ok,
    };
  });
  assert.ok(browserFlow.taskId);
  assert.equal(browserFlow.actionConfirmed, true);
  progress('browser-api-flow-complete');

  const messagesBefore = await page.locator('[data-hook="dialogue-stream"] .message').count();
  await page.locator('[data-hook="chat-input"]').fill('浏览器真实模式问候。');
  await page.locator('[data-hook="send-button"]').click();
  await page.waitForResponse((response) => response.url().includes('/api/chat') && response.request().method() === 'POST');
  await page.waitForFunction((before) => document.querySelectorAll('[data-hook="dialogue-stream"] .message').length >= before + 2, messagesBefore);
  assert.equal(await page.locator('[data-hook="chat-input"]').inputValue(), '');
  progress('browser-chat-complete');

  await page.locator('#today-portal').click();
  await page.locator('#today-overlay[data-today-status="ready"]').waitFor();
  assert.match(await page.locator('[data-hook="today-panel"]').innerText(), /浏览器验收任务/);

  await page.locator('#today-overlay .dialog-close-btn').click();
  progress('today-space-complete');

  await page.locator('#memory-portal').click();
  await page.locator('#memory-overlay[open]').waitFor();
  await page.locator('#memory-overlay .dialog-close-btn').click();
  progress('memory-space-complete');

  await page.locator('#privacy-portal').click();
  await page.locator('#privacy-overlay[open]').waitFor();
  await page.locator('#privacy-overlay .dialog-close-btn').click();
  progress('privacy-space-complete');

  await page.locator('#outbox-portal').click();
  await page.locator('#outbox-overlay[open]').waitFor();
  await page.locator('#outbox-overlay .dialog-close-btn').click();
  progress('outbox-space-complete');

  const readLayoutSnapshot = async () => page.evaluate(() => {
    const selectors = ['#dialogue-stream', '#input-surface', '#today-portal', '#memory-portal', '#privacy-portal', '#outbox-portal'];
    const rect = (selector) => {
      const element = document.querySelector(selector);
      const box = element?.getBoundingClientRect();
      return box ? { left: box.left, top: box.top, right: box.right, bottom: box.bottom } : null;
    };
    const area = (first, second) => first && second
      ? Math.max(0, Math.min(first.right, second.right) - Math.max(first.left, second.left))
        * Math.max(0, Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top))
      : 0;
    const dialogue = document.querySelector('#dialogue-stream');
    const boxes = Object.fromEntries(selectors.map((selector) => [selector, rect(selector)]));
    return {
      atLatest: dialogue.scrollTop + dialogue.clientHeight >= dialogue.scrollHeight - 2,
      overlaps: Object.fromEntries(selectors.slice(1).map((selector) => [selector, area(boxes['#dialogue-stream'], boxes[selector])])),
    };
  });
  const layoutSnapshot = await readLayoutSnapshot();
  assert.equal(layoutSnapshot.atLatest, true);
  assert.deepEqual(layoutSnapshot.overlaps, {
    '#input-surface': 0,
    '#today-portal': 0,
    '#memory-portal': 0,
    '#privacy-portal': 0,
    '#outbox-portal': 0,
  });
  progress('desktop-layout-complete');

  await page.setViewportSize({ width: 430, height: 932 });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('body[data-app-status="ready"]:not([data-js-loading])').waitFor();
  progress('mobile-reload-ready');
  await page.waitForTimeout(100);
  const mobileLayout = await readLayoutSnapshot();
  assert.equal(mobileLayout.atLatest, true);
  assert.deepEqual(mobileLayout.overlaps, {
    '#input-surface': 0,
    '#today-portal': 0,
    '#memory-portal': 0,
    '#privacy-portal': 0,
    '#outbox-portal': 0,
  });
  progress('mobile-layout-complete');

  await page.waitForTimeout(200);
  const bodies = await Promise.all(apiBodies);
  progress('api-bodies-complete');
  const leaks = bodies.flatMap((body) => [...findForbidden(body ?? {})]);
  assert.deepEqual([...new Set(leaks)], []);
  assert.deepEqual(errors, []);
  await context.close();
  await browser.close();
  progress('browser-closed');

  await stopChild(child);
  progress('server-stopped');
  const restarted = spawn('python3', [
    '-m', 'luminous.runtime.infrastructure.http', '--project-root', dataRoot,
    '--frontend', frontendDir, '--env', join(dataRoot, '.env'),
    '--mock', '--host', '127.0.0.1', '--port', String(port),
  ], { cwd: repoRoot, env: { ...process.env, PYTHONPATH: repoRoot }, stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    await waitForServer(restarted, port);
    progress('restart-ready');
    const restored = await call(baseUrl, '/api/state?include=history');
    assert.ok(restored.history.items.some((item) => item.content.includes('真实历史')));
    const tasks = await call(baseUrl, '/api/tasks?limit=10');
    assert.ok(tasks.items.some((item) => item.title === '浏览器验收任务'));
  } finally {
    await stopChild(restarted);
  }
  console.log('I1_REAL_MODE_BROWSER_OK chat=restored life_flow=complete memory=edited-forgotten action=confirmed network_boundary=clean restart=persistent');
} catch (error) {
  throw new Error(`${error.message}\nbackend stderr: ${stderr.slice(-2000)}`);
} finally {
  await stopChild(child);
  await rm(dataRoot, { recursive: true, force: true });
}
