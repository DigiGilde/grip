/**
 * The feed of updates: what happened that the reader would want to know.
 * The server selects, collapses and writes the sentence; the screen shows it.
 */
import { apiGet, apiPost } from '@/api/client';

export interface UpdatePart {
  text: string;
  /** Where the thing is to be seen, inside the application. */
  href?: string;
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

export const UPDATE_KEYS = {
  all: ['updates'] as const,
  list: (limit: number) => ['updates', limit] as const,
};

export async function fetchUpdates(limit: number, cursor?: number): Promise<UpdatePage> {
  const page = await apiGet<Partial<UpdatePage>>('/api/updates', {
    limiet: limit,
    ...(cursor ? { na: cursor } : {}),
  });
  return {
    items: page.items ?? [],
    new_count: page.new_count ?? 0,
    next: page.next ?? null,
  };
}

/** The reader has looked: nothing that is there now is new any more. */
export const markUpdatesSeen = () => apiPost<void>('/api/updates/seen');

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
