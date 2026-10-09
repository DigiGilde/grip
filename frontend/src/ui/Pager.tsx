/**
 * A long list in pages.
 *
 * The server sends one page and says how many rows there are in all. This
 * draws the two things a reader needs for that: above the list which rows
 * these are ("51 tot 100 van 300"), below it the way to the other pages.
 * A list of one page shows neither.
 *
 * The page is part of the address (`?pagina=2`), so a page can be shared and
 * the back button returns to the page you came from. The pages are links in
 * a navigation landmark with the current one marked; that is the design
 * system's pagination. After a change of page focus goes to the line that
 * says which rows are shown, so a keyboard or screen reader user starts at
 * the top of the new rows and hears where they are.
 *
 *     const paging = usePaging(total, pageSize);
 *     <PageRange paging={paging} noun="opdrachten" />
 *     ...the rows...
 *     <Pager paging={paging} label="Pagina's van de opdrachten" />
 */
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNlddEvent } from '@/components/nldd/events';

import type { Paging } from './paging';
import './pager.css';

if (import.meta.env.MODE !== 'test') void import('@nldd/design-system/pagination');

const NUMBER = new Intl.NumberFormat('nl-NL');
const formatNumber = (value: number) => NUMBER.format(value);

/** "51 tot en met 100 van 300 opdrachten"; nothing for a list of one page. */
export function PageRange({ paging, noun }: { paging: Paging; noun: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useRef(paging.page);
  // Another page: focus goes to the line above its rows.
  useEffect(() => {
    if (seen.current === paging.page) return;
    seen.current = paging.page;
    ref.current?.focus();
  }, [paging.page]);
  if (paging.pages <= 1) return null;
  return (
    <div ref={ref} tabIndex={-1} data-page-range>
      <nldd-text size="sm" color="secondary">
        {`${formatNumber(paging.from)} tot en met ${formatNumber(paging.to)} van ${formatNumber(paging.total)} ${noun}`}
      </nldd-text>
    </div>
  );
}

interface PagerProps {
  paging: Paging;
  /** The name of the navigation: "Pagina's van de opdrachten". */
  label: string;
}

export function Pager({ paging, label }: PagerProps) {
  const ref = useRef<HTMLElement>(null);
  const navigate = useNavigate();
  // The component follows the link itself unless told not to: hand the
  // change to the router, so the page does not reload.
  useNlddEvent(ref, 'page-change', (event) => {
    const page = (event as CustomEvent<{ page?: number }>).detail?.page;
    if (typeof page !== 'number') return;
    event.preventDefault();
    navigate(paging.hrefFor(page));
  });
  // An object cannot travel as an attribute: set the name as a property.
  useEffect(() => {
    const element = ref.current as (HTMLElement & { translations?: object }) | null;
    if (element) element.translations = { 'components.pagination.accessible-label': label };
  });
  if (paging.pages <= 1) return null;
  // `current` is a page number here, not the on/off mark it is elsewhere.
  const numbers = { current: paging.page, total: paging.pages };
  // `{page}` survives in the pattern as the component's own placeholder.
  const pattern = paging.hrefFor(987_654_321).replace('987654321', '{page}');
  return <nldd-pagination ref={ref} {...numbers} href-pattern={pattern} />;
}
