import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { PersonOccupancy } from '../api';
import { hasInzet, type SortMode } from './model';

/**
 * Which people the table shows. Every figure on top opens the group it
 * counts, so a number can always be followed to the rows behind it.
 */
export type Show =
  | 'met-inzet'
  | 'zonder-inzet'
  | 'boven-100'
  | 'vrij'
  | 'zonder-inzet-jaar'
  | 'iedereen';

/** The view lives in the address, so a filtered table can be linked to. */
export const SHOW_PARAM = 'toon';
export const MONTH_PARAM = 'maand';
export const SORT_PARAM = 'volgorde';

const SORT_WORDS: Record<string, SortMode> = { naam: 'name', ruimte: 'free' };
const SORT_VALUES: Record<SortMode, string> = { problems: '', name: 'naam', free: 'ruimte' };

export type Groups = Record<Show, PersonOccupancy[]>;

export function groupPersons(persons: readonly PersonOccupancy[]): Groups {
  return {
    'met-inzet': persons.filter(hasInzet),
    // Exactly the people the figure "zonder inzet de komende 3 maanden" counts.
    'zonder-inzet': persons.filter((person) => person.idle_ahead),
    'boven-100': persons.filter((person) => (person.over_months?.length ?? 0) > 0),
    vrij: persons.filter((person) => person.now_pct !== null && Number(person.now_pct) < 100),
    'zonder-inzet-jaar': persons.filter((person) => !hasInzet(person)),
    iedereen: [...persons],
  };
}

const ids = (persons: readonly PersonOccupancy[]) =>
  persons
    .map((person) => person.person_id)
    .sort()
    .join(' ');

/** Whether two groups hold the same people; then one control is enough. */
export const sameGroup = (a: readonly PersonOccupancy[], b: readonly PersonOccupancy[]) =>
  ids(a) === ids(b);

const isShow = (value: string | null, groups: Groups): value is Show =>
  value !== null && Object.hasOwn(groups, value);

/** The table opens on the people with inzet; without any, on everyone. */
export const defaultShow = (groups: Groups): Show =>
  groups['met-inzet'].length > 0 ? 'met-inzet' : 'iedereen';

export interface ViewTarget {
  show: Show;
  month?: string;
  sort?: SortMode;
}

export function useOccupancyView(groups: Groups) {
  const [params, setParams] = useSearchParams();
  const fallback = defaultShow(groups);
  const asked = params.get(SHOW_PARAM);
  const show = isShow(asked, groups) ? asked : fallback;
  const sort = SORT_WORDS[params.get(SORT_PARAM) ?? ''] ?? 'problems';
  const month = params.get(MONTH_PARAM);

  /** The query string of a view, keeping whatever else is in the address. */
  const searchFor = useCallback(
    (target: ViewTarget) => {
      const next = new URLSearchParams(params);
      if (target.show === fallback) next.delete(SHOW_PARAM);
      else next.set(SHOW_PARAM, target.show);
      if (target.month) next.set(MONTH_PARAM, target.month);
      else next.delete(MONTH_PARAM);
      const word = SORT_VALUES[target.sort ?? 'problems'];
      if (word) next.set(SORT_PARAM, word);
      else next.delete(SORT_PARAM);
      const text = next.toString();
      return text ? `?${text}` : '';
    },
    [params, fallback],
  );

  const go = useCallback(
    (target: ViewTarget) => setParams(new URLSearchParams(searchFor(target)), { replace: false }),
    [setParams, searchFor],
  );

  return useMemo(
    () => ({ show, sort, month, searchFor, go, fallback }),
    [show, sort, month, searchFor, go, fallback],
  );
}
