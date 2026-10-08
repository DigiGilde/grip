/**
 * The service worker: registering it, and emptying what it keeps.
 *
 * The worker (public/sw.js) keeps the shell of the application and never an
 * answer of the API. It runs in a built application only: in development the
 * dev server serves modules that must not be kept.
 */

const WORKER_URL = '/sw.js';
const HOUR = 60 * 60 * 1000;

export function registerServiceWorker(): void {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(WORKER_URL, { scope: '/' })
      .then((registration) => {
        // A tab that stays open for days still learns of a new worker.
        window.setInterval(() => void registration.update().catch(() => undefined), HOUR);
      })
      .catch(() => undefined);
  });
}

/**
 * Empty everything the worker and this origin keep in caches. Called before
 * logging out, so nothing of this session's shell stays on a shared device.
 * Resolves also when there is no worker or the browser has no caches.
 */
export async function clearKeptFiles(): Promise<void> {
  try {
    if ('caches' in window) {
      const names = await caches.keys();
      await Promise.all(names.map((name) => caches.delete(name)));
    }
    // The worker also drops the number on the icon and any notice shown.
    if ('serviceWorker' in navigator) {
      const registration = await navigator.serviceWorker.getRegistration();
      registration?.active?.postMessage('clear');
    }
  } catch {
    // Nothing kept, or not allowed to look: there is nothing to empty.
  }
}
