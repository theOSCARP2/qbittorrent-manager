const CACHE_NAME = 'qbm-v1.24.0';

const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

// Installation : mise en cache des assets statiques
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activation : suppression des anciens caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch : network-first pour les appels API, cache-first pour les assets statiques
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Toujours réseau pour les appels API et pages dynamiques
  if (url.pathname.startsWith('/api/') || event.request.method !== 'GET') {
    return;
  }

  // Cache-first pour les assets statiques
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
    return;
  }

  // Network-first pour les pages HTML
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
