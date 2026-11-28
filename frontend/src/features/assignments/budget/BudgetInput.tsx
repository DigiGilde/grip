import { useQuery } from '@tanstack/react-query';
import { fetchQuotes, quoteKeys } from '@/features/quotes/api';
import { WHOLE_PERIOD } from '@/features/overview/years';
import type { ActionBarAction } from '@/ui/ActionBar';
import { Quiet } from '@/ui/layout';
import { assignmentKeys, fetchBudget, type AssignmentDetail, type BudgetLine } from '../api';
import { BudgetEditor } from '../BudgetEditor';
import { ReadOnlyNote } from '../ReadOnlyNote';
import { CsvDownloads } from './MonthlyEffort';

/**
 * For who may change the budget: what a change means while a quote is with
 * the client, and after one was signed. Said before the change, not after.
 */
export function OfferedQuoteNote({ assignmentId }: { assignmentId: string }) {
  const quotes = useQuery({
    queryKey: quoteKeys.list(assignmentId),
    queryFn: () => fetchQuotes(assignmentId),
    retry: false,
  });
  const waiting = [...(quotes.data?.quotes ?? [])]
    .sort((a, b) => a.issued_at.localeCompare(b.issued_at))
    .at(-1);
  // The signed quote is the agreement; the budget is not locked after it,
  // so say what a change means.
  if (waiting?.status === 'accepted') {
    return (
      <Quiet>
        {`De getekende offerte${waiting.reference ? ` (${waiting.reference})` : ''} is de afspraak. ` +
          'Wijzig je de begroting, dan wijkt die af van wat is getekend.'}
      </Quiet>
    );
  }
  if (waiting?.status !== 'issued') return null;
  return (
    <Quiet>
      {`Er ligt een offerte bij de opdrachtgever${waiting.reference ? ` (${waiting.reference})` : ''}. ` +
        'Wijzig je de begroting, dan maak je daarna een nieuwe offerte; de oude vervalt.'}
    </Quiet>
  );
}

interface BudgetInputProps {
  assignment: AssignmentDetail;
  /** Whether the assignment has its period yet. */
  periodKnown: boolean;
  /** Actions of the part that stand in the bar. */
  actions: readonly ActionBarAction[];
  onOpenLine: (line: BudgetLine) => void;
}

/** Until the agreement: the lines to enter, with FTE, scale and amount. */
export function BudgetInput({ assignment, periodKnown, actions, onOpenLine }: BudgetInputProps) {
  const mayRead = assignment.permissions.read_financial;
  const budget = useQuery({
    queryKey: assignmentKeys.budget(assignment.id),
    queryFn: () => fetchBudget(assignment.id),
    enabled: mayRead,
  });
  const hasLines = (budget.data?.lines.length ?? 0) > 0;
  return (
    <>
      {!periodKnown && <Quiet>De looptijd van de opdracht is nog niet ingevuld.</Quiet>}
      {assignment.permissions.edit_financial && <OfferedQuoteNote assignmentId={assignment.id} />}
      {!assignment.permissions.edit_financial && (
        <ReadOnlyNote assignment={assignment} what="deze begroting" />
      )}
      <BudgetEditor assignment={assignment} actions={actions} onOpenLine={onOpenLine} />
      {mayRead && (
        <CsvDownloads
          assignmentId={assignment.id}
          year={WHOLE_PERIOD}
          lines={hasLines}
          months={hasLines && periodKnown}
        />
      )}
    </>
  );
}
