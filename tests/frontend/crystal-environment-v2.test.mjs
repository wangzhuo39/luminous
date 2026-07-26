import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyEnvironment,
  crystalCountForMemoryCount,
  deriveEnvironment,
  deriveSolarState,
  initSceneEnvironment,
  renderMemoryCrystals,
} from '../../apps/companion-web/companion-ui/js/scene-environment.js';

function localTime(hour, minute = 0) {
  return new Date(2026, 6, 26, hour, minute, 0, 0);
}

function fakeStyle() {
  const values = new Map();
  return {
    values,
    setProperty(key, value) { values.set(key, value); },
  };
}

function fakeCrystalField() {
  const ownerDocument = {
    createDocumentFragment() {
      return { children: [], appendChild(node) { this.children.push(node); } };
    },
    createElement() {
      return {
        className: '',
        attributes: new Map(),
        style: fakeStyle(),
        setAttribute(key, value) { this.attributes.set(key, value); },
      };
    },
  };
  return {
    ownerDocument,
    children: [],
    replaceChildren(fragment) { this.children = fragment?.children ?? []; },
  };
}

test('solar phases follow local-time boundaries', () => {
  assert.equal(deriveSolarState(localTime(4, 59)).phase, 'night');
  assert.equal(deriveSolarState(localTime(5)).phase, 'dawn');
  assert.equal(deriveSolarState(localTime(9)).phase, 'day');
  assert.equal(deriveSolarState(localTime(17)).phase, 'dusk');
  assert.equal(deriveSolarState(localTime(20)).phase, 'night');
  assert.equal(deriveSolarState(new Date('invalid')).phase, 'night');
});

test('environment derives bounded visual values from safe aggregate state', () => {
  const environment = deriveEnvironment({
    tone: 'warm',
    activityPresence: 'active',
    memoryCount: 9,
    outboxUnread: true,
    dnd: true,
    activeSpace: 'memory',
  }, localTime(7, 20));
  assert.equal(environment.phase, 'dawn');
  assert.equal(environment.tone, 'warm');
  assert.equal(environment.activityPresence, 'active');
  assert.equal(environment.activeSpace, 'memory');
  assert.equal(environment.crystalCount, 12);
  assert.equal(environment.crystalBucket, 'many');
  assert.equal(environment.letterWarmth, 1);
  assert.equal(environment.privacyStillness, 1);
  assert.ok(environment.rayFocus >= 0 && environment.rayFocus <= 1);
  assert.ok(environment.mistDensity >= 0 && environment.mistDensity <= 1);
});

test('unknown or hostile values collapse to inert defaults', () => {
  const environment = deriveEnvironment({
    tone: '<img src=x onerror=alert(1)>',
    activityPresence: 'running',
    memoryCount: Number.POSITIVE_INFINITY,
    activeSpace: '__proto__',
    outboxUnread: 'yes',
  }, localTime(12));
  assert.equal(environment.tone, 'unknown');
  assert.equal(environment.activityPresence, 'none');
  assert.equal(environment.activeSpace, 'none');
  assert.equal(environment.crystalCount, 0);
  assert.equal(environment.letterWarmth, 0);
});

test('memory count maps to a deliberately bounded anonymous crystal field', () => {
  assert.deepEqual(
    [0, 1, 3, 4, 8, 9, 100].map(crystalCountForMemoryCount),
    [0, 2, 4, 5, 7, 12, 12],
  );
  const field = fakeCrystalField();
  renderMemoryCrystals(field, 100);
  assert.equal(field.children.length, 12);
  assert.ok(field.children.every((node) => node.className === 'memory-crystal-node'));
  assert.ok(field.children.every((node) => node.attributes.get('aria-hidden') === 'true'));
  assert.ok(field.children.every((node) => node.textContent === undefined));
});

test('scene environment updates CSS variables and clears its minute timer', () => {
  const scene = { dataset: {}, style: fakeStyle() };
  const field = fakeCrystalField();
  let callback = null;
  let cleared = null;
  const controller = initSceneEnvironment({
    scene,
    crystalField: field,
    now: () => localTime(18, 30),
    setTimer(next) { callback = next; return 42; },
    clearTimer(id) { cleared = id; },
  });
  const environment = controller.update({ tone: 'quiet', memoryCount: 4 });
  assert.equal(environment.phase, 'dusk');
  assert.equal(scene.dataset.solarPhase, 'dusk');
  assert.equal(scene.style.values.get('--breath-period'), '12s');
  assert.equal(field.children.length, 5);
  assert.equal(typeof callback, 'function');
  callback();
  controller.destroy();
  assert.equal(cleared, 42);
  assert.equal(field.children.length, 0);
});

test('applyEnvironment is a no-op for absent scene nodes', () => {
  assert.doesNotThrow(() => applyEnvironment(null, deriveEnvironment({}, localTime(12))));
});
