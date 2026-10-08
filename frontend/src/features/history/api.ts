/**
 * The history API: what happened, as the reader may know it. An event the
 * reader may not know of is absent; a field whose values the reader may not
 * see comes with `visible: false` and no values.
 */
import { apiGet } from '@/api/client';

export type CaseKind = 'assignment' | 'vacancy';

export interface EventChange {
  field: string;
  visible: boolean;
  old?: unknown;
  new?: unknown;
}

export interface HistoryEvent {
  seq: number;
  id: string;
  occurred_at: string;
  type: string;
  action?: string | null;
  subject_kind: string;
  subject_id?: string | null;
  case_kind?: CaseKind | null;
  case_id?: string | null;
  actor_kind: 'person' | 'guest' | 'peer' | 'system';
  actor_person_id?: string | null;
  actor_name?: string | null;
  correlation_id: string;
  person_id?: string | null;
  person_name?: string | null;
  changes: EventChange[];
  details_visible: boolean;
  payload?: Record<string, unknown> | null;
  note?: string | null;
  erased?: boolean;
}

export interface EventPage {
  items: HistoryEvent[];
  /** Pass as `before` to read on; null when there is nothing older. */
  next_before: number | null;
}

export interface EventFilters {
  case_kind?: CaseKind;
  case_id?: string;
  subject_kind?: string;
  actor_id?: string;
  person_id?: string;
  since?: string;
  until?: string;
}

export const PAGE_SIZE = 50;

export const HISTORY_KEYS = {
  all: ['history'] as const,
  list: (filters: EventFilters) => ['history', filters] as const,
  kinds: ['history', 'kinds'] as const,
};

export async function fetchEvents(filters: EventFilters, before?: number): Promise<EventPage> {
  const page = await apiGet<Partial<EventPage>>('/api/events', {
    ...filters,
    limit: PAGE_SIZE,
    ...(before ? { before } : {}),
  });
  return { items: page.items ?? [], next_before: page.next_before ?? null };
}

export const fetchKinds = async () =>
  (await apiGet<{ items?: string[] }>('/api/events/kinds')).items ?? [];
