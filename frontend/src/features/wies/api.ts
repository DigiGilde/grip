/**
 * Proposals from Wies for the persons of this instance. Grip never adds or
 * deactivates someone on its own: the beheerder confirms a selection here.
 */
import { apiGet, apiPost } from '@/api/client';

export type ProposalAction = 'add' | 'deactivate' | 'reactivate' | 'rename';

export interface PersonProposal {
  action: ProposalAction;
  email: string;
  name: string;
  person_id?: string | null;
  /** What grip has now, for a rename. */
  current_name?: string | null;
  reason: string;
  suborganization?: string | null;
  skills?: string[];
}

export interface Reconciliation {
  /** False when the link with Wies is not set up in this instance. */
  configured: boolean;
  fetched_at?: string | null;
  wies_colleagues?: number;
  proposals?: PersonProposal[];
  note?: string | null;
}

export interface AppliedChange {
  action: ProposalAction;
  email: string;
  person_id?: string | null;
  applied: boolean;
  /** Why a confirmed change was not applied. */
  reason?: string | null;
}

export const WIES_KEYS = {
  reconciliation: ['wies', 'reconciliation'] as const,
};

const BASE = '/api/integrations/wies/reconciliation';

export const fetchReconciliation = () => apiGet<Reconciliation>(BASE);

export const confirmChanges = (changes: { action: ProposalAction; email: string }[]) =>
  apiPost<{ applied: AppliedChange[] }>(BASE, { changes }).then((body) => body.applied ?? []);

/** One proposal is one action for one address. */
export const proposalKey = (proposal: { action: string; email: string }) =>
  `${proposal.action}:${proposal.email.toLowerCase()}`;
