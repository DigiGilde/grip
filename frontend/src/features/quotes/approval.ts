/**
 * Internal approval of a quote: where it stands and what the reader may do.
 * Optional per organisation; a quote that does not need it has
 * `approval_required` false and nothing of this shows.
 */
import { apiGet, apiPatch, apiPost } from '@/api/client';
import { PATHS } from '@/paths';
import type { QuoteContent } from './api';
import { formatDateTime } from './format';

export type ApprovalStatus = 'none' | 'requested' | 'approved' | 'sent_back' | 'withdrawn';

export interface ApprovalRequest {
  id: string;
  status: ApprovalStatus | string;
  requested_at: string;
  requested_by_name?: string | null;
  request_note?: string | null;
  decided_at?: string | null;
  decided_by_name?: string | null;
  decision_note?: string | null;
  self_approved?: boolean;
  for_this_version?: boolean;
}

export interface ApprovalState {
  quote_id: string;
  approval_required: boolean;
  /** Why, in words: "vanaf € 100.000". */
  approval_reason?: string | null;
  status: ApprovalStatus | string;
  may_offer: boolean;
  blocked_message?: string | null;
  approver_available: boolean;
  may_request_approval?: boolean;
  may_decide_approval?: boolean;
  may_withdraw?: boolean;
  current?: ApprovalRequest | null;
  history?: ApprovalRequest[];
}

export interface WaitingApproval {
  quote_id: string;
  quote_reference?: string | null;
  assignment_id: string;
  assignment_name: string;
  client_name?: string | null;
  requested_at: string;
  requested_by_name?: string | null;
  request_note?: string | null;
  total_cents?: number;
  may_decide?: boolean;
}

export interface ApproverQuote {
  quote_id: string;
  quote_reference?: string | null;
  assignment_id: string;
  assignment_name: string;
  client_name?: string | null;
  issued_at: string;
  issued_by_name?: string | null;
  total_cents?: number;
  snapshot_hash?: string;
  content?: QuoteContent | null;
  approval: ApprovalState;
}

export interface InstanceSetting {
  key: string;
  value: unknown;
  default: unknown;
  label: string;
}

export const SETTING_MODE = 'quote_approval.mode';
export const SETTING_THRESHOLD = 'quote_approval.threshold_cents';
export const SETTING_ALLOW_SELF = 'quote_approval.allow_self_approval';
export const SETTING_REFERENCE_PREFIX = 'quote.reference_prefix';

export const APPROVAL_MODE_LABELS: Record<string, string> = {
  never: 'Nooit',
  always: 'Altijd',
  from_amount: 'Vanaf een bedrag',
};

/** The right that lets someone approve, as the screens of Team name it. */
export const APPROVER_RIGHT = 'Interne goedkeurder van offertes';

// Under 'quotes', so a change to a quote refreshes its approval too.
export const approvalKeys = {
  ofAssignment: (assignmentId: string) => ['quotes', 'approvals', assignmentId] as const,
  waiting: ['quotes', 'approvals-waiting'] as const,
  approverQuote: (quoteId: string) => ['quotes', 'approver-quote', quoteId] as const,
  settings: ['instance-settings'] as const,
};

export function fetchApprovals(assignmentId: string): Promise<{ items?: ApprovalState[] }> {
  return apiGet(`/api/assignments/${assignmentId}/quote-approvals`);
}

export function requestApproval(quoteId: string, note: string | null): Promise<ApprovalState> {
  return apiPost(`/api/quotes/${quoteId}/approval/request`, { note });
}

export function decideApproval(
  quoteId: string,
  input: { decision: 'approve' | 'send_back'; quote_hash: string; note: string | null },
): Promise<ApprovalState> {
  return apiPost(`/api/quotes/${quoteId}/approval/decision`, input);
}

export function withdrawApproval(quoteId: string): Promise<ApprovalState> {
  return apiPost(`/api/quotes/${quoteId}/approval/withdrawal`);
}

export function fetchWaitingApprovals(): Promise<{ items?: WaitingApproval[] }> {
  return apiGet('/api/quote-approvals/waiting');
}

export function fetchApproverQuote(quoteId: string): Promise<ApproverQuote> {
  return apiGet(`/api/quote-approvals/quotes/${quoteId}`);
}

export function approverDocumentUrl(quoteId: string, download = false): string {
  return `/api/quote-approvals/quotes/${quoteId}/document${download ? '?download=true' : ''}`;
}

export function fetchInstanceSettings(): Promise<{ items: InstanceSetting[] }> {
  return apiGet('/api/instance-settings');
}

export function saveInstanceSettings(
  values: Record<string, unknown>,
): Promise<{ items: InstanceSetting[] }> {
  return apiPatch('/api/instance-settings', { values });
}

/** Where someone with the right decides on one quote. */
export function approvalPath(quoteId: string): string {
  return PATHS.quoteApproval.replace(':quoteId', quoteId);
}

/** Whether the step "Interne goedkeuring" still stands between making and offering. */
export function awaitsApproval(approval: ApprovalState | null | undefined): boolean {
  return Boolean(approval?.approval_required && !approval.may_offer);
}

/** Where the approval stands, in one sentence; null when there is nothing to say. */
export function approvalLine(approval: ApprovalState | null | undefined): string | null {
  if (!approval?.approval_required) return null;
  const current = approval.current;
  const by = (name: string | null | undefined) => (name ? ` door ${name}` : '');
  switch (approval.status) {
    case 'requested':
      return `Wacht op goedkeuring sinds ${formatDateTime(current?.requested_at)}${
        current?.requested_by_name ? `, gevraagd door ${current.requested_by_name}` : ''
      }.`;
    case 'approved':
      return `Intern goedgekeurd op ${formatDateTime(current?.decided_at)}${by(current?.decided_by_name)}.`;
    case 'sent_back':
      return `Teruggestuurd op ${formatDateTime(current?.decided_at)}${by(current?.decided_by_name)}${
        current?.decision_note ? `: ${current.decision_note}` : '.'
      }`;
    default:
      return `Deze offerte heeft interne goedkeuring nodig${
        approval.approval_reason ? ` (${approval.approval_reason})` : ''
      } voor je haar aanbiedt.`;
  }
}
