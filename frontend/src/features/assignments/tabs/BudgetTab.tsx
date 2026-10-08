import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { errorMessage } from '@/api/client';
import { formatPeriod } from '@/lib/format';
import { Facts, FormSheet, Stack } from '@/ui/layout';
import { assignmentKeys, updateAssignment, type AssignmentDetail } from '../api';
import { BudgetEditor } from '../BudgetEditor';
import { useAssignmentShell } from '../shell';
import { Button, DateInput } from '../ui';

/** The period of the assignment: every budget line follows it unless it deviates. */
function AssignmentPeriod({ assignment }: { assignment: AssignmentDetail }) {
  const queryClient = useQueryClient();
  const [sheet, setSheet] = useState({ open: false, session: 0 });
  const [start, setStart] = useState(assignment.start_date ?? '');
  const [end, setEnd] = useState(assignment.end_date ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => updateAssignment(assignment.id, { start_date: start, end_date: end }),
    onSuccess: (saved) => {
      queryClient.setQueryData(assignmentKeys.detail(assignment.id), saved);
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.budget(assignment.id) });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
      setSheet((current) => ({ ...current, open: false }));
    },
    onError: (error) => setProblem(errorMessage(error)),
  });
  const known = Boolean(assignment.start_date && assignment.end_date);
  const open = () => {
    setStart(assignment.start_date ?? '');
    setEnd(assignment.end_date ?? '');
    setProblem(null);
    setSheet((current) => ({ open: true, session: current.session + 1 }));
  };
  return (
    <>
      <Facts
        label="Looptijd van de opdracht"
        facts={[
          {
            label: 'Looptijd van de opdracht',
            value: known
              ? formatPeriod(assignment.start_date, assignment.end_date)
              : 'Nog niet ingevuld. Regels zonder eigen periode worden pas berekend als de looptijd er is.',
          },
        ]}
      />
      {assignment.permissions.edit_basic && (
        <nldd-container layout="row">
          <Button text={known ? 'Wijzig de looptijd' : 'Vul de looptijd in'} onClick={open} />
        </nldd-container>
      )}
      <FormSheet
        open={sheet.open}
        title="Looptijd van de opdracht"
        submitText="Bewaar"
        busy={save.isPending}
        error={problem}
        onClose={() => setSheet((current) => ({ ...current, open: false }))}
        onSubmit={() => {
          if (!start || !end) setProblem('Vul de begin- en einddatum in.');
          else if (end < start) setProblem('De einddatum ligt voor de begindatum.');
          else save.mutate();
        }}
      >
        <DateInput label="Begindatum" value={start} onChange={setStart} required />
        <DateInput label="Einddatum" value={end} onChange={setEnd} required />
      </FormSheet>
    </>
  );
}

/** The budget lines of the assignment and their computed amounts. */
export function BudgetTab() {
  const assignment = useAssignmentShell();
  if (!assignment) return null;
  return (
    <nldd-simple-section>
      <Stack gap="group">
        <Stack gap="close">
          <AssignmentPeriod assignment={assignment} />
        </Stack>
        <BudgetEditor assignmentId={assignment.id} />
      </Stack>
    </nldd-simple-section>
  );
}
