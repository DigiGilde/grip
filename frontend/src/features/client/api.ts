/**
 * The client side of an instance: asking a contractor for a quote, the
 * quotes that came in, and following an assignment. Fields of a data class
 * the person may not see are absent from a response, not null, so most
 * fields are optional here.
 */
import { apiGet, apiPost } from '@/api/client';
import type { QuoteContent, QuoteSummary } from '@/features/quotes/api';

export interface ContractorOption {
  peer_id: string;
  name: string;
  base_uri: string;
  reachable: boolean;
}

export interface ClientOptions {
  may_request: boolean;
  contractors?: ContractorOption[];
  problem?: string | null;
}

export interface Delivery {
  operation: string;
  status: 'pending' | 'sent' | 'rejected' | 'dead' | string;
  queued_at: string;
  sent_at?: string | null;
  attempts?: number;
}

export interface QuoteRef {
  id: string;
  status: string;
  issued_at: string;
  total_cents?: number;
}

export interface ClientAssignment {
  id: string;
  uri: string;
  name: string;
  status: string;
  contractor_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  created_at: string;
  context_count?: number;
  latest_quote?: QuoteRef | null;
  request_delivery?: Delivery | null;
}

export interface ClientAssignmentList {
  may_request: boolean;
  items: ClientAssignment[];
}

export interface ClientAssignmentDetail extends ClientAssignment {
  description?: string | null;
  context_refs?: string[];
  quotes?: QuoteRef[];
  contractor_reachable?: boolean;
  may_request_usage?: boolean;
}

export interface AssignmentRequestInput {
  contractor_peer_id: string;
  name: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  context_uris: string[];
}

export interface ReceivedRequest {
  id: string;
  uri: string;
  name: string;
  status: string;
  client_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
  context_count?: number;
  quote_count?: number;
  received_at: string;
}

export interface ReceivedQuoteRow {
  id: string;
  assignment_id: string;
  assignment_name: string;
  contractor_name?: string | null;
  status: string;
  issued_at: string;
  total_cents?: number;
  may_decide?: boolean;
}

export interface ReceivedQuoteDetail {
  assignment_id: string;
  assignment_name: string;
  contractor_name?: string | null;
  may_decide?: boolean;
  quote: QuoteSummary & { content?: QuoteContent | null };
  deliveries?: Delivery[];
}

export interface Milestone {
  description: string;
  due_date?: string | null;
  state?: string | null;
}

export interface Progress {
  available: boolean;
  problem?: string | null;
  fetched_at: string;
  status?: string | null;
  as_of?: string | null;
  summary?: string | null;
  milestones?: Milestone[];
  delivered?: string[];
  not_delivered?: string[];
}

export interface UsageLine {
  description: string;
  budgeted_cents?: number | null;
  used_cents?: number | null;
  available_cents?: number | null;
}

export interface BudgetUsage {
  available: boolean;
  not_in_contract?: boolean;
  problem?: string | null;
  fetched_at: string;
  as_of?: string | null;
  year?: number | null;
  budgeted_cents?: number | null;
  used_cents?: number | null;
  available_cents?: number | null;
  lines?: UsageLine[];
}

export interface FinalReport {
  received: boolean;
  received_at?: string | null;
  issued_at?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  summary?: string | null;
  agreed?: string[];
  delivered?: string[];
  not_delivered?: { description: string; reason?: string | null }[];
  total_cost_cents?: number | null;
}

export interface Decision {
  quote_id: string;
  assignment_id: string;
  decision: 'accepted' | 'rejected';
  decided_at: string;
  sent_to_contractor: boolean;
}

export const clientKeys = {
  all: ['client'] as const,
  options: () => ['client', 'options'] as const,
  assignments: () => ['client', 'assignments'] as const,
  assignment: (id: string) => ['client', 'assignment', id] as const,
  progress: (id: string) => ['client', 'progress', id] as const,
  finalReport: (id: string) => ['client', 'final-report', id] as const,
  receivedRequests: () => ['client', 'received-requests'] as const,
  receivedQuotes: () => ['client', 'received-quotes'] as const,
  receivedQuote: (id: string) => ['client', 'received-quote', id] as const,
};

export function fetchClientOptions(): Promise<ClientOptions> {
  return apiGet('/api/client/options');
}

export function fetchClientAssignments(): Promise<ClientAssignmentList> {
  return apiGet('/api/client/assignments');
}

export function fetchClientAssignment(id: string): Promise<ClientAssignmentDetail> {
  return apiGet(`/api/client/assignments/${id}`);
}

export function requestQuote(input: AssignmentRequestInput): Promise<ClientAssignmentDetail> {
  return apiPost('/api/client/requests', input);
}

export function fetchReceivedRequests(): Promise<{ items: ReceivedRequest[] }> {
  return apiGet('/api/received-requests');
}

export function fetchReceivedQuotes(): Promise<{ items: ReceivedQuoteRow[] }> {
  return apiGet('/api/received-quotes');
}

export function fetchReceivedQuote(id: string): Promise<ReceivedQuoteDetail> {
  return apiGet(`/api/received-quotes/${id}`);
}

export function acceptReceivedQuote(id: string, signerFunction: string | null): Promise<Decision> {
  return apiPost(`/api/received-quotes/${id}/acceptance`, { signer_function: signerFunction });
}

export function rejectReceivedQuote(id: string, reason: string | null): Promise<Decision> {
  return apiPost(`/api/received-quotes/${id}/rejection`, { reason });
}

export function fetchProgress(id: string): Promise<Progress> {
  return apiGet(`/api/client/assignments/${id}/progress`);
}

/** The explicit request for the spending; never called without a click. */
export function requestBudgetUsage(id: string, year: number | null): Promise<BudgetUsage> {
  return apiPost(`/api/client/assignments/${id}/budget-usage`, { year });
}

export function fetchFinalReport(id: string): Promise<FinalReport> {
  return apiGet(`/api/client/assignments/${id}/final-report`);
}
