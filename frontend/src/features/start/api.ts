/**
 * What Start tells the reader. A block the reader has no use for or no right
 * to is absent; decimals are strings, amounts whole cents, dates ISO.
 */
import { apiGet } from '@/api/client';

export interface ToDoGroup {
  case_kind: 'assignment' | 'vacancy' | 'instance';
  /** Null for the instance itself. */
  case_id: string | null;
  case_label: string;
  task_id: string;
  headline: string;
  /** Where the work is done; null when the reader may open neither it nor the case. */
  href: string | null;
  overdue: boolean;
  due_on: string | null;
  /** "daarna nog 7 maanden en 1 taak", without the name of the case. */
  more_text: string | null;
}

export interface StartData {
  to_do: { groups: ToDoGroup[]; total: number };
  my_work?: {
    person_id: string;
    rows: { assignment_id: string; name: string; line: string; warning: string | null }[];
    total: number;
  };
  my_assignments?: {
    rows: {
      assignment_id: string;
      name: string;
      line: string;
      /** This instance is the client: the assignment is followed under Aanvragen. */
      as_client?: boolean;
      verdict: 'room' | 'overrun' | null;
    }[];
    total: number;
  };
  planning?: {
    open_roles: number;
    open_fte: string;
    idle_people: number;
    idle_from: string | null;
  };
  my_people?: {
    rows: {
      person_id: string;
      name: string;
      now_pct: string | null;
      free_from: string | null;
    }[];
    total: number;
  };
  figures?: {
    year: number;
    expected_cents: number;
    budgeted_cents: number;
    room_cents?: number;
    shortfall?: boolean;
    /** Over the whole run of each quote, not only of `year`. */
    potential_cents: number;
    quotes_waiting: number;
    /** Executors whose cost items could not be counted in the agreed figures. */
    incomplete_by?: string[];
  };
  my_requests?: {
    rows: { assignment_id: string; name: string; line: string }[];
    total: number;
  };
  connections?: { problems: number };
}

export const START_KEYS = { all: ['start'] as const };

export const fetchStart = () => apiGet<StartData>('/api/start');
