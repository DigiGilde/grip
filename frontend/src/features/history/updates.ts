/**
 * The feed of updates: what happened that the reader would want to know.
 * The server selects, collapses and writes the sentence; the screen shows it.
 */
import { apiGet, apiPost } from '@/api/client';

export interface UpdatePart {
  text: string;
  /** Where the thing is to be seen, inside the application. */
  href?: string | null;
}

export interface UpdateItem {
  id: string;
  seq: number;
  kind: string;
  when: string;
  /** "vanochtend", "gisteren", then a date. */
  when_text: string;
  /** The day it is grouped under: "Vandaag", "Gisteren", a date. */
  day: string;
  parts: UpdatePart[];
  text: string;
  count: number;
  /** Came after the reader last looked. */
  new: boolean;
}

export interface UpdatePage {
  items: UpdateItem[];
  new_count: number;
  /** Pass as `na` to read further back; null when there is nothing older. */
  next: number | null;
}

/**
 * What the feed is narrowed to, by id, under the names the address and the
 * server give them: the items about one assignment, the items one person did.
 */
export interface UpdateFilter {
  opdracht?: string;
  persoon?: string;
}

export type UpdateFilterKey = keyof UpdateFilter;

export const FILTER_KEYS: readonly UpdateFilterKey[] = ['opdracht', 'persoon'];

export const NO_FILTER: UpdateFilter = {};

export const UPDATE_KEYS = {
  all: ['updates'] as const,
  list: (limit: number, filter: UpdateFilter = NO_FILTER) => ['updates', limit, filter] as const,
  filters: ['updates', 'filters'] as const,
};

export function isFiltered(filter: UpdateFilter): boolean {
  return FILTER_KEYS.some((key) => Boolean(filter[key]));
}

/** The filter the address holds: `?opdracht=<id>&persoon=<id>`. */
export function filterOf(params: URLSearchParams): UpdateFilter {
  const filter: UpdateFilter = {};
  for (const key of FILTER_KEYS) {
    const value = params.get(key);
    if (value) filter[key] = value;
  }
  return filter;
}

/** The address with one filter chosen, or without it when `value` is empty. */
export function withFilter(
  params: URLSearchParams,
  key: UpdateFilterKey,
  value: string,
): URLSearchParams {
  const next = new URLSearchParams(params);
  if (value) next.set(key, value);
  else next.delete(key);
  return next;
}

export async function fetchUpdates(
  limit: number,
  cursor?: number,
  filter: UpdateFilter = NO_FILTER,
): Promise<UpdatePage> {
  const page = await apiGet<Partial<UpdatePage>>('/api/updates', {
    limiet: limit,
    ...(cursor ? { na: cursor } : {}),
    ...filter,
  });
  return {
    items: page.items ?? [],
    new_count: page.new_count ?? 0,
    next: page.next ?? null,
  };
}

/** The reader has looked: nothing that is there now is new any more. */
export const markUpdatesSeen = () => apiPost<void>('/api/updates/seen');

export interface UpdateOption {
  id: string;
  name: string;
}

/** What the feed of this reader can be narrowed to, taken from that feed. */
export interface UpdateFilterOptions {
  assignments: UpdateOption[];
  people: UpdateOption[];
}

export async function fetchUpdateFilters(): Promise<UpdateFilterOptions> {
  const body = await apiGet<Partial<UpdateFilterOptions>>('/api/updates/filters');
  return { assignments: body.assignments ?? [], people: body.people ?? [] };
}

/** The options of each filter, keyed as the filter is. */
export function optionsFor(options: UpdateFilterOptions, key: UpdateFilterKey): UpdateOption[] {
  return key === 'opdracht' ? options.assignments : options.people;
}

/** Chooses nothing: the whole feed. */
export const ALL = '';

const CHOICE_WORDS: Record<UpdateFilterKey, { label: string; all: string }> = {
  opdracht: { label: 'Opdracht', all: 'Alle opdrachten' },
  persoon: { label: 'Persoon', all: 'Iedereen' },
};

export interface UpdateFilterChoice {
  key: UpdateFilterKey;
  label: string;
  value: string;
  options: { value: string; label: string }[];
}

/** A choice for each filter that has options, with the one in the address chosen. */
export function filterChoices(
  options: UpdateFilterOptions,
  filter: UpdateFilter,
): UpdateFilterChoice[] {
  return FILTER_KEYS.filter((key) => optionsFor(options, key).length > 0).map((key) => ({
    key,
    label: CHOICE_WORDS[key].label,
    value: filter[key] ?? ALL,
    options: [
      { value: ALL, label: CHOICE_WORDS[key].all },
      ...optionsFor(options, key).map((option) => ({ value: option.id, label: option.name })),
    ],
  }));
}

/**
 * The filters in the address that the options do not hold: an id this
 * reader cannot see in the feed or one that does not exist, which find
 * nothing, and one that every item has, which changes nothing.
 */
export function unknownFilters(
  filter: UpdateFilter,
  options: UpdateFilterOptions,
): UpdateFilterKey[] {
  return FILTER_KEYS.filter((key) => {
    const value = filter[key];
    return Boolean(value) && !optionsFor(options, key).some((option) => option.id === value);
  });
}

export interface UpdateDay {
  day: string;
  items: UpdateItem[];
}

/** The items under the day they happened, in the order they came. */
export function byDay(items: readonly UpdateItem[]): UpdateDay[] {
  const days: UpdateDay[] = [];
  for (const item of items) {
    const last = days[days.length - 1];
    if (last && last.day === item.day) last.items.push(item);
    else days.push({ day: item.day, items: [item] });
  }
  return days;
}
