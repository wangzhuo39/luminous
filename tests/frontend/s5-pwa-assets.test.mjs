import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { test } from 'node:test';

const root = new URL('../../apps/companion-web/companion-ui/', import.meta.url);

test('manifest exposes installable identity and required maskable PNG sizes', async () => {
  const manifest = JSON.parse(await readFile(new URL('manifest.webmanifest', root), 'utf8'));
  assert.equal(manifest.name, '栖光 Luminous');
  assert.equal(manifest.start_url, './');
  assert.equal(manifest.scope, './');
  assert.equal(manifest.display, 'standalone');
  assert.equal(manifest.prefer_related_applications, false);
  assert.deepEqual(manifest.icons.map((icon) => icon.sizes), ['192x192', '512x512']);
  assert.ok(manifest.icons.every((icon) => icon.purpose.includes('maskable')));
  await Promise.all(manifest.icons.map((icon) => access(new URL(icon.src, root))));
});

test('service worker precaches every declared shell asset and never caches API traffic', async () => {
  const source = await readFile(new URL('service-worker.js', root), 'utf8');
  const list = source.match(/const SHELL_ASSETS = \[(.*?)\];/s)?.[1] ?? '';
  const assets = [...list.matchAll(/'([^']+)'/g)].map((match) => match[1]);
  assert.ok(assets.length > 40);
  await Promise.all(assets.filter((asset) => asset !== './').map((asset) => access(new URL(asset, root))));
  assert.match(source, /url\.pathname\.startsWith\('\/api\/'\)/);
  assert.match(source, /request\.mode === 'navigate'/);
  assert.match(source, /SKIP_WAITING/);
  assert.doesNotMatch(source, /BackgroundSync|PushManager|Notification\.requestPermission|indexedDB/i);
});
