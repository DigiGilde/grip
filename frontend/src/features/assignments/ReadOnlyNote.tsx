import { Quiet } from '@/ui/layout';
import type { AssignmentDetail } from './api';

interface ReadOnlyNoteProps {
  assignment: AssignmentDetail;
  /** What the reader looks at, as in "Je kunt <what> bekijken": "deze begroting". */
  what: string;
  /** Who else may change it besides the owner: "een manager", "een manager of een planner". */
  others?: string;
}

/**
 * Said once, quietly, where the action would have been: the reader may look
 * and not change, and who can. Without it a missing button reads as "locked".
 */
export function ReadOnlyNote({ assignment, what, others = 'een manager' }: ReadOnlyNoteProps) {
  const owner = assignment.roles.find((holder) => holder.role === 'owner');
  return (
    <Quiet>
      {`Je kunt ${what} bekijken. Wijzigen kan de eigenaar${owner ? ` (${owner.name})` : ''} of ${others}.`}
    </Quiet>
  );
}
