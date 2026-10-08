import { BudgetEditor } from '../BudgetEditor';
import { useAssignmentShell } from '../shell';

/** The budget lines of the assignment and their computed amounts. */
export function BudgetTab() {
  const assignment = useAssignmentShell();
  if (!assignment) return null;
  return (
    <nldd-simple-section>
      <BudgetEditor assignmentId={assignment.id} />
    </nldd-simple-section>
  );
}
