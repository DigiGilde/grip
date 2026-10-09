/**
 * Where a reader is in a list that comes in pages: the page of the address,
 * the rows it holds and the addresses of the other pages. See `Pager`.
 */
import { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';

export const PAGE_PARAM = 'pagina';

/** The page the address asks for; the first for anything else. */
export function pageOf(params: URLSearchParams): number {
  const value = params.get(PAGE_PARAM);
  return value !== null && /^[1-9]\d{0,5}$/.test(value) ? Number(value) : 1;
}

export interface Paging {
  page: number;
  pages: number;
  total: number;
  /** The first and the last row of this page, counted from one. */
  from: number;
  to: number;
  /** The address of another page of the same list. */
  hrefFor: (page: number) => string;
}

/**
 * Where the reader is in a list of `total` rows. `total` is undefined while
 * the first answer is on its way; the page of the address then stands.
 */
export function usePaging(total: number | undefined, pageSize: number): Paging {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const asked = pageOf(params);
  const pages = total === undefined ? asked : Math.max(1, Math.ceil(total / pageSize));
  // A page past the end (a row was removed, a filter narrowed): the last one.
  const page = Math.min(asked, pages);
  const hrefFor = (target: number) => {
    const next = new URLSearchParams(params);
    if (target <= 1) next.delete(PAGE_PARAM);
    else next.set(PAGE_PARAM, String(target));
    const query = next.toString();
    return query ? `${pathname}?${query}` : pathname;
  };
  const count = total ?? 0;
  return {
    page,
    pages,
    total: count,
    from: count === 0 ? 0 : (page - 1) * pageSize + 1,
    to: Math.min(count, page * pageSize),
    hrefFor,
  };
}

/** How long the reader may pause typing before the list follows. */
const SEARCH_DELAY_MS = 250;

/**
 * The words in a search field, and the same words in the address a moment
 * later (under `param`). Returns what is typed, how to change it, and the
 * words the list should be asked for: the list follows the address, so a search can be shared and the
 * back button undoes it.
 */
export function useSearchWords(param: string): [string, (words: string) => void, string] {
  const [searchParams, setSearchParams] = useSearchParams();
  const inAddress = searchParams.get(param) ?? '';
  const [words, setWords] = useState(inAddress);
  // Back or forward changed the address under the field: show its words.
  const [followed, setFollowed] = useState(inAddress);
  if (followed !== inAddress) {
    setFollowed(inAddress);
    if (words.trim() !== inAddress) setWords(inAddress);
  }
  useEffect(() => {
    const wanted = words.trim();
    if (wanted === inAddress) return;
    const timer = window.setTimeout(() => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (wanted) next.set(param, wanted);
          else next.delete(param);
          // Other words, another list: start at its first page.
          next.delete(PAGE_PARAM);
          return next;
        },
        { replace: true },
      );
    }, SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [words, inAddress, param, setSearchParams]);
  return [words, setWords, inAddress];
}
