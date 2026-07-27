import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const root = new URL('../../apps/companion-web/companion-ui/', import.meta.url);

async function lineCount(relativePath) {
  const content = await readFile(new URL(relativePath, root), 'utf8');
  return content.split('\n').length;
}

test('companion UI entrypoints stay within architecture guardrails', async () => {
  const budgets = {
    'index.html': 620,
    'js/main.js': 520,
    'js/app-state.js': 80,
    'js/dom-registry.js': 260,
    'js/state/life-flow-state.js': 760,
  };
  for (const [file, budget] of Object.entries(budgets)) {
    const lines = await lineCount(file);
    assert.ok(lines <= budget, `${file} is ${lines} lines; budget is ${budget}`);
  }
});

test('state facade has no DOM or view-template responsibilities', async () => {
  const facade = await readFile(new URL('js/app-state.js', root), 'utf8');
  assert.doesNotMatch(facade, /document\.|window\.|querySelector|innerHTML|createElement/);
  assert.match(facade, /from ['"]\.\/state\//);
});

test('main scene styles are split by surface', async () => {
  const surfaces = [
    'base.css', 'header.css', 'portals.css', 'dialogue.css',
    'status.css', 'composer.css', 'responsive.css', 'motion.css',
  ];
  for (const surface of surfaces) {
    const lines = await lineCount(`styles/features/main-scene/${surface}`);
    assert.ok(lines <= 300, `${surface} is ${lines} lines; split the surface further`);
  }
});
