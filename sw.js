/*
 * sw.js — service worker: offline provoz aplikace.
 *
 * - install: předem uloží všechny soubory aplikace do cache.
 * - fetch: „stale-while-revalidate“. Soubor se vrátí okamžitě z cache (funguje
 *   offline) a na pozadí se stáhne nová verze, která se použije při DALŠÍM
 *   spuštění. Nasazení nové verze tedy nevyžaduje ruční zvyšování VERSION;
 *   VERSION stačí změnit, když se soubory odstraňují nebo přejmenovávají
 *   (starý cache se pak při aktivaci smaže).
 * - Všechny cesty jsou relativní, aby aplikace fungovala i v podadresáři
 *   (GitHub Pages: https://uzivatel.github.io/repozitar/).
 */
const VERSION = 'v1';
const CACHE = 'sudoku-' + VERSION;

const ASSETS = [
  './',
  'index.html',
  'style.css',
  'app.js',
  'sudoku.js',
  'manifest.webmanifest',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/icon-maskable-512.png',
  'icons/apple-touch-icon.png',
  'icons/favicon-32.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      // cache: 'reload' obejde HTTP cache, ať se uloží opravdu aktuální soubory
      .then((cache) => cache.addAll(ASSETS.map((a) => new Request(a, { cache: 'reload' }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k.startsWith('sudoku-') && k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(handle(event, req, url));
});

async function handle(event, req, url) {
  const cache = await caches.open(CACHE);

  let cached = await cache.match(req, { ignoreSearch: true });
  if (!cached && req.mode === 'navigate') cached = await cache.match('index.html');

  const refresh = fetch(req, { cache: 'no-cache' }).then((res) => {
    if (res.ok && res.type === 'basic' && url.search === '') {
      return cache.put(req, res.clone()).then(() => res);
    }
    return res;
  });

  if (cached) {
    // aktualizace na pozadí; service worker nesmí skončit dřív, než doběhne
    event.waitUntil(refresh.catch(() => {}));
    return cached;
  }

  try {
    return await refresh;
  } catch (e) {
    return Response.error(); // offline a soubor není v cache
  }
}
