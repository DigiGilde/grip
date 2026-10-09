import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import {
  assignmentKeys,
  createAssignment,
  fetchAssignment,
  updateAssignment,
  type AssignmentDetail,
  type AssignmentInput,
} from './api';
import { assignmentInput, initialState, type FormState } from './assignmentForm';
import { KIND_LABELS } from './labels';
import { OrganisationPicker } from '@/features/organisations';
import { DateInput, FormSheet, SelectInput, TextInput } from './ui';
import { ConflictPanel } from '@/ui/ConflictPanel';
import { useStaleRecord } from '@/ui/stale';

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
  // The version this form started from; a save on an older one is refused
  // and the form then shows what stands there now.
  const [onTopOf, setOnTopOf] = useState(assignment?.version);
  const stale = useStaleRecord<AssignmentDetail>(async () =>
    assignment ? fetchAssignment(assignment.id) : null,
  );
  if (seenSession !== session) {
    setSeenSession(session);
    setForm(initialState(assignment));
    setOnTopOf(assignment?.version);
    stale.clear();
    setProblem(null);
  }
  // A message about a field goes once the reader changes something.
  const set = (patch: Partial<FormState>) => {
    setProblem(null);
    setForm((current) => ({ ...current, ...patch }));
  };
  const creating = !assignment;
  const external = form.kind === 'external';

  const save = useMutation({
    mutationFn: ({ input, version }: { input: AssignmentInput; version?: number }) =>
      assignment ? updateAssignment(assignment.id, input, version) : createAssignment(input),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.all });
      setProblem(null);
      stale.clear();
      onSaved(saved);
    },
    onError: async (error) => {
      if (await stale.caught(error)) {
        setProblem(null);
        return;
      }
      setProblem(errorMessage(error));
    },
  });

  const submit = (version: number | undefined = onTopOf) => {
    const input = assignmentInput(form, creating);
    if (typeof input === 'string') {
      setProblem(input);
      return;
    }
    setOnTopOf(version);
    save.mutate({ input, version });
  };

  const describe = (values: FormState) => [
    { label: 'Naam', value: values.name },
    { label: 'Soort', value: KIND_LABELS[values.kind] ?? values.kind },
    { label: 'Contactpersoon', value: values.clientContact },
    { label: 'Begindatum', value: values.startDate },
    { label: 'Einddatum', value: values.endDate },
    { label: 'Notities', value: values.notes },
  ];

  return (
    <FormSheet
      open={open}
      title={assignment ? `${assignment.name} bewerken` : 'Nieuwe opdracht'}
      submitText={creating ? 'Maak opdracht' : 'Bewaar'}
      onSubmit={() => submit()}
      onClose={onClose}
      busy={save.isPending}
      error={problem}
    >
      {stale.theirs ? (
        <ConflictPanel
          conflict={stale.theirs.conflict}
          theirs={describe(initialState(stale.theirs.record))}
          mine={describe(form)}
          onKeepMine={() => submit(stale.theirs?.record.version)}
          onTakeTheirs={() => {
            if (!stale.theirs) return;
            setForm(initialState(stale.theirs.record));
            setOnTopOf(stale.theirs.record.version);
            stale.clear();
          }}
          busy={save.isPending}
        />
      ) : null}
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
      <DateInput
        label="Begindatum"
        optional
        value={form.startDate}
        onChange={(startDate) => set({ startDate })}
      />
      <DateInput
        label="Einddatum"
        optional
        hint="Begrotingsregels en inzet volgen de looptijd van de opdracht."
        value={form.endDate}
        onChange={(endDate) => set({ endDate })}
      />
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
