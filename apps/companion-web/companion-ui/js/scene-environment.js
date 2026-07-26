const TONES = new Set(['calm', 'warm', 'quiet', 'concerned', 'unknown']);
const SPACES = new Set(['today', 'memory', 'privacy', 'outbox']);
const PRESENCE_STATES = new Set(['none', 'active', 'paused']);

const CRYSTAL_SEEDS = Object.freeze([
  [11, 78, 0.68, -12, 0.18], [24, 62, 0.84, 8, 0.54], [38, 82, 0.58, -5, 0.31],
  [51, 68, 0.74, 14, 0.72], [66, 79, 0.62, -9, 0.44], [79, 59, 0.88, 5, 0.83],
  [89, 76, 0.55, -16, 0.26], [17, 47, 0.49, 12, 0.66], [33, 53, 0.57, -7, 0.39],
  [59, 49, 0.52, 9, 0.76], [73, 42, 0.46, -11, 0.22], [92, 51, 0.42, 6, 0.61],
]);

const TONE_ENVIRONMENT = Object.freeze({
  calm: { rayFocus: 0.56, mistDensity: 0.66, breathPeriod: 9.2 },
  warm: { rayFocus: 0.78, mistDensity: 0.54, breathPeriod: 7.8 },
  quiet: { rayFocus: 0.38, mistDensity: 0.8, breathPeriod: 12 },
  concerned: { rayFocus: 0.44, mistDensity: 0.72, breathPeriod: 10.8 },
  unknown: { rayFocus: 0.5, mistDensity: 0.68, breathPeriod: 10 },
});

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

function safeCount(value) {
  return Number.isFinite(value) ? clamp(Math.floor(value), 0, 9999) : 0;
}

export function deriveSolarState(value = new Date()) {
  const date = value instanceof Date && Number.isFinite(value.getTime()) ? value : null;
  const minutes = date ? date.getHours() * 60 + date.getMinutes() : 0;
  const phase = minutes >= 300 && minutes < 540
    ? 'dawn'
    : minutes >= 540 && minutes < 1020
      ? 'day'
      : minutes >= 1020 && minutes < 1200 ? 'dusk' : 'night';
  const solarPhase = Number((minutes / 1440).toFixed(4));
  const lightAngle = Number(clamp((minutes - 720) / 6, -60, 60).toFixed(2));
  return Object.freeze({ phase, solarPhase, lightAngle });
}

export function crystalCountForMemoryCount(value) {
  const count = safeCount(value);
  if (count === 0) return 0;
  if (count <= 3) return count + 1;
  if (count <= 8) return Math.min(7, count + 1);
  return 12;
}

export function deriveEnvironment(input = {}, now = new Date()) {
  const solar = deriveSolarState(now);
  const tone = TONES.has(input.tone) ? input.tone : 'unknown';
  const activityPresence = PRESENCE_STATES.has(input.activityPresence)
    ? input.activityPresence
    : 'none';
  const activeSpace = SPACES.has(input.activeSpace) ? input.activeSpace : 'none';
  const memoryCount = safeCount(input.memoryCount);
  const crystalCount = crystalCountForMemoryCount(memoryCount);
  const base = TONE_ENVIRONMENT[tone];

  return Object.freeze({
    ...solar,
    tone,
    activityPresence,
    activeSpace,
    rayFocus: Number(clamp(base.rayFocus + (activityPresence === 'active' ? 0.08 : 0), 0, 1).toFixed(2)),
    mistDensity: Number(clamp(base.mistDensity + (activityPresence === 'paused' ? 0.1 : 0), 0, 1).toFixed(2)),
    breathPeriod: Number((base.breathPeriod + (activityPresence === 'paused' ? 2 : 0)).toFixed(1)),
    crystalCount,
    crystalBucket: crystalCount === 0 ? 'empty' : crystalCount < 5 ? 'few' : crystalCount < 12 ? 'some' : 'many',
    presenceLift: activityPresence === 'active' ? 1 : activityPresence === 'paused' ? 0.28 : 0,
    letterWarmth: input.outboxUnread === true ? 1 : 0,
    privacyStillness: input.dnd === true ? 1 : 0,
  });
}

export function applyEnvironment(scene, environment) {
  if (!scene || !environment) return;
  scene.dataset.solarPhase = environment.phase;
  scene.dataset.crystalDensity = environment.crystalBucket;
  scene.dataset.environmentTone = environment.tone;
  scene.dataset.environmentSpace = environment.activeSpace;
  scene.style.setProperty('--solar-phase', String(environment.solarPhase));
  scene.style.setProperty('--light-angle', `${environment.lightAngle}deg`);
  scene.style.setProperty('--ray-focus', String(environment.rayFocus));
  scene.style.setProperty('--mist-density', String(environment.mistDensity));
  scene.style.setProperty('--breath-period', `${environment.breathPeriod}s`);
  scene.style.setProperty('--presence-lift', String(environment.presenceLift));
  scene.style.setProperty('--letter-warmth', String(environment.letterWarmth));
  scene.style.setProperty('--privacy-stillness', String(environment.privacyStillness));
}

export function renderMemoryCrystals(container, count) {
  if (!container?.ownerDocument) return;
  const safeCrystalCount = clamp(safeCount(count), 0, CRYSTAL_SEEDS.length);
  const fragment = container.ownerDocument.createDocumentFragment();
  CRYSTAL_SEEDS.slice(0, safeCrystalCount).forEach((seed, index) => {
    const node = container.ownerDocument.createElement('i');
    node.className = 'memory-crystal-node';
    node.setAttribute('aria-hidden', 'true');
    node.style.setProperty('--seed-x', `${seed[0]}%`);
    node.style.setProperty('--seed-y', `${seed[1]}%`);
    node.style.setProperty('--seed-scale', String(seed[2]));
    node.style.setProperty('--seed-rotate', `${seed[3]}deg`);
    node.style.setProperty('--seed-delay', `${seed[4] * -8}s`);
    node.style.setProperty('--seed-index', String(index));
    fragment.appendChild(node);
  });
  container.replaceChildren(fragment);
}

export function initSceneEnvironment({
  scene,
  crystalField,
  now = () => new Date(),
  setTimer = window.setInterval.bind(window),
  clearTimer = window.clearInterval.bind(window),
} = {}) {
  let lastInput = {};
  let lastCrystalCount = -1;

  const update = (input = lastInput) => {
    lastInput = { ...input };
    const environment = deriveEnvironment(lastInput, now());
    applyEnvironment(scene, environment);
    if (environment.crystalCount !== lastCrystalCount) {
      renderMemoryCrystals(crystalField, environment.crystalCount);
      lastCrystalCount = environment.crystalCount;
    }
    return environment;
  };

  const timerId = setTimer(() => update(), 60_000);
  return {
    update,
    destroy() {
      clearTimer(timerId);
      crystalField?.replaceChildren();
    },
  };
}
