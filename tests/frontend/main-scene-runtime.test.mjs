import assert from 'node:assert/strict';
import test from 'node:test';

import { createMainSceneView } from '../../apps/companion-web/companion-ui/js/features/main-scene/main-scene-view.js';

function textNode() {
  return { textContent: '' };
}

test('main scene renders every dynamic companion status field', () => {
  const nodes = {
    heartLabel: textNode(),
    heartDetail: textNode(),
    activityLabel: textNode(),
    activityDetail: textNode(),
    moodLabel: textNode(),
    moodDetail: textNode(),
  };
  const selectorKeys = {
    'companion-heart-label': 'heartLabel',
    'companion-heart-detail': 'heartDetail',
    'companion-activity-label': 'activityLabel',
    'companion-activity-detail': 'activityDetail',
    'companion-mood-label': 'moodLabel',
    'companion-mood-detail': 'moodDetail',
  };
  const scene = {
    querySelector(selector) {
      const entry = Object.entries(selectorKeys).find(([hook]) => selector.includes(hook));
      return entry ? nodes[entry[1]] : null;
    },
  };
  const body = { dataset: {} };
  const figure = { label: '', setAttribute(_key, value) { this.label = value; } };
  const view = createMainSceneView({ body, scene, companionFigure: figure });

  view.renderScene({
    caption: '正专注地听着。',
    tone: 'warm',
    status: {
      heartLabel: '心跳轻快', heartDetail: '76 次/分',
      activityLabel: '正专心陪你', activityDetail: '刚刚 · 还在听你说',
      moodLabel: '有些温柔', moodDetail: '心里暖着',
    },
  });

  assert.equal(figure.label, '正专注地听着。');
  assert.equal(body.dataset.tone, 'warm');
  assert.deepEqual(Object.fromEntries(Object.entries(nodes).map(([key, node]) => [key, node.textContent])), {
    heartLabel: '心跳轻快', heartDetail: '76 次/分',
    activityLabel: '正专心陪你', activityDetail: '刚刚 · 还在听你说',
    moodLabel: '有些温柔', moodDetail: '心里暖着',
  });
});
