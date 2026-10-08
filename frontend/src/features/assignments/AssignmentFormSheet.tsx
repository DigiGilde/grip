import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import {
  assignmentKeys,
  createAssignment,
  createOrganisation,
  fetchOrganisations,
  updateAssignment,
  type AssignmentDetail,
  type AssignmentInput,
} from './api';
import { KIND_LABELS, TRAFFIC_FORM_LABELS } from './labels';
import { centsToInput, parseEuroToCents } from './money';
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

interface FormState {
  name: string;
  kind: string;
  trafficForm: string;
  clientId: string;
  newClient: string;
  clientContact: string;
  startDate: string;
  endDate: string;
  quotedAmount: string;
  notes: string;
}

function initialState(assignment?: AssignmentDetail): FormState {
  return {
    name: assignment?.name ?? '',
    kind: assignment?.kind ?? 'external',
    trafficForm: assignment?.traffic_form ?? 'none',
    clientId: assignment?.client_organisation_id ?? '',
    newClient: '',
    clientContact: assignment?.client_contact ?? '',
    startDate: assignment?.start_date ?? '',
    endDate: assignment?.end_date ?? '',
    quotedAmount: centsToInput(assignment?.quoted_amount_cents),
    notes: assignment?.notes ?? '',
  };
}

const toOptions = (labels: Record<string, string>) =>
  Object.entries(labels).map(([value, label]) => ({ value, label }));

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

  const organisations = useQuery({
    queryKey: assignmentKeys.organisations,
    queryFn: fetchOrganisations,
    enabled: open,
  });
  const mayEditMoney = assignment?.permissions.edit_financial ?? false;

  const save = useMutation({
    mutationFn: async () => {
      let clientId: string | null = form.clientId || null;
      if (form.newClient.trim()) {
        clientId = (await createOrganisation(form.newClient.trim())).id;
      }
      const input: AssignmentInput = {
        name: form.name.trim(),
        kind: form.kind,
        traffic_form: form.trafficForm,
        client_organisation_id: clientId,
        client_contact: form.clientContact.trim() || null,
        start_date: form.startDate || null,
        end_date: form.endDate || null,
        notes: form.notes.trim() || null,
      };
      if (assignment && mayEditMoney) {
        input.quoted_amount_cents = parseEuroToCents(form.quotedAmount);
      }
      return assignment ? updateAssignment(assignment.id, input) : createAssignment(input);
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.all });
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.organisations });
      setProblem(null);
      onSaved(saved);
    },
    onError: (error) => setProblem(errorMessage(error)),
  });

  const submit = () => {
    if (!form.name.trim()) {
      setProblem('Geef de opdracht een naam.');
      return;
    }
    if (form.quotedAmount && mayEditMoney && parseEuroToCents(form.quotedAmount) === null) {
      setProblem('Het offertebedrag is geen geldig bedrag.');
      return;
    }
    save.mutate();
  };

  return (
    <FormSheet
      open={open}
      title={assignment ? `${assignment.name} bewerken` : 'Nieuwe opdracht'}
      submitText="Bewaar"
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
        options={toOptions(KIND_LABELS)}
      />
      <SelectInput
        label="Verkeer met de opdrachtgever"
        value={form.trafficForm}
        onChange={(trafficForm) => set({ trafficForm })}
        options={toOptions(TRAFFIC_FORM_LABELS)}
      />
      <SelectInput
        label="Opdrachtgever"
        optional
        value={form.clientId}
        onChange={(clientId) => set({ clientId })}
        placeholder="Geen opdrachtgever"
        options={(organisations.data ?? []).map((o) => ({ value: o.id, label: o.name }))}
      />
      <TextInput
        label="Nieuwe opdrachtgever"
        hint="Vul in als de opdrachtgever nog niet in de lijst staat."
        optional
        value={form.newClient}
        onChange={(newClient) => set({ newClient })}
      />
      <TextInput
        label="Contactpersoon bij de opdrachtgever"
        optional
        value={form.clientContact}
        onChange={(clientContact) => set({ clientContact })}
      />
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
      {assignment && mayEditMoney && (
        <TextInput
          label="Offertebedrag"
          hint="In euro's. Het afgesproken bedrag; de begroting kan afwijken."
          optional
          keyboard="decimal"
          value={form.quotedAmount}
          onChange={(quotedAmount) => set({ quotedAmount })}
        />
      )}
      <TextInput
        label="Notities"
        optional
        multiline
        value={form.notes}
        onChange={(notes) => set({ notes })}
      />
    </FormSheet>
  );
}
