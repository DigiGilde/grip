/*
 * The service worker of grip.
 *
 * It keeps the shell of the application (the page and its scripts, styles and
 * fonts) so the application opens fast and can say plainly that it is
 * offline. It never keeps an answer of the API: what grip shows is decided
 * per person and per field on the server, and an answer kept on a shared
 * device would be shown to whoever uses it next.
 *
 * Three rules, in this order:
 *   1. Anything under /api/ is not touched at all: the browser fetches it.
 *   2. A page (a navigation) comes from the network. Only when the network
 *      fails does the kept shell answer, and the application then says it
 *      has no connection.
 *   3. Static files of the build are kept: the hashed ones under /assets/
 *      for good, the few others refreshed in the background.
 *
 * Logging out empties everything kept here (the page posts "clear").
 *
 * Notifications. A push carries no sentence and no name: a kind from the
 * fixed list below, a number, and a path of ids to open. The words shown on
 * the device are chosen here, so nothing a stranger may not read can ever
 * appear on a locked screen. The worker fetches nothing to show one.
 */

const STATIC = 'grip-static-v1';
const SHELL_URL = '/index.html';

const OFFLINE_PAGE =
  '<!doctype html><html lang="nl"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1">' +
  '<title>Grip: geen verbinding</title>' +
  '<style>body{font-family:system-ui,sans-serif;margin:0;min-height:100vh;display:grid;' +
  'place-items:center;background:#f4f6f8;color:#1c2b3a}main{max-width:28rem;padding:1.5rem}' +
  '@media(prefers-color-scheme:dark){body{background:#1f232b;color:#e6e9ee}}</style></head>' +
  '<body><main><h1>Geen verbinding</h1><p>Grip heeft een internetverbinding nodig. ' +
  'Controleer je verbinding en laad de pagina opnieuw.</p></main></body></html>';

self.addEventListener('install', (event) => {
  // A new worker takes over at the next load instead of waiting for every
  // tab to close, so a deploy reaches people who leave a tab open.
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.filter((name) => name !== STATIC).map((name) => caches.delete(name)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('message', (event) => {
  // The page says how many tasks are the person's to do: the number on the
  // application's icon, and no task notice left when nothing waits.
  if (event.data && event.data.type === 'tasks') {
    const count = event.data.count;
    event.waitUntil(
      (async () => {
        await setBadge(count);
        if (count === 0) {
          for (const tag of TASK_KINDS) {
            const shown = await self.registration.getNotifications({ tag });
            for (const one of shown) one.close();
          }
        }
      })(),
    );
    return;
  }
  if (event.data === 'clear') {
    event.waitUntil(
      (async () => {
        const names = await caches.keys();
        await Promise.all(names.map((name) => caches.delete(name)));
        // Nothing of the session stays on the device: no number, no notice.
        await setBadge(0);
        if (self.registration.getNotifications) {
          for (const shown of await self.registration.getNotifications()) shown.close();
        }
        event.ports[0]?.postMessage('cleared');
      })(),
    );
  }
});

// What a notice says, per kind and number. Nothing else is ever shown.
const WORDS = {
  tasks: (n) => (n === 1 ? 'Er wacht een taak op je' : `${n} taken wachten op je`),
  overdue: (n) => (n === 1 ? 'Een taak is over de datum' : `${n} taken zijn over de datum`),
  quote_accepted: () => 'Een offerte is getekend',
  quote_rejected: () => 'Een offerte is afgewezen',
  approval_given: () => 'Een offerte is intern goedgekeurd',
  approval_sent_back: () => 'Een offerte is teruggestuurd naar jou',
  test: () => 'Meldingen van grip werken',
};
// Notices about tasks: closed when the page says nothing waits any more.
const TASK_KINDS = ['tasks', 'overdue'];

/** A path inside the application, or the start. Never an address elsewhere. */
function safePath(path) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) return '/';
  if (path.includes('\\') || path === '/api' || path.startsWith('/api/')) return '/';
  return path;
}

function setBadge(count) {
  if (typeof count !== 'number' || !('setAppBadge' in self.navigator)) return Promise.resolve();
  const done = count > 0 ? self.navigator.setAppBadge(count) : self.navigator.clearAppBadge();
  return done.catch(() => undefined);
}

function notice(data) {
  const words = WORDS[data && data.k];
  if (!words) return null;
  const count = Number.isInteger(data.n) && data.n > 0 ? data.n : 1;
  return {
    title: words(count),
    options: {
      body: 'Open grip om verder te gaan.',
      // One notice per kind on the device: a newer one replaces the older.
      tag: data.k,
      renotify: true,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-mono-512.png',
      lang: 'nl',
      data: { path: safePath(data.p) },
    },
  };
}

self.addEventListener('push', (event) => {
  let data = null;
  try {
    data = event.data ? event.data.json() : null;
  } catch {
    data = null;
  }
  const shown = notice(data);
  // A push must show something; one that cannot be read says only that.
  const title = shown ? shown.title : 'Er is iets nieuws in grip';
  const options = shown
    ? shown.options
    : { body: 'Open grip om verder te gaan.', tag: 'grip', data: { path: '/' } };
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(title, options),
      setBadge(data && data.b),
    ]),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const path = safePath(event.notification.data && event.notification.data.path);
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      const open = windows.find((client) => new URL(client.url).origin === self.location.origin);
      if (open) {
        // Either may be refused by the browser; then a new window still opens.
        const focused = await open.focus().then(
          () => true,
          () => false,
        );
        const moved =
          'navigate' in open &&
          (await open.navigate(path).then(
            () => true,
            () => false,
          ));
        if (focused || moved) return;
      }
      await self.clients.openWindow(path);
    })(),
  );
});

