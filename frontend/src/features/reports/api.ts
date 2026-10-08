/**
 * The report endpoints. The API leaves out what a reader may not see: a
 * block of the steering overview that is not for the reader is absent, and
 * so is a field of a class the reader lacks. Every amount arrives computed;
 * nothing is added up in the browser.
 */
import { apiGet } from '@/api/client';

/** all: everything, through a function. own: what follows from the reader's relations. */
export type Scope = 'all' | 'own';

// -- steering ---------------------------------------------------------------

export interface TurnoverMonth {
  month: string;
  realised_cents: number;
  /** Agreed formally or verbally; includes `verbal_cents`. */
  forecast_cents: number;
  verbal_cents: number;
  pipeline_cents: number;
}

export interface Turnover {
  scope: Scope;
  months: TurnoverMonth[];
  realised_cents: number;
  forecast_cents: number;
  verbal_cents: number;
  pipeline_cents: number;
  /** Realised plus forecast. */
  expected_cents: number;
  /** The year of the agreed assignments, in the words of the assignment pages. */
  figures: FinanceFigures;
  unpriced_assignments: string[];
}

export interface FinanceFigures {
  budgeted_cents: number;
  realised_cents: number;
  planned_cents: number;
  costs_cents: number;
  expected_total_cents: number;
  /** Budgeted minus expected total; negative is an overrun. */
  variance_cents: number;
  variance_pct: string | null;
  overrun: boolean;
  realised_total_cents: number;
  /** Uitputting: the share of the budget that is realised. */
  realised_pct: string | null;
}

export interface OccupancyMonth {
  month: string;
  allocated_fte: string;
  tentative_fte: string;
  available_fte: string;
  free_fte: string;
  pct: string | null;
  under: number;
  full: number;
  over: number;
}

export interface OccupancySummary {
  person_count: number;
  average_pct: string | null;
  over_count: number;
  over_months: string[];
  /** Today's month, whatever year is on screen. */
  current_month: string;
  /** This month and the three after it. */
  window: OccupancyMonth[];
  idle_count: number;
}

export interface OccupancyPart {
  /** Absent when the reader may not see that assignment. */
  assignment_id?: string;
  assignment_name?: string;
  pct: string;
  tentative: boolean;
  verbally_agreed: boolean;
  established: boolean;
}

export interface OccupancyCell {
  month: string;
  available: boolean;
  pct: string;
  tentative_pct: string;
  established: boolean;
  parts: OccupancyPart[];
}

export interface PersonOccupancy {
  person_id: string;
  person_name: string;
  average_pct: string | null;
  over_months: string[];
  cells: OccupancyCell[];
}

export interface Occupancy {
  scope: Scope;
  summary: OccupancySummary;
  months: OccupancyMonth[];
  persons: PersonOccupancy[];
  not_deployable?: { person_id: string; person_name: string }[];
}

export interface PipelineStatus {
  status: string;
  count: number;
  total_cents: number;
}

export interface PipelineQuote {
  quote_id: string;
  assignment_id: string;
  assignment_name: string;
  client_name: string | null;
  status: string;
  total_cents: number;
  issued_at: string;
  valid_until: string | null;
}

export interface Pipeline {
  scope: Scope;
  statuses: PipelineStatus[];
  waiting: PipelineQuote[];
}

export interface CostCoverageItem {
  cost_item_id: string;
  description: string;
  forecast_cents: number;
  covered_cents: number | null;
  uncovered_cents: number | null;
  pct_total: string;
}

export interface CostCoverage {
  scope: Scope;
  forecast_cents: number;
  covered_cents: number;
  uncovered_cents: number;
  items: CostCoverageItem[];
}

export interface PersonKpi {
  person_id: string;
  person_name: string;
  year: number;
  target_pct: string | null;
  target_cents: number | null;
  realised_cents: number | null;
  forecast_cents: number | null;
  realisation_cents: number | null;
  unavailable_reason: string | null;
}

export interface Billability {
  scope: Scope;
  persons: PersonKpi[];
  target_cents: number;
  realised_cents: number;
  forecast_cents: number;
  realisation_cents: number;
  with_target_count: number;
  below_target_count: number;
}

export interface OpenRole {
  assignment_id: string | null;
  assignment_name: string | null;
  budget_line_id: string | null;
  description: string;
  unfilled_fte: string;
  start_date: string | null;
  end_date: string | null;
  vacancy_status: string | null;
}

export interface OpenRoles {
  scope: Scope;
  unfilled_fte: string;
  roles: OpenRole[];
}

export interface Steering {
  year: number;
  turnover?: Turnover;
  occupancy?: Occupancy;
  pipeline?: Pipeline;
  costs?: CostCoverage;
  billability?: Billability;
  open_roles?: OpenRoles;
}

// -- year account -----------------------------------------------------------

