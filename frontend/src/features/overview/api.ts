/**
 * The stand van zaken endpoints. Amounts are class B: for a reader without
 * it, `totals` is an empty object and the grand total is absent.
 */
import { apiGet } from '@/api/client';

export interface Totals {
  budgeted_cents?: number;
  realised_cents?: number;
  forecast_cents?: number;
  coverage_cents?: number;
  used_cents?: number;
  available_cents?: number;
  overrun?: boolean;
}

export interface OverviewRow {
  assignment_id: string;
  name: string;
  status: string;
  client_name: string | null;
  start_date: string | null;
  end_date: string | null;
  totals: Totals | null;
  pricing_error?: string | null;
}

export interface Overview {
  year: number | null;
  rows: OverviewRow[];
  totals?: Totals;
}

export interface TeamMember {
  allocation_id: string;
  person_id: string;
  person_name: string;
  start_date?: string;
  end_date?: string;
  fte_pct?: string;
  amount_cents?: number | null;
  pricing_error?: string | null;
  category_mismatch?: boolean;
}

export interface LineCost {
  cost_item_id: string;
  description: string;
  pct: string;
  amount_cents: number | null;
}

export interface LineOverview {
  budget_line_id: string;
  description: string;
  kind: string;
  role?: string | null;
  fte?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  rate_category?: string | null;
  totals: Totals | null;
  pricing_error?: string | null;
  team: TeamMember[];
  costs?: LineCost[];
}

export interface AssignmentOverview {
  assignment_id: string;
  name: string;
  status: string;
  year: number | null;
  totals?: Totals | null;
  pricing_error?: string | null;
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
export function hasAmounts(totals: Totals | null | undefined): totals is Required<Totals> {
  return totals !== null && totals !== undefined && 'budgeted_cents' in totals;
}
