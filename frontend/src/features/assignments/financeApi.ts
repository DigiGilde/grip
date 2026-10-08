/**
 * The financial state of one assignment. Every figure is computed by the
 * service; the screen formats and never adds up.
 */
import { apiGet } from '@/api/client';

export interface Figures {
  budgeted_cents: number;
  /** Inzet of closed months, at the established percentage. */
  realised_cents: number;
  /** Inzet of open months, at the planned percentage. */
  planned_cents: number;
  costs_realised_cents: number;
  costs_forecast_cents: number;
  costs_cents: number;
  /** Realised plus planned plus costs. */
  expected_total_cents: number;
  /** Budgeted minus expected total; negative is an overrun. */
  variance_cents: number;
  variance_pct: string | null;
  overrun: boolean;
  realised_total_cents: number;
  /** Share of the budget already realised. */
  realised_pct: string | null;
}

export interface KeyFigures {
  agreed_cents: number | null;
  budgeted_cents: number | null;
  expected_total_cents: number | null;
  agreed_minus_budgeted_cents: number | null;
  budgeted_minus_expected_cents: number | null;
  realised_cents: number | null;
  realised_pct: string | null;
  /** Aangeleverd: billing data exported for the financial administration. */
  delivered_cents: number;
  /** Nog aan te leveren: closed and priced, not delivered yet. */
  to_deliver_cents: number | null;
  /** Gefactureerd: only what was recorded as actually invoiced. */
  invoiced_cents: number;
  /** Nog te factureren: delivered, and no invoice recorded for it. */
  to_invoice_cents: number;
}

export interface PersonAmount {
  allocation_id: string;
  person_id: string;
  person_name: string;
  start_date?: string;
  end_date?: string;
  realised_cents: number;
  planned_cents: number;
  total_cents: number;
  category_mismatch?: boolean;
}

export interface CostAmount {
  cost_item_id: string;
  description: string;
  pct: string;
  realised_cents: number;
  forecast_cents: number;
  total_cents: number;
}

export interface FinanceLine {
  budget_line_id: string;
  description: string;
  kind: string;
  rate_category: string | null;
  figures: Figures | null;
  pricing_error: string | null;
  /** Why the line runs over or under; the server words it for this reader. */
  rate_difference_notes?: string[];
  persons: PersonAmount[];
  /** Persons on the line whose amounts this reader may not see. */
  persons_hidden: number;
  costs: CostAmount[];
}

export interface MonthRow {
  month: string;
  closed: boolean;
  budgeted_cents: number;
  planned_cents: number;
  realised_cents: number | null;
  cumulative_budgeted_cents: number;
  cumulative_realised_cents: number;
  cumulative_planned_open_cents: number;
  cumulative_expected_cents: number;
  cumulative_variance_cents: number;
}

export interface Signal {
  kind: 'overrun' | 'free_room' | 'rate_mismatch' | 'months_not_closed' | 'not_priced' | string;
  budget_line_id: string | null;
  description: string | null;
  amount_cents: number | null;
  pct: string | null;
  count: number | null;
  months: string[];
}

export interface AssignmentFinance {
  assignment_id: string;
  name: string;
  year: number | null;
  /** First day of the last closed month; null when none is closed. */
  reference_month: string | null;
  key_figures: KeyFigures;
  totals: Figures | null;
  pricing_error: string | null;
  lines: FinanceLine[];
  months: MonthRow[];
  budgeted_outside_months_cents: number;
  signals: Signal[];
  free_room_threshold_pct: string;
}

export const financeKeys = {
  assignment: (id: string, year: string) => ['overview', 'finance', id, year] as const,
};

export const fetchAssignmentFinance = (id: string, year: string) =>
  apiGet<AssignmentFinance>(`/api/assignments/${id}/financial`, { year });

/** The CSV of what the tab shows; a download, so a plain link. */
export const financeCsvPath = (id: string, year: string, section: 'lines' | 'months') =>
  `/api/assignments/${id}/financial/csv?year=${encodeURIComponent(year)}&section=${section}`;
