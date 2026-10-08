import { useEffect } from 'react';

/** The id the layout focuses after a route change. */
export const PAGE_HEADING_ID = 'page-heading';

interface PageHeadingProps {
  text: string;
  /** Name of the instance, appended to the document title when known. */
  instanceName?: string;
}

/**
 * The single h1 of a page. It also sets the document title, so the tab, the
 * history and a screen reader's page announcement all say the same thing.
 */
export function PageHeading({ text, instanceName }: PageHeadingProps) {
  useEffect(() => {
    document.title = [text, instanceName ?? 'Grip'].join(' - ');
  }, [text, instanceName]);

  return (
    <nldd-title size={2}>
      {/* tabIndex -1: focusable from script after navigation, not a tab stop. */}
      <h1 id={PAGE_HEADING_ID} tabIndex={-1}>
        {text}
      </h1>
    </nldd-title>
  );
}
