const CACHE_NAME = 'luminous-shell-v3';
const SHELL_ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './companion.png',
  './assets/luminous-icon.svg',
  './assets/luminous-icon-192.png',
  './assets/luminous-icon-512.png',
  './styles/tokens.css',
  './styles/base.css',
  './styles/scene.css',
  './styles/overlays.css',
  './styles/responsive.css',
  './styles/motion.css',
  './styles/network-states.css',
  './styles/life-flow.css',
  './styles/crystal-solarium.css',
  './styles/silent-spaces.css',
  './styles/productization.css',
  './js/main.js',
  './js/app-state.js',
  './js/conversation.js',
  './js/core-runtime.js',
  './js/fixture-adapter.js',
  './js/fixtures.js',
  './js/life-flow-datasource.js',
  './js/overlays.js',
  './js/presentation.js',
  './js/scene-environment.js',
  './js/scene-parallax.js',
  './js/view-models.js',
  './js/adapters/api-adapter.js',
  './js/adapters/life-flow-adapter.js',
  './js/adapters/life-flow-fixture-adapter.js',
  './js/adapters/scheduling-action-adapter.js',
  './js/adapters/silent-spaces-adapter.js',
  './js/services/api-client.js',
  './js/services/life-flow-api.js',
  './js/services/silent-spaces-api.js',
  './js/shared/errors.js',
  './js/shared/operation.js',
  './js/shared/time.js',
  './js/shared/validation.js',
  './js/features/action-proposal/action-controller.js',
  './js/features/action-proposal/action-state.js',
  './js/features/action-proposal/action-view.js',
  './js/features/life-flow/activity-view.js',
  './js/features/life-flow/calendar-view.js',
  './js/features/life-flow/diary-view.js',
  './js/features/life-flow/life-flow-controller.js',
  './js/features/life-flow/life-flow-state.js',
  './js/features/life-flow/reminder-view.js',
  './js/features/life-flow/routine-view.js',
  './js/features/life-flow/task-view.js',
  './js/features/life-flow/today-view.js',
  './js/features/silent-spaces/silent-spaces-controller.js',
  './js/features/silent-spaces/silent-spaces-fixture.js',
  './js/features/silent-spaces/silent-spaces-view.js',
  './js/features/productization/draft-recovery.js',
  './js/features/productization/pwa-controller.js',
  './js/features/productization/space-router.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('./index.html')),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
      }
      return response;
    })),
  );
});
