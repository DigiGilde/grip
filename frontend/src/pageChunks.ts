/**
 * Pages that are loaded when someone goes there, and which file of the
 * build belongs to which address.
 *
 * The first load carries the shell, the start page and the tasks. Every
 * other page is a file of its own, fetched on the way to it.
 *
 * A deployment replaces those files. A tab that was opened before it still
 * asks for the old names and gets a 404. That is not an error to show: the
 * page reloads once, which brings the new index and the new names. Only when
 * the file is still missing after that does the reader see that loading
 * failed.
 *
 * `page` makes a page that is loaded on demand and remembers the addresses
 * it serves. `preloadFor` fetches the files of an address ahead of the
 * click: the shell calls it when a link gets the pointer or the focus, and
 * the route table for the address it is about to render, so a layout and the
 * page inside it are fetched side by side and not one after the other.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import { matchPath } from 'react-router-dom';

/** When this tab last reloaded for a missing file, so it does so once. */
const RELOADED_KEY = 'grip.chunk-reload';
/** A second failure within this time is shown instead of reloaded. */
const RELOAD_ONCE_MS = 30_000;

function reloadedJustNow(): boolean {
  try {
    const at = Number(sessionStorage.getItem(RELOADED_KEY));
    return Number.isFinite(at) && at > 0 && Date.now() - at < RELOAD_ONCE_MS;
  } catch {
    // No storage: say it reloaded, so a missing file can never loop.
    return true;
  }
}

/**
 * Reload the page for a file of the build that is gone. Returns false when
 * this tab did so a moment ago: then reloading does not help.
 */
export function reloadForNewBuild(reload: () => void = () => window.location.reload()): boolean {
  if (reloadedJustNow()) return false;
  try {
    sessionStorage.setItem(RELOADED_KEY, String(Date.now()));
  } catch {
    return false;
  }
  reload();
  return true;
}

/** Load a file of the build; reload once when it is no longer there. */
export function loadChunk<T>(load: () => Promise<T>): Promise<T> {
  return load().catch((error: unknown) => {
    // The reload is on its way: keep waiting instead of showing a failure.
    if (reloadForNewBuild()) return new Promise<T>(() => {});
    throw error;
  });
}

/** The component a module exports under a name. */
export type PageOf<M, K extends keyof M> =
  M[K] extends ComponentType<infer P> ? ComponentType<P> : never;

/**
 * A page from a module, loaded on demand. Named exports stay named: the
 * second argument says which one is the page.
 */
export function lazyPage<M, K extends keyof M>(
  load: () => Promise<M>,
  name: K,
): LazyExoticComponent<PageOf<M, K>> {
  return lazy(() => loadChunk(load).then((module) => ({ default: module[name] as PageOf<M, K> })));
}

type Loader = () => Promise<unknown>;

const CHUNKS: Array<{ pattern: string; load: Loader }> = [];

export function page<M, K extends keyof M>(
  load: () => Promise<M>,
  name: K,
  ...patterns: string[]
): LazyExoticComponent<PageOf<M, K>> {
  for (const pattern of patterns) CHUNKS.push({ pattern, load });
  return lazyPage(load, name);
}

/** Start fetching what the page at this address needs. Asking twice costs nothing. */
export function preloadFor(href: string): void {
  const pathname = href.split(/[?#]/, 1)[0] ?? href;
  for (const { pattern, load } of CHUNKS) {
    if (matchPath({ path: pattern, end: true }, pathname)) {
      // A file that is gone is dealt with when the page itself asks for it.
      void load().catch(() => undefined);
    }
  }
}
