import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { PAGE_HEADING_ID } from '@/pages/PageHeading';

/** How long after a route change the hook keeps looking for the heading. */
const WATCH_MS = 10_000;
const RETRY_MS = 100;

/**
 * Moves focus to the page heading after a route change.
 *
 * A client-side navigation does not reset focus the way a page load does:
 * without this a keyboard or screen reader user stays on the link they
 * activated and hears nothing about the new page. The first render is left
 * alone so the browser's own start-of-page focus applies.
 *
 * The heading may come late, be replaced (a loading title gives way to the
 * real one) or not take focus yet (a title that is not drawn has no box), so
 * for a while the hook keeps looking. It only moves focus that is nowhere:
 * on the body, on the element the reader left, or on a heading it set itself.
 * A reader who went on, or a sheet that took focus, is left where they are.
 */
export function useRouteFocus(): void {
  const { pathname } = useLocation();
  const previous = useRef(pathname);

  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;

    const left = document.activeElement;
    let ours: HTMLElement | null = null;
    let done = false;
    const observer = new MutationObserver(() => attempt());
    // A hidden tab runs no animation frames and may batch mutations: poll too.
    const timer = setInterval(() => attempt(), RETRY_MS);
    const limit = setTimeout(() => stop(), WATCH_MS);
    observer.observe(document.body, { childList: true, subtree: true });

    function stop() {
      done = true;
      observer.disconnect();
      clearInterval(timer);
      clearTimeout(limit);
    }

    function attempt() {
      if (done) return;
      const active = document.activeElement;
      const nowhere = !active || active === document.body || active === left || active === ours;
      if (!nowhere) {
        stop();
        return;
      }
      const heading = document.getElementById(PAGE_HEADING_ID);
      if (!heading || heading === ours) return;
      heading.focus();
      if (document.activeElement === heading) ours = heading;
    }

    attempt();
    return stop;
  }, [pathname]);
}
