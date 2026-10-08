import { useRef, type ReactNode } from 'react';
import { useRouterLinks } from './useRouterLinks';

interface RouterLinksProps {
  children: ReactNode;
  /**
   * The slot of the element this stands in, when the children belong in one
   * (a title block in the header of a section). A slot is only honoured on a
   * direct child, so the wrapper takes it over from what it wraps.
   */
  slot?: string;
}

/**
 * Hands plain clicks on in-app links inside it to the router, so they do not
 * reload the page. See useRouterLinks. The wrapper makes no box of its own
 * (`display: contents`): what it wraps is laid out as if it were not there.
 */
export function RouterLinks({ children, slot }: RouterLinksProps) {
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  return (
    <div ref={ref} style={{ display: 'contents' }} {...(slot ? { slot } : {})}>
      {children}
    </div>
  );
}
