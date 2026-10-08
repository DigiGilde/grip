/**
 * The monthly close and billing data endpoints. Fields of a data class the
 * person may not see are absent, so most fields are optional here.
 */
import { apiGet, apiPatch, apiPost } from '@/api/client';
import { withLists } from '@/lib/absent';

export interface MonthState {
  month: string;
  closed: boolean;
  closable: boolean;
  closed_at: string | null;
  closed_by_name: string | null;
  reopen_count: number;
}

export interface MonthTimeline {
  assignment_id: string;
  assignment_name: string;
  /** False until there is an agreement with the client: no month can be closed yet. */
  closing_started: boolean;
  /** Whether the reader is the one who closes months of this assignment. */
  may_close: boolean;
  months: MonthState[];
}

export interface MonthLine {
  allocation_id: string;
  person_id: string;
  person_name: string;
  description: string;
  planned_fte_pct?: string;
  established_fte_pct?: string | null;
  category?: string;
  monthly_rate_cents?: number;
  planned_amount_cents?: number;
  established_amount_cents?: number | null;
}

export interface CloseRecord {
  closed_at: string;
  closed_by_name: string | null;
  reopened_at: string | null;
  reopened_by_name: string | null;
  reopen_reason: string | null;
}

export interface MonthDetail {
  assignment_id: string;
  month: string;
  closed: boolean;
  closable: boolean;
  closed_at: string | null;
  closed_by_name: string | null;
  may_close: boolean;
  may_reopen: boolean;
  pricing_problem: string | null;
  lines: MonthLine[];
  history: CloseRecord[];
  planned_total_cents?: number;
  established_total_cents?: number | null;
}

export interface BillingExportLine {
  description: string;
  person_name: string;
  fte_pct?: string;
  category?: string;
  monthly_rate_cents?: number;
  amount_cents?: number;
}

export interface BillingExport {
  id: string;
  assignment_id: string;
  month: string;
  created_at: string;
  exported_by_name: string | null;
  total_cents?: number;
  lines: BillingExportLine[];
}

export const monthKeys = {
  timeline: (assignmentId: string) => ['months', assignmentId, 'timeline'] as const,
  detail: (assignmentId: string, month: string) => ['months', assignmentId, month] as const,
  exports: (assignmentId: string) => ['months', assignmentId, 'exports'] as const,
};

export function fetchTimeline(assignmentId: string): Promise<MonthTimeline> {
  return apiGet(`/api/assignments/${assignmentId}/months`);
}

// Lines and history are absent for a reader who may not see them.
const monthDetail = (detail: MonthDetail): MonthDetail => withLists(detail, 'lines', 'history');
const billingExport = (run: BillingExport): BillingExport => withLists(run, 'lines');

export function fetchMonth(assignmentId: string, month: string): Promise<MonthDetail> {
  return apiGet<MonthDetail>(`/api/assignments/${assignmentId}/months/${month}`).then(monthDetail);
}

export function closeMonth(
  assignmentId: string,
  month: string,
  established: { allocation_id: string; fte_pct: string }[],
): Promise<MonthDetail> {
  return apiPost<MonthDetail>(`/api/assignments/${assignmentId}/months/${month}/close`, {
    established,
  }).then(monthDetail);
}

export function reopenMonth(
  assignmentId: string,
  month: string,
  reason: string,
): Promise<MonthDetail> {
  return apiPost<MonthDetail>(`/api/assignments/${assignmentId}/months/${month}/reopen`, {
    reason,
  }).then(monthDetail);
}

export function fetchExports(assignmentId: string): Promise<{ exports: BillingExport[] }> {
  return apiGet<{ exports?: BillingExport[] }>(
    `/api/assignments/${assignmentId}/billing-exports`,
  ).then((body) => ({ exports: (body.exports ?? []).map(billingExport) }));
}

export function createExport(assignmentId: string, month: string): Promise<BillingExport> {
  return apiPost<BillingExport>(
    `/api/assignments/${assignmentId}/months/${month}/billing-exports`,
  ).then(billingExport);
}

