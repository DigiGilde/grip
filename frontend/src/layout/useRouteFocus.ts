import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { PAGE_HEADING_ID } from '@/pages/PageHeading';

/**
 * Moves focus to the page heading after a route change.
 *
 * A client-side navigation does not reset focus the way a page load does:
 * without this a keyboard or screen reader user stays on the link they
 * activated and hears nothing about the new page. The first render is left
 * alone so the browser's own start-of-page focus applies.
 */
export function useRouteFocus(): void {
  const { pathname } = useLocation();
  const previous = useRef(pathname);

  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;
    document.getElementById(PAGE_HEADING_ID)?.focus();
  }, [pathname]);
}