// The browser replaced the subscription. The page registers the new one the
// next time it opens; an open page is told now.
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window' });
      for (const client of windows) client.postMessage('subscription-changed');
    })(),
  );
});

function isStatic(url) {
  return (
    url.pathname.startsWith('/assets/') ||
    /\.(?:js|css|woff2|svg|png|ico|webmanifest)$/.test(url.pathname)
  );
}

async function page(request) {
  try {
    const response = await fetch(request);
    const type = response.headers.get('content-type') || '';
    // The shell is the same document for every path of the application and
    // holds no data. Keep the latest good copy for when the network is gone.
    if (response.ok && type.includes('text/html')) {
      const cache = await caches.open(STATIC);
      await cache.put(SHELL_URL, response.clone());
    }
    return response;
  } catch {
    const kept = await caches.match(SHELL_URL);
    return (
      kept ||
      new Response(OFFLINE_PAGE, {
        status: 503,
        headers: { 'content-type': 'text/html; charset=utf-8' },
      })
    );
  }
}

// How many files are kept at most. One build is under two hundred; the
// oldest go first, so files of earlier builds leave on their own.
const KEPT_FILES = 400;

async function trim(cache) {
  const keys = await cache.keys();
  // Keys come back in the order they were kept.
  for (const key of keys.slice(0, Math.max(0, keys.length - KEPT_FILES))) {
    if (new URL(key.url).pathname !== SHELL_URL) await cache.delete(key);
  }
}

/** A file of the build, and not a page that was served in its place. */
function isFile(response) {
  const type = response.headers.get('content-type') || '';
  return response.ok && !type.includes('text/html');
}

async function staticFile(request, url) {
  const cache = await caches.open(STATIC);
  const kept = await cache.match(request);
  const fresh = fetch(request).then((response) => {
    // Never keep an error or a page under the name of a file: a hashed file
    // is kept for good, so a wrong answer would stay wrong. A file that is
    // gone after a deployment answers 404 here; the page then reloads once.
    if (isFile(response)) void cache.put(request, response.clone()).then(() => trim(cache));
    return response;
  });
  // A hashed file never changes: the kept copy is the file.
  if (kept && url.pathname.startsWith('/assets/')) return kept;
  if (kept) {
    fresh.catch(() => undefined);
    return kept;
  }
  return fresh;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Rule 1: the API is never answered or kept by this worker.
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return;
  if (request.mode === 'navigate') {
    event.respondWith(page(request));
    return;
  }
  if (isStatic(url)) event.respondWith(staticFile(request, url));
});
