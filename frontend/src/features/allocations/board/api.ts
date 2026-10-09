/**
 * The planner's board. Time and people only: the endpoint returns no
 * amounts. A field of a data class the reader may not see is absent.
 */
import { apiGet } from '@/api/client';

export interface BoardCell {
  /** First day of the month. */
  month: string;
  /** False in a month the person could not be deployed. */
  available: boolean;
  pct: string;
  tentative_pct: string;
  over: boolean;
  /** Everything in this month comes from a closed month. */
  established: boolean;
}

export interface BoardBar {
  allocation_id: string;
  person_id: string;
  person_name: string;
  assignment_id?: string;
  assignment_name?: string;
  budget_line_id?: string;
  line_description?: string;
  role?: string | null;
  tentative: boolean;
  verbally_agreed: boolean;
  start_date: string;
  end_date: string;
  fte_pct: string;
  /** First days of the closed months of this allocation. */
  closed_months: string[];
  can_edit: boolean;
  category_mismatch?: boolean;
  line_category?: string | null;
  person_category?: string | null;
}

export interface BoardPerson {
  person_id: string;
  person_name: string;
  manager_id?: string | null;
  manager_name?: string | null;
  /** Empty when the reader may not see the person's totals. */
  cells: BoardCell[];
  now_pct?: string | null;
  /** First month from now with less than 100 percent. */
  room_from?: string | null;
  /** First month from which there is no inzet at all. */
  idle_from?: string | null;
  over_months?: string[];
  bars: BoardBar[];
}

export interface BoardOpenRole {
  budget_line_id: string;
  assignment_id: string;
  assignment_name: string;
  description: string;
  role?: string | null;
  fte: string;
  unfilled_fte: string;
  start_date: string | null;
  end_date: string | null;
  can_fill: boolean;
}

export interface Board {
  months: string[];
  current_month: string;
  persons: BoardPerson[];
  open_roles: BoardOpenRole[];
  can_add: boolean;
}

export const BOARD_MONTHS = 12;

export const boardKeys = {
  board: (start: string) => ['allocations', 'board', start] as const,
  // Under the board's key, so whatever refreshes the board refreshes this too.
  person: (personId: string) => ['allocations', 'board', '', 'person', personId] as const,
};

/** `start` is the first month as YYYY-MM; empty for the default window. */
export const fetchBoard = (start: string) =>
  apiGet<Board>('/api/allocations/board', { start, months: BOARD_MONTHS });

/** The board with the row of one person only, for the page about them. */
export const fetchPersonBoard = (personId: string) =>
  apiGet<Board>('/api/allocations/board', { months: BOARD_MONTHS, person_id: personId });
