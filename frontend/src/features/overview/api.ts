/**
 * The stand van zaken endpoints. Amounts are class B: for a reader without
 * it, `figures` is absent or empty and the subtotals are absent.
 */
import { apiGet } from '@/api/client';
import type { Figures } from '@/features/assignments/financeApi';
import type { Phase } from '@/features/assignments/labels';

export type { Figures };

export interface OverviewRow {
  assignment_id: string;
  name: string;
  status: string;
  phase: Phase;
  client_name: string | null;
  start_date: string | null;
  end_date: string | null;
  figures?: Partial<Figures> | null;
  pricing_error?: string | null;
  /** First day of the last closed month; null when none is closed. */
  reference_month?: string | null;
}

export interface Overview {
  year: number | null;
  rows: OverviewRow[];
  /** Subtotal per phase; pipeline is never added to running work. */
  figures_potential?: Figures;
  figures_active?: Figures;
  figures_closed?: Figures;
}

export interface TeamMember {
  allocation_id: string;
  person_id: string;
  person_name: string;
  start_date?: string;
  end_date?: string;
  fte_pct?: string;
  category_mismatch?: boolean;
}

export interface LineOverview {
  budget_line_id: string;
  description: string;
  kind: string;
  role?: string | null;
  fte?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  team: TeamMember[];
}

/** The lines of one assignment with their team; the staffing tab reads this. */
export interface AssignmentOverview {
  assignment_id: string;
  name: string;
  status: string;
  year: number | null;
  lines: LineOverview[];
}

/** The year filter: a year, or 'all' for the whole period. */
export type YearChoice = string;

export const overviewKeys = {
  list: (year: YearChoice) => ['overview', 'list', year] as const,
  assignment: (id: string, year: YearChoice) => ['overview', 'assignment', id, year] as const,
};

export const fetchOverview = (year: YearChoice) => apiGet<Overview>('/api/overview', { year });

export const fetchAssignmentOverview = (id: string, year: YearChoice) =>
  apiGet<AssignmentOverview>(`/api/assignments/${id}/overview`, { year });

/** Whether the reader got amounts at all. */
export function hasFigures(figures: Partial<Figures> | null | undefined): figures is Figures {
  return figures !== null && figures !== undefined && 'budgeted_cents' in figures;
}

/**
 * The totals of the report screens (budgeted, realised, forecast, costs,
 * available), which still read `/api/reports`. The stand van zaken itself
 * uses `Figures`.
 */
export interface Totals {
  budgeted_cents?: number;
  realised_cents?: number;
  forecast_cents?: number;
  coverage_cents?: number;
  used_cents?: number;
  available_cents?: number;
  overrun?: boolean;
}

export function hasAmounts(totals: Totals | null | undefined): totals is Required<Totals> {
  return totals !== null && totals !== undefined && 'budgeted_cents' in totals;
}
