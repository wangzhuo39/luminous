import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_SCENE_BACKGROUND,
  SCENE_BACKGROUND_STORAGE_KEY,
  loadSceneBackground,
  normalizeSceneBackground,
  saveSceneBackground,
} from '../../apps/companion-web/companion-ui/js/features/main-scene/scene-background.js';

function createStorage(initialValue = null) {
  const values = new Map();
  if (initialValue !== null) values.set(SCENE_BACKGROUND_STORAGE_KEY, initialValue);
  return {
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, value); },
    removeItem(key) { values.delete(key); },
  };
}

test('scene background accepts only known choices', () => {
  assert.equal(normalizeSceneBackground('crystal-sanctuary'), 'crystal-sanctuary');
  assert.equal(normalizeSceneBackground('unknown-background'), DEFAULT_SCENE_BACKGROUND);
});

test('scene background persists and reloads a valid choice', () => {
  const storage = createStorage();
  assert.equal(saveSceneBackground(storage, 'crystal-sanctuary'), true);
  assert.equal(loadSceneBackground(storage), 'crystal-sanctuary');
});

test('scene background clears an invalid stored choice', () => {
  const storage = createStorage('retired-background');
  assert.equal(loadSceneBackground(storage), DEFAULT_SCENE_BACKGROUND);
  assert.equal(storage.getItem(SCENE_BACKGROUND_STORAGE_KEY), null);
});

test('scene background tolerates unavailable storage', () => {
  const unavailableStorage = {
    getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
  };
  assert.equal(loadSceneBackground(unavailableStorage), DEFAULT_SCENE_BACKGROUND);
  assert.equal(saveSceneBackground(unavailableStorage, 'crystal-sanctuary'), false);
});
