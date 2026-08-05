import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import net from 'node:net';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const frontend = resolve(root, 'apps/companion-web/companion-ui');
const scenarios = [
  'crystal-solarium-browser-acceptance.mjs',
  's3-browser-acceptance.mjs',
  's3-b4-browser-acceptance.mjs',
  's3-b5-browser-acceptance.mjs',
  's3-b6-browser-acceptance.mjs',
  's3-b7-browser-acceptance.mjs',
  's3-b8-browser-acceptance.mjs',
  's4-silent-spaces-browser-acceptance.mjs',
  's5-productization-browser-acceptance.mjs',
];

function freePort() {
  return new Promise((resolvePort, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => resolvePort(port));
    });
  });
}

function run(command, args, options = {}) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(command, args, { stdio: 'inherit', ...options });
    child.once('error', reject);
    child.once('exit', (code, signal) => {
      if (code === 0) resolveRun();
      else reject(new Error(`${command} exited with ${code ?? signal}`));
    });
  });
}

async function waitForServer(url) {
  let lastError;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw lastError || new Error(`server did not become ready: ${url}`);
}

async function stopServer(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  child.kill('SIGTERM');
  const stopped = await Promise.race([
    once(child, 'exit').then(() => true),
    new Promise((resolveWait) => setTimeout(() => resolveWait(false), 3_000)),
  ]);
  if (!stopped) child.kill('SIGKILL');
}

const port = await freePort();
const baseUrl = `http://127.0.0.1:${port}`;
const runtimeDir = await mkdtemp(resolve(tmpdir(), 'luminous-browser-'));
const server = spawn(
  resolve(root, '.venv/bin/luminous-api'), [
    '--project-root', root,
    '--env', '/dev/null',
    '--frontend', frontend,
    '--host', '127.0.0.1',
    '--port', String(port),
    '--deployment-mode', 'local',
    '--mock',
  ],
  {
    stdio: ['ignore', 'ignore', 'inherit'],
    env: {
      ...process.env,
      LUMINOUS_RUNTIME_DATA_DIR: runtimeDir,
      LUMINOUS_TESTER_ACCESS_CODE: '',
      LUMINOUS_SESSION_SECRET: '',
      LUMINOUS_AUTH_TOKEN: '',
    },
  },
);

try {
  await waitForServer(`${baseUrl}/api/health`);
  for (const scenario of scenarios) {
    await run(process.execPath, [resolve(root, 'tests/frontend', scenario)], {
      cwd: root,
      env: { ...process.env, LUMINOUS_FRONTEND_URL: baseUrl },
    });
  }
} finally {
  await stopServer(server);
  await rm(runtimeDir, { recursive: true, force: true });
}
