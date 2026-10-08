import { useEffect } from 'react';

/** The id the layout focuses after a route change. */
export const PAGE_HEADING_ID = 'page-heading';

interface PageHeadingProps {
  text: string;
  /** Name of the instance, appended to the document title when known. */
  instanceName?: string;
  /** One sentence under the title that says what the page is for. */
  lead?: string;
  /**
   * Keep the heading in the normal flow. By default it goes into the header
   * slot of the nldd-simple-section it sits in, which gives it the design
   * system's own distance to the content. Use this when the parent is not a
   * simple section: a slotted element without that slot is not drawn at all.
   */
  inline?: boolean;
}

/**
 * The single h1 of a page. It also sets the document title, so the tab, the
 * history and a screen reader's page announcement all say the same thing.
 */
export function PageHeading({ text, instanceName, lead, inline }: PageHeadingProps) {
  useEffect(() => {
    document.title = [text, instanceName ?? 'Grip'].join(' - ');
  }, [text, instanceName]);

  return (
    <nldd-title
      size={2}
      {...(inline ? {} : { slot: 'header' })}
      {...(lead ? { 'supporting-text': lead } : {})}
    >
      {/* tabIndex -1: focusable from script after navigation, not a tab stop. */}
      <h1 id={PAGE_HEADING_ID} tabIndex={-1}>
        {text}
      </h1>
    </nldd-title>
  );
}
