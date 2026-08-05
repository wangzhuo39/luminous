import { createHash } from 'node:crypto';
import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(root, 'apps/companion-web/companion-ui');
const output = resolve(root, 'apps/companion-android/dist');
const nativeEntry = resolve(root, 'apps/companion-android/native-entry.js');

async function frontendRevision(directory, relative = '') {
  const hash = createHash('sha256');
  const visit = async (current, prefix) => {
    const entries = await readdir(current, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const entryRelative = prefix ? `${prefix}/${entry.name}` : entry.name;
      const entryPath = resolve(current, entry.name);
      if (entry.isDirectory()) {
        await visit(entryPath, entryRelative);
      } else if (/\.(?:css|html|js|webmanifest)$/.test(entry.name)) {
        hash.update(entryRelative);
        hash.update(await readFile(entryPath));
      }
    }
  };
  await visit(directory, relative);
  return hash.digest('hex').slice(0, 12);
}

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(source, output, { recursive: true });
await rm(resolve(output, 'downloads'), { recursive: true, force: true });

const indexPath = resolve(output, 'index.html');
const index = await readFile(indexPath, 'utf8');
const marker = '<script type="module" src="js/main.js"></script>';
if (!index.includes(marker)) throw new Error('Android web build could not find the main module marker');
const revision = await frontendRevision(output);
const bootstrapName = `android-bootstrap-${revision}.js`;
await writeFile(resolve(output, bootstrapName), `
const registrations = await navigator.serviceWorker?.getRegistrations?.().catch(() => []) || [];
await Promise.all(registrations.map((registration) => registration.unregister()));
const cacheKeys = await globalThis.caches?.keys?.().catch(() => []) || [];
await Promise.all(cacheKeys.filter((key) => key.startsWith('luminous-shell-')).map((key) => caches.delete(key)));
await import('./js/main.js?android=${revision}');
`, 'utf8');
await writeFile(
  indexPath,
  index.replace(marker, `<script type="module" src="native-runtime.js"></script>\n  <script type="module" src="${bootstrapName}"></script>`),
  'utf8',
);

await build({
  entryPoints: [nativeEntry],
  outfile: resolve(output, 'native-runtime.js'),
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: ['chrome120'],
  minify: true,
  sourcemap: false,
});

const androidBundleRequirements = [
  ['index.html', [
    'data-hook="companion-settings-form"',
    'data-hook="companion-api-key"',
    'data-hook="companion-instructions"',
    'android-bootstrap-',
  ]],
  ['js/services/silent-spaces-api.js', ['/api/settings/companion', 'saveCompanionSettings']],
  ['js/features/silent-spaces/silent-spaces-controller.js', ['activate', 'saveCompanionSettings']],
];

for (const [relativePath, requiredText] of androidBundleRequirements) {
  const content = await readFile(resolve(output, relativePath), 'utf8');
  for (const expected of requiredText) {
    if (!content.includes(expected)) {
      throw new Error(`Android web bundle is missing ${expected} in ${relativePath}`);
    }
  }
}

console.log(`Android web assets built at ${output}`);
