/**
 * How things stood at each moment of an assignment, read from the server.
 * Fields of a data class the reader may not see are absent, not null.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/api/client';
import type { QuoteContent } from '@/features/quotes/api';
import type { Course } from '@/ui/course';

export interface Moment {
  seq: number;
  occurred_at: string;
  fact: string;
  title: string;
  decision: boolean;
  actor_name: string | null;
  actor_kind: 'person' | 'guest' | 'peer' | 'system' | null;
  effective_on?: string | null;
  statement?: string;
  lines?: string[];
  erased: boolean;
}

export interface StandAssignment {
  name: string;
  status: string;
  status_label: string;
  kind: string;
  owner_name: string | null;
  client_name: string | null;
  start_date: string | null;
  end_date: string | null;
  notes: string | null;
  quote_date?: string | null;
  verbal_agreement_note: string | null;
  quoted_amount_cents?: number | null;
}

export interface LaterKnown {
  seq: number;
  title: string;
  statement?: string;
  effective_on?: string;
}

/** A later moment took a text out of this one. Oldest first. */
export interface Restatement {
  /** The moment that took the text out. */
  seq: number;
  occurred_at: string;
  /** Dutch labels of what was taken out. */
  removed: string[];
}

/** A typed text of this moment that may be taken out. Only for who may do that. */
export interface RemovableText {
  key: string;
  label: string;
  text?: string;
  /** What stays as it was made, in sentences. */
  kept: string[];
}

export interface StandBudgetLine {
  id: string;
  description: string;
  kind: string;
  position: number;
  role?: string | null;
  fte?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  rate_category?: string | null;
  amount_cents?: number | null;
  year?: number | null;
  budgeted_cents?: number | null;
  change: 'added' | 'changed' | null;
}

export interface StandBudget {
  lines: StandBudgetLine[];
  removed: string[];
  subtotals_by_year?: Record<string, number>;
  total_budgeted_cents?: number | null;
  previous_total_cents?: number | null;
  pricing_error?: string | null;
}

export interface StandApproval {
  status: string;
  requested_by_name: string | null;
  requested_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  withdrawn_by_name: string | null;
  withdrawn_at: string | null;
  request_note: string | null;
  decision_note: string | null;
  self_approved: boolean;
}

/** Where a signing link stood at this moment; only for who manages the assignment. */
export interface StandInvitation {
  state: string;
  expires_at: string | null;
  opened_at: string | null;
  used_at: string | null;
  withdrawn_at: string | null;
}

export interface StandOffer {
  channel: string;
  recipient: string | null;
  offered_at: string;
  offered_by_name: string | null;
  invitation?: StandInvitation | null;
}

export interface StandAcceptance {
  signer_name: string;
  form: string;
  signed_at: string;
  organisation_name: string | null;
  recorded_by_name: string | null;
}

export interface StandRejection {
  reason: string | null;
  rejected_at: string;
  recorded_by_name: string | null;
}

export interface StandQuote {
  id: string;
  reference: string | null;
  status: string;
  status_label: string;
  changed: boolean;
  total_cents?: number;
  valid_until?: string | null;
  issued_at?: string;
  snapshot_hash?: string;
  document_sha256?: string | null;
  has_document?: boolean;
  approvals?: StandApproval[];
  offers?: StandOffer[];
  acceptance?: StandAcceptance | null;
  rejection?: StandRejection | null;
  content?: QuoteContent;
}

export interface Stand {
  moment: Moment;
  previous_seq: number | null;
  next_seq: number | null;
  assignment: StandAssignment;
  course: Course | null;
  outside: string[];
  /** The same with its values, for who reads them: replaces `outside`. */
  outside_values?: string[];
  later_known: LaterKnown[];
  restated: Restatement[];
  removable_texts?: RemovableText[] | null;
  budget?: StandBudget;
  quotes: StandQuote[];
  incomplete: boolean;
}

/** The search parameter that holds the moment being looked at. */
export const MOMENT_PARAM = 'moment';

/** The moment in the address; nothing for an address without a valid one. */
export function momentOf(params: URLSearchParams): number | null {
  const value = params.get(MOMENT_PARAM);
  return value !== null && /^\d+$/.test(value) ? Number(value) : null;
}

// Not under ['course']: every save anywhere invalidates that key, and what
// stood at a moment does not change by a save. The list of moments does change
// with every fact: a step taken beside it invalidates this key itself.
export const chronicleKeys = {
  moments: (assignmentId: string) => ['chronicle', assignmentId] as const,
  stand: (assignmentId: string, seq: number) => ['chronicle', assignmentId, seq] as const,
};

export function fetchMoments(assignmentId: string): Promise<{ items: Moment[] }> {
  return apiGet(`/api/assignments/${assignmentId}/chronicle`);
}

export function fetchStand(assignmentId: string, seq: number): Promise<Stand> {
  return apiGet(`/api/assignments/${assignmentId}/chronicle/${seq}`);
}

export interface RestatedStand {
  stand: Stand;
  kept: string[];
}

/** Erase a moment and record it again without the chosen texts. */
export function restateMoment(
  assignmentId: string,
  seq: number,
  columns: string[],
): Promise<RestatedStand> {
  return apiPost(`/api/assignments/${assignmentId}/chronicle/${seq}/restate`, { columns });
}

export function useMoments(assignmentId: string) {
  return useQuery({
    queryKey: chronicleKeys.moments(assignmentId),
    queryFn: () => fetchMoments(assignmentId),
    enabled: assignmentId !== '',
  });
}

export function useStand(assignmentId: string, seq: number) {
  return useQuery({
    queryKey: chronicleKeys.stand(assignmentId, seq),
    queryFn: () => fetchStand(assignmentId, seq),
    placeholderData: keepPreviousData,
  });
}
