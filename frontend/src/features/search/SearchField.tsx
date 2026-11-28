import { useRef } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useNlddEvent } from '@/components/nldd/events';
import { PATHS } from '@/paths';
import { cleanQuery, MAX_QUERY } from './api';

/** The one search field for names. Enter opens the search page with what was typed. */
export function SearchField() {
  const ref = useRef<HTMLElement>(null);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const shown = pathname === PATHS.search ? cleanQuery(params.get('q')) : '';

  useNlddEvent(ref, 'search', (event) => {
    const detail = (event as CustomEvent<{ value?: unknown }>).detail;
    const q = cleanQuery(typeof detail?.value === 'string' ? detail.value : '');
    if (q === '') return;
    navigate({ pathname: PATHS.search, search: new URLSearchParams({ q }).toString() });
  });

  return (
    <nldd-search-field
      ref={ref}
      value={shown}
      placeholder="Zoek op naam"
      accessible-label="Zoek op naam"
      maxlength={MAX_QUERY}
    />
  );
}