export interface YearAccountRow {
  assignment_id: string;
  uri: string;
  name: string;
  kind: string;
  client_name: string | null;
  status: string;
  start_date: string | null;
  end_date: string | null;
  agreed_cents?: number | null;
  budgeted_cents?: number | null;
  realised_cents?: number | null;
  forecast_cents?: number | null;
  costs_cents?: number | null;
  /** Billing data delivered to the financial administration; not an invoice. */
  delivered_cents?: number;
  to_deliver_cents?: number | null;
  /** An invoice recorded as sent; zero until one is recorded. */
  invoiced_cents?: number;
  /** Delivered, and no invoice recorded for it. */
  to_invoice_cents?: number;
  difference_cents?: number | null;
  pricing_error?: string | null;
}

export interface YearAccountTotals {
  agreed_cents: number;
  budgeted_cents: number;
  realised_cents: number;
  forecast_cents: number;
  costs_cents: number;
  delivered_cents: number;
  to_deliver_cents: number;
  invoiced_cents: number;
  to_invoice_cents: number;
}

export interface YearAccount {
  year: number;
  scope: Scope;
  rows: YearAccountRow[];
  totals?: YearAccountTotals;
}

// -- report per assignment --------------------------------------------------

/** Budgeted, used and available. Absent fields: the reader lacks class B. */
export interface Totals {
  budgeted_cents?: number;
  realised_cents?: number;
  forecast_cents?: number;
  coverage_cents?: number;
  used_cents?: number;
  available_cents?: number;
  overrun?: boolean;
}

/** Whether the reader got amounts at all. */
export function hasAmounts(totals: Totals | null | undefined): totals is Required<Totals> {
  return totals !== null && totals !== undefined && 'budgeted_cents' in totals;
}

export type Audience = 'client' | 'internal';

export interface AgreedLine {
  description: string;
  kind: string;
  role: string | null;
  fte: string | null;
  start_date: string | null;
  end_date: string | null;
  amount_cents: number;
}

export interface Agreed {
  quote_id: string;
  quote_uri: string;
  issued_at: string;
  accepted_at: string | null;
  form: string | null;
  total_cents: number;
  lines: AgreedLine[];
  subtotals: { year: number; amount_cents: number }[];
}

export interface StatusChange {
  occurred_at: string;
  old_status: string | null;
  new_status: string;
  reason: string | null;
}

export interface FinalReport {
  issued_at: string;
  summary: string | null;
  delivered: string[];
  not_delivered: string[];
}

export interface ReportPeriod {
  year: number;
  totals: Totals | null;
  pricing_error: string | null;
}

export interface ReportLine {
  budget_line_id: string;
  description: string;
  kind: string;
  totals?: Totals | null;
  pricing_error?: string | null;
}

export interface ReportCost {
  cost_item_id: string;
  description: string;
  budget_line_description: string;
  pct: string;
  amount_cents: number | null;
}

export interface ReportStaffing {
  person_id: string;
  person_name: string;
  budget_line_description: string;
  role?: string | null;
  start_date?: string;
  end_date?: string;
  fte_pct?: string;
}

export interface AssignmentReport {
  assignment_id: string;
  uri: string;
  name: string;
  kind: string;
  status: string;
  client_name: string | null;
  contractor_name: string | null;
  start_date: string | null;
  end_date: string | null;
  context_refs: string[];
  audience: Audience;
  generated_on: string;
  months_total: number;
  months_closed: number;
  agreed?: Agreed | null;
  quoted_amount_cents?: number | null;
  status_history: StatusChange[];
  final_report: FinalReport | null;
  months: { month: string; closed: boolean; closed_at: string | null }[];
  totals?: Totals | null;
  pricing_error?: string | null;
  periods?: ReportPeriod[];
  lines: ReportLine[];
  costs?: ReportCost[];
  staffing?: ReportStaffing[];
}

export const reportKeys = {
  steering: (year: string) => ['reports', 'steering', year] as const,
  yearAccount: (year: string) => ['reports', 'year-account', year] as const,
  assignment: (id: string, audience: Audience) =>
    ['reports', 'assignment', id, audience] as const,
};

export const fetchSteering = (year: string) =>
  apiGet<Steering>('/api/reports/steering', { year });

export const fetchYearAccount = (year: string) =>
  apiGet<YearAccount>('/api/reports/year-account', { year });

export const fetchAssignmentReport = (id: string, audience: Audience) =>
  apiGet<AssignmentReport>(`/api/reports/assignments/${id}`, { audience });

/** The CSV of the year account; a download, so a plain link. */
export const yearAccountCsvUrl = (year: string) =>
  `/api/reports/year-account/csv?year=${encodeURIComponent(year)}`;

/** The printable page of an assignment report. */
export const assignmentReportDocumentUrl = (id: string, audience: Audience) =>
  `/api/reports/assignments/${id}/document?audience=${audience}`;
