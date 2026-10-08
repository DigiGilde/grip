import { useQuery } from '@tanstack/react-query';
import { fetchQuoteDetail, fetchQuotes, quoteKeys } from '@/features/quotes/api';
import { approvalKeys, fetchApprovals } from '@/features/quotes/approval';
import { assignmentKeys, fetchBudget, type AssignmentDetail } from './api';
import { standing, type Standing } from './standing';
import { draftKeys, fetchDraft } from '@/features/quotes/draftApi';
import { ownersText } from './steps';

/** Gathers the facts for `standing` from what the reader may fetch. */
export function useStanding(assignment: AssignmentDetail): Standing | null {
  const potential = assignment.phase === 'potential';
  const money = assignment.permissions.read_financial;
  const budget = useQuery({
    queryKey: assignmentKeys.budget(assignment.id),
    queryFn: () => fetchBudget(assignment.id),
    enabled: potential,
    retry: false,
  });
  const quotes = useQuery({
    queryKey: quoteKeys.list(assignment.id),
    queryFn: () => fetchQuotes(assignment.id),
    enabled: potential && money,
    retry: false,
  });
  const inForce = [...(quotes.data?.quotes ?? [])]
    .sort((a, b) => a.issued_at.localeCompare(b.issued_at))
    .at(-1);
  const detail = useQuery({
    queryKey: quoteKeys.detail(inForce?.id ?? ''),
    queryFn: () => fetchQuoteDetail(inForce?.id ?? ''),
    enabled: potential && inForce?.status === 'issued',
    retry: false,
  });
  const approvals = useQuery({
    queryKey: approvalKeys.ofAssignment(assignment.id),
    queryFn: () => fetchApprovals(assignment.id),
    enabled: potential && money,
    retry: false,
  });
  // The step for internal approval exists only for a quote that needs it.
  const approvalOf = (quoteId: string) => {
    const state = approvals.data?.items?.find((item) => item.quote_id === quoteId);
    return state?.approval_required
      ? { approval: state.status, blockedMessage: state.blocked_message ?? null }
      : {};
  };
  // The letter in preparation, for who may read the money of the assignment.
  const draft = useQuery({
    queryKey: draftKeys.draft(assignment.id),
    queryFn: () => fetchDraft(assignment.id),
    enabled: potential && money,
    retry: false,
  });
  // Until the quotes have answered, say nothing rather than a first guess.
  if (potential && money && (quotes.isPending || approvals.isPending)) return null;
  if (inForce?.status === 'issued' && detail.isPending) return null;
  return standing({
    phase: assignment.phase,
    status: assignment.status,
    mayAct: money,
    owners: ownersText(assignment),
    quoteSeen: assignment.pipeline_amount_source === 'quote',
    ...(draft.data?.saved ? { draftProblems: draft.data.problems.length } : {}),
    // Decided on the server from the content of budget and quote.
    ...(quotes.data?.budget_moved === true ? { budgetMoved: true } : {}),
    ...(budget.data ? { budgetLines: budget.data.lines.length } : {}),
    ...(quotes.data
      ? { quotes: quotes.data.quotes.map((quote) => ({ ...quote, ...approvalOf(quote.id) })) }
      : {}),
    ...(detail.data?.offers
      ? {
          offers: detail.data.offers.map((offer) => ({
            channel: offer.channel,
            offered_at: offer.offered_at,
            invitationState: offer.invitation?.state ?? null,
          })),
        }
      : {}),
    today: new Date().toISOString().slice(0, 10),
  });
}
