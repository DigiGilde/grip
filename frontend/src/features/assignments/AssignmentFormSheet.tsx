import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import {
  assignmentKeys,
  createAssignment,
  updateAssignment,
  type AssignmentDetail,
  type AssignmentInput,
} from './api';
import { assignmentInput, initialState, type FormState } from './assignmentForm';
import { KIND_LABELS } from './labels';
import { OrganisationPicker } from '@/features/organisations';
import { DateInput, FormSheet, SelectInput, TextInput } from './ui';

interface Props {
  open: boolean;
  /** Changes each time the sheet is opened, so the form starts fresh. */
  session: number;
  /** The assignment to edit; omit to create one. */
  assignment?: AssignmentDetail;
  onClose: () => void;
  onSaved: (assignment: AssignmentDetail) => void;
}

const KIND_OPTIONS = Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }));

/**
 * Creating is quick: a name, internal or external, and for an external
 * assignment the client. Everything else (contact, period, notes) can be
 * added later from the overview tab, where this same sheet edits it.
 */
export function AssignmentFormSheet({ open, session, assignment, onClose, onSaved }: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => initialState(assignment));
  const [problem, setProblem] = useState<string | null>(null);
  // The sheet stays mounted while closed, so a new opening resets the form
  // here instead of by remounting.
  const [seenSession, setSeenSession] = useState(session);
  if (seenSession !== session) {
    setSeenSession(session);
    setForm(initialState(assignment));
    setProblem(null);
  }
  const set = (patch: Partial<FormState>) => setForm((current) => ({ ...current, ...patch }));
  const creating = !assignment;
  const external = form.kind === 'external';

  const save = useMutation({
    mutationFn: (input: AssignmentInput) =>
      assignment ? updateAssignment(assignment.id, input) : createAssignment(input),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.all });
      setProblem(null);
      onSaved(saved);
    },
    onError: (error) => setProblem(errorMessage(error)),
  });

  const submit = () => {
    const input = assignmentInput(form, creating);
    if (typeof input === 'string') {
      setProblem(input);
      return;
    }
    save.mutate(input);
  };

  return (
    <FormSheet
      open={open}
      title={assignment ? `${assignment.name} bewerken` : 'Nieuwe opdracht'}
      submitText={creating ? 'Maak opdracht' : 'Bewaar'}
      onSubmit={submit}
      onClose={onClose}
      busy={save.isPending}
      error={problem}
    >
      <TextInput label="Naam" value={form.name} onChange={(name) => set({ name })} required />
      <SelectInput
        label="Soort"
        value={form.kind}
        onChange={(kind) => set({ kind })}
        options={KIND_OPTIONS}
      />
      {external && (
        <OrganisationPicker
          label="Opdrachtgever"
          supportingLabel="Kan ook later worden gekozen."
          optional
          value={form.clientId || null}
          onChange={(organisation) => set({ clientId: organisation?.id ?? '' })}
        />
      )}
      {!creating && (
        <>
          {external && (
            <TextInput
              label="Contactpersoon bij de opdrachtgever"
              optional
              value={form.clientContact}
              onChange={(clientContact) => set({ clientContact })}
            />
          )}
          <DateInput
            label="Begindatum"
            optional
            value={form.startDate}
            onChange={(startDate) => set({ startDate })}
          />
          <DateInput
            label="Einddatum"
            optional
            value={form.endDate}
            onChange={(endDate) => set({ endDate })}
          />
          <TextInput
            label="Notities"
            optional
            multiline
            value={form.notes}
            onChange={(notes) => set({ notes })}
          />
        </>
      )}
    </FormSheet>
  );
}