export function exportCsvUrl(exportId: string): string {
  return `/api/billing-exports/${exportId}/csv`;
}

/**
 * A percentage as typed (Dutch decimal comma allowed) in the form the API
 * takes, or null when it is not a percentage between 0 and 100. This only
 * normalises the notation; no amount is computed in the browser.
 */
export function normalisePercent(input: string): string | null {
  const text = input.trim().replace('%', '').replace(',', '.').trim();
  if (!/^\d{1,3}(\.\d{1,3})?$/.test(text)) return null;
  const value = Number(text);
  if (value < 0 || value > 100) return null;
  return text;
}

/** A percentage from the API as the text of an input, with a decimal comma. */
export function percentInput(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  const number = Number(value);
  if (Number.isNaN(number)) return '';
  return String(number).replace('.', ',');
}

/** Where a closed month stands: delivered, invoiced, or neither. */
export interface MonthBilling {
  month: string;
  closed: boolean;
  state: 'not_delivered' | 'delivered' | 'invoiced';
  deliverable_cents: number | null;
  to_deliver_cents: number | null;
  export_id: string | null;
  delivered_at: string | null;
  delivered_by_name: string | null;
  delivered_cents: number | null;
  invoice_id: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  invoiced_cents: number | null;
  invoice_on_earlier_delivery: boolean;
}

/** The recorded fact that an invoice was sent. */
export interface OutgoingInvoice {
  id: string;
  invoice_number: string;
  invoice_date: string;
  amount_cents: number;
  delivered_cents: number;
  difference_cents: number;
  months: string[];
  export_ids: string[];
  source: 'manual' | 'financial_system';
  note: string | null;
  recorded_at: string;
  recorded_by_name: string | null;
  withdrawn_at: string | null;
  withdrawn_by_name: string | null;
  withdrawn_reason: string | null;
}

/**
 * Delivered and invoiced of an assignment. The amounts, months and invoices
 * are absent for someone who may not read the financial data.
 */
export interface BillingStatus {
  assignment_id: string;
  year: number | null;
  billable: boolean;
  may_record_invoice: boolean;
  deliverable_cents?: number | null;
  delivered_cents?: number;
  to_deliver_cents?: number | null;
  invoiced_cents?: number;
  to_invoice_cents?: number;
  months?: MonthBilling[];
  invoices?: OutgoingInvoice[];
}

export const billingKey = (assignmentId: string) => ['months', assignmentId, 'billing'] as const;

export function fetchBillingStatus(assignmentId: string): Promise<BillingStatus> {
  return apiGet(`/api/assignments/${assignmentId}/billing-status`);
}

/** What was delivered for a selection of deliveries, added up by the server. */
export function fetchInvoiceProposal(
  assignmentId: string,
  exportIds: string[],
): Promise<{ months: string[]; delivered_cents: number }> {
  const query = exportIds.map((id) => `export_id=${encodeURIComponent(id)}`).join('&');
  return apiGet(`/api/assignments/${assignmentId}/outgoing-invoices/proposal?${query}`);
}

export interface InvoiceInput {
  export_ids: string[];
  invoice_number: string;
  invoice_date: string;
  amount_cents: number;
  note: string | null;
}

export function recordInvoice(assignmentId: string, input: InvoiceInput): Promise<BillingStatus> {
  return apiPost(`/api/assignments/${assignmentId}/outgoing-invoices`, input);
}

export function correctInvoice(
  invoiceId: string,
  input: Omit<InvoiceInput, 'export_ids'>,
): Promise<BillingStatus> {
  return apiPatch(`/api/outgoing-invoices/${invoiceId}`, { ...input, note: input.note ?? '' });
}

export function withdrawInvoice(invoiceId: string, reason: string): Promise<BillingStatus> {
  return apiPost(`/api/outgoing-invoices/${invoiceId}/withdraw`, { reason });
}
