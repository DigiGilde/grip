import { useRef, type ReactNode } from 'react';
import { useRouterLinks } from './useRouterLinks';

/**
 * Hands plain clicks on in-app links inside it to the router, so they do not
 * reload the page. See useRouterLinks.
 */
export function RouterLinks({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  return <div ref={ref}>{children}</div>;
}
