import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { test } from 'node:test';

const projectRoot = new URL('../../', import.meta.url).pathname;

async function waitForServer(url) {
  let lastError = null;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
    } catch (error) { lastError = error; }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw lastError ?? new Error('static server did not become ready');
}

test('bundled HTTP server serves PWA assets with explicit MIME and hardening headers', async () => {
  const port = 4197;
  const server = spawn('luminous-api', [
    '--host', '127.0.0.1', '--port', String(port), '--mock', '--deployment-mode', 'local',
  ], {
    cwd: projectRoot,
    stdio: 'ignore',
  });
  try {
    const manifest = await waitForServer(`http://127.0.0.1:${port}/manifest.webmanifest`);
    assert.match(manifest.headers.get('content-type') ?? '', /^application\/manifest\+json/);
    assert.equal(manifest.headers.get('cache-control'), 'no-cache');
    assert.equal(manifest.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(manifest.headers.get('referrer-policy'), 'no-referrer');
    assert.equal(
      manifest.headers.get('permissions-policy'),
      'camera=(), geolocation=(), microphone=(self)',
    );
    const serviceWorker = await fetch(`http://127.0.0.1:${port}/service-worker.js`);
    assert.equal(serviceWorker.status, 200);
    assert.match(serviceWorker.headers.get('content-type') ?? '', /javascript/);
  } finally {
    server.kill('SIGTERM');
    await Promise.race([once(server, 'exit'), new Promise((resolve) => setTimeout(resolve, 1000))]);
  }
});
