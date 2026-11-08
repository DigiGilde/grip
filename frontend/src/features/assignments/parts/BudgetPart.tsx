import { useState } from 'react';
import { Button } from '@/ui/Button';
import type { AssignmentDetail, BudgetLine } from '../api';
import { AssignmentPartPage } from '../AssignmentPartPage';
import { useAssignmentPeriod } from '../budget/AssignmentPeriod';
import { BudgetInput, OfferedQuoteNote } from '../budget/BudgetInput';
import { BudgetSheet } from '../budget/BudgetSheet';
import { LineSheet } from '../BudgetEditor';
import { useAssignmentShell } from '../shell';

function Budget({ assignment }: { assignment: AssignmentDetail }) {
  const period = useAssignmentPeriod({ assignment });
  const [sheet, setSheet] = useState<{ open: boolean; line?: BudgetLine; key: number }>({
    open: false,
    key: 0,
  });
  const openSheet = (line?: BudgetLine) =>
    setSheet((current) => ({ open: true, line, key: current.key + 1 }));
  const mayEdit = assignment.permissions.edit_financial;
  const agreed = assignment.phase !== 'potential';

  return (
    <AssignmentPartPage
      part="budget"
      kind="worksheet"
      action={
        mayEdit ? (
          <Button appearance="primary" text="Nieuwe begrotingsregel" onClick={() => openSheet()} />
        ) : undefined
      }
    >
      {agreed ? (
        <BudgetSheet assignment={assignment} actions={period.action} onOpenLine={openSheet} />
      ) : (
        <BudgetInput
          assignment={assignment}
          periodKnown={period.known}
          actions={period.action}
          onOpenLine={openSheet}
        />
      )}
      {mayEdit && (
        <LineSheet
          session={sheet.key}
          assignmentId={assignment.id}
          line={sheet.line}
          assignment={assignment}
          open={sheet.open}
          onClose={() => setSheet((current) => ({ ...current, open: false }))}
          note={agreed && sheet.key > 0 ? <OfferedQuoteNote assignmentId={assignment.id} /> : null}
        />
      )}
      {period.sheet}
    </AssignmentPartPage>
  );
}

/** Until the agreement the lines to enter, after it how the budget stands. */
export function BudgetPart() {
  const assignment = useAssignmentShell();
  if (!assignment) return null;
  return <Budget assignment={assignment} />;
}
