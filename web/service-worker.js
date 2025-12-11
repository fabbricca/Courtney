/**
 * GLaDOS PWA Service Worker
 *
 * Handles caching of static assets for offline access
 */

const CACHE_NAME = 'glados-v1.0.0';
const urlsToCache = [
    '/',
    '/index.html',
    '/css/style.css',
    '/js/app.js',
    '/js/websocket.js',
    '/js/audio.js',
    '/manifest.json',
    '/icons/icon-192.png',
    '/icons/icon-512.png'
];

/**
 * Install event - cache static assets
 */
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing...');

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[Service Worker] Caching static assets');
                return cache.addAll(urlsToCache);
            })
            .then(() => {
                console.log('[Service Worker] Installed successfully');
                return self.skipWaiting();
            })
            .catch((error) => {
                console.error('[Service Worker] Installation failed:', error);
            })
    );
});

/**
 * Activate event - cleanup old caches
 */
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating...');

    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames.map((cacheName) => {
                        if (cacheName !== CACHE_NAME) {
                            console.log('[Service Worker] Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
            .then(() => {
                console.log('[Service Worker] Activated successfully');
                return self.clients.claim();
            })
    );
});

/**
 * Fetch event - serve from cache, fallback to network
 */
self.addEventListener('fetch', (event) => {
    // Skip WebSocket requests
    if (event.request.url.startsWith('ws://') || event.request.url.startsWith('wss://')) {
        return;
    }

    // Network-first strategy for API calls, cache-first for static assets
    const isStaticAsset = urlsToCache.some(url => event.request.url.endsWith(url));

    if (isStaticAsset) {
        // Cache-first strategy for static assets
        event.respondWith(
            caches.match(event.request)
                .then((response) => {
                    if (response) {
                        return response;
                    }

                    return fetch(event.request).then((response) => {
                        // Cache the new response if it's valid
                        if (response && response.status === 200) {
                            const responseToCache = response.clone();
                            caches.open(CACHE_NAME).then((cache) => {
                                cache.put(event.request, responseToCache);
                            });
                        }

                        return response;
                    });
                })
                .catch(() => {
                    // Return offline page if available
                    return caches.match('/index.html');
                })
        );
    } else {
        // Network-first strategy for everything else
        event.respondWith(
            fetch(event.request)
                .catch(() => {
                    return caches.match(event.request);
                })
        );
    }
});

/**
 * Message event - handle messages from clients
 */
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
