/**
 * Billing per period: settle per month, deliver per billing period, record
 * the invoice per delivery. Amounts are absent for a reader without the
 * right to see the money of the assignment.
 */
import { apiGet, apiPost, apiPut } from '@/api/client';

export type Rhythm = 'month' | 'quarter';
export type PeriodState = 'running' | 'to_close' | 'ready' | 'delivered' | 'invoiced';
export type MonthStateName = 'closed' | 'to_close' | 'running' | 'upcoming';

/** What the client gave for the invoice. */
export const DETAIL_KEYS = [
  'organisation',
  'attention_of',
  'address',
  'postcode_city',
  'reference',
  'contact_name',
  'contact_phone',
  'contact_email',
] as const;
export type DetailKey = (typeof DETAIL_KEYS)[number];
export type BillingDetails = Partial<Record<DetailKey, string>>;

export interface BillingTerms {
  rhythm: Rhythm;
  rhythm_is_default: boolean;
  details?: BillingDetails;
  missing_details?: DetailKey[];
  names_on_specification?: boolean;
}

export interface PeriodMonth {
  month: string;
  label: string;
  state: MonthStateName;
  closed_at: string | null;
  closed_by_name: string | null;
  amount_cents?: number | null;
  delivered_cents?: number | null;
  correction_cents?: number;
}

export interface BillingDelivery {
  id: string;
  reference: string;
  period_key: string;
  total_cents: number;
  via: 'mail' | 'self';
  recipient: string | null;
  delivered_at: string;
  delivered_by_name: string | null;
  has_document: boolean;
  mail_state: 'queued' | 'sent' | 'failed' | null;
  invoice_id: string | null;
  invoice_number: string | null;
}

export interface BillingPeriod {
  key: string;
  label: string;
  span: string;
  state: PeriodState;
  months: PeriodMonth[];
  closed_cents?: number | null;
  to_deliver_cents?: number | null;
  delivered_cents?: number;
  invoiced_cents?: number;
  deliveries?: BillingDelivery[];
  invoice_numbers?: string[];
  awaits_invoice?: boolean;
  last_step_at: string | null;
}

export interface NextStep {
  kind: 'close_month' | 'deliver' | 'record_invoice' | 'none';
  month: string | null;
  month_label: string | null;
  period_key: string | null;
  period_label: string | null;
  amount_cents?: number | null;
  from_date: string | null;
}

export interface BillingOverview {
  assignment_id: string;
  assignment_name: string;
  client_name: string | null;
  closing_started: boolean;
  billable: boolean;
  may_close: boolean;
  may_deliver: boolean;
  may_record_invoice: boolean;
  may_edit_terms: boolean;
  terms: BillingTerms;
  next_step: NextStep;
  periods: BillingPeriod[];
  upcoming_count: number;
  upcoming_until: string | null;
  closed_cents?: number | null;
  delivered_cents?: number;
  invoiced_cents?: number;
  can_mail: boolean;
  recipient?: string | null;
}

export const billingOverviewKey = (assignmentId: string) =>
  ['months', assignmentId, 'periods'] as const;
export const billingAcrossKey = ['billing', 'across'] as const;

export function fetchBillingOverview(assignmentId: string): Promise<BillingOverview> {
  return apiGet(`/api/assignments/${assignmentId}/billing`);
}

export interface TermsInput {
  rhythm?: Rhythm;
  details?: BillingDetails;
  names_on_specification?: boolean;
}

export function saveTerms(assignmentId: string, input: TermsInput): Promise<BillingOverview> {
  return apiPut(`/api/assignments/${assignmentId}/billing/terms`, input);
}

export function deliverPeriod(
  assignmentId: string,
  periodKey: string,
  via: 'mail' | 'self',
): Promise<BillingOverview> {
  return apiPost(`/api/assignments/${assignmentId}/billing/deliveries`, {
    period_key: periodKey,
    via,
  });
}

export interface PeriodInvoiceInput {
  invoice_number: string;
  invoice_date: string;
  amount_cents: number;
  note: string | null;
}

export function recordPeriodInvoice(
  assignmentId: string,
  periodKey: string,
  input: PeriodInvoiceInput,
): Promise<BillingOverview> {
  return apiPost(`/api/assignments/${assignmentId}/billing/periods/${periodKey}/invoice`, input);
}

export function deliveryDocumentUrl(deliveryId: string): string {
  return `/api/billing/deliveries/${deliveryId}/document`;
}

export function deliveryCsvUrl(deliveryId: string): string {
  return `/api/billing/deliveries/${deliveryId}/csv`;
}

export interface BillingAcross {
  assignments: BillingOverview[];
  can_mail: boolean;
}

export function fetchBillingAcross(): Promise<BillingAcross> {
  return apiGet('/api/billing');
}

export function deliverBatch(
  items: { assignment_id: string; period_key: string }[],
  via: 'mail' | 'self',
): Promise<{ delivered: { id: string; reference: string }[] }> {
  return apiPost('/api/billing/deliveries/batch', { items, via });
}

export interface DeliveryLine {
  month: string;
  month_label: string;
  correction: boolean;
  description: string;
  person_name: string;
  fte_pct: string;
  monthly_rate_cents: number;
  amount_cents: number;
}

export interface DeliveryDetail {
  id: string;
  assignment_id: string;
  reference: string;
  assignment_name: string;
  client_name: string | null;
  period_label: string;
  total_cents: number;
  delivered_at: string;
  delivered_by_name: string | null;
  has_document: boolean;
  details: BillingDetails;
  lines: DeliveryLine[];
}

export function fetchDelivery(deliveryId: string): Promise<DeliveryDetail> {
  return apiGet(`/api/billing/deliveries/${deliveryId}`);
}
