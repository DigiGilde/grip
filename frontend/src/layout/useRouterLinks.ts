import { useCallback, type RefObject } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNlddEvent } from '@/components/nldd/events';

/** True when the click asked for something other than plain navigation. */
function isModifiedClick(event: MouseEvent): boolean {
  return event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0;
}

/** The in-app path an event target links to, or null. */
export function internalHref(event: Event): string | null {
  for (const target of event.composedPath()) {
    if (!(target instanceof Element)) continue;
    const href = target.getAttribute('href');
    if (href === null) continue;
    // Only application routes: /api/* must stay a full navigation.
    return href.startsWith('/') && !href.startsWith('//') && !href.startsWith('/api/')
      ? href
      : null;
  }
  return null;
}

/**
 * Hands clicks on links inside a container to the router.
 *
 * The design system renders real `<a href>` elements, so middle-click and
 * cmd-click keep working and the address is shareable. A plain click would do
 * a full page load, which this intercepts.
 */
export function useRouterLinks(ref: RefObject<HTMLElement | null>): void {
  const navigate = useNavigate();
  const onClick = useCallback(
    (event: Event) => {
      if (event.defaultPrevented || isModifiedClick(event as MouseEvent)) return;
      const href = internalHref(event);
      if (href === null) return;
      event.preventDefault();
      navigate(href);
    },
    [navigate],
  );
  useNlddEvent(ref, 'click', onClick);
}
