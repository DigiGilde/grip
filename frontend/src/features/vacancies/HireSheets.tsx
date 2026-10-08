import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { assignmentKeys, fetchPersonOptions } from '@/features/assignments/api';
import { FormSheet } from '@/ui/layout';
import {
  DEFAULT_RECRUITMENT_SYSTEM,
  VACANCY_KEYS,
  hireKey,
  recordHire,
  setRecruitmentRef,
  withdrawHire,
  withdrawVacancy,
  type HireInput,
  type RecruitmentRef,
  type Vacancy,
  type VacancyHire,
} from './api';
import { todayIso, useVacancyChange } from './hooks';
import { Button, CheckboxInput, DateInput, SelectInput, TextInput } from './ui';

/** Choice in the person picker for someone grip does not know yet. */
const NEW_COLLEAGUE = 'new';

/** A change to the recruitment reference or the hire; refreshes the vacancy too. */
function useHireChange<Input>(
  vacancyId: string,
  change: (input: Input) => Promise<VacancyHire>,
  onDone: () => void,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: change,
    onSuccess: (result) => {
      // The answer to a hire carries the proposed inzet, which a later read
      // does not; keep it for the page.
      queryClient.setQueryData(hireKey(vacancyId), result);
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.detail(vacancyId) });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.list });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.openRoles });
      onDone();
    },
  });
  return {
    run: mutation.mutate,
    busy: mutation.isPending,
    error: mutation.isError ? errorMessage(mutation.error) : null,
  };
}

interface SheetProps {
  vacancy: Vacancy;
  open: boolean;
  onClose: () => void;
}

/** Who was hired and from when: the vacancy is filled and the person planned. */
export function HireSheet({ vacancy, open, onClose }: SheetProps) {
  const people = useQuery({
    queryKey: assignmentKeys.personOptions,
    queryFn: fetchPersonOptions,
    enabled: open,
  });
  const known = people.data ?? [];
  // A vacancy for a known candidate proposes that person, so the name is entered once.
  const [personId, setPersonId] = useState(vacancy.candidate_person_id ?? NEW_COLLEAGUE);
  const [name, setName] = useState('');
  const [start, setStart] = useState(vacancy.start_date ?? todayIso());
  const [plan, setPlan] = useState(true);
  const [problem, setProblem] = useState<string | null>(null);
  const change = useHireChange(
    vacancy.id,
    (body: HireInput) => recordHire(vacancy.id, body),
    onClose,
  );
  const isNew = personId === NEW_COLLEAGUE;
  const onBudgetLine = Boolean(vacancy.budget_line_id);

  function submit() {
    setProblem(null);
    if (isNew && !name.trim()) return setProblem('Vul de naam van de nieuwe collega in.');
    if (!start) return setProblem('Vul in vanaf wanneer de collega begint.');
    change.run({
      start_date: start,
      ...(isNew ? { name: name.trim() } : { person_id: personId }),
      create_allocation: onBudgetLine && plan,
    });
  }

  return (
    <FormSheet
      open={open}
      title={`Vacature ${vacancy.function_title} vervullen`}
      submitText="Vervul"
      onSubmit={submit}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      {known.length > 0 && (
        <SelectInput
          label="Wie is aangenomen"
          value={personId}
          onChange={setPersonId}
          options={[
            { value: NEW_COLLEAGUE, label: 'Een nieuwe collega' },
            ...known.map((person) => ({ value: person.id, label: person.name })),
          ]}
        />
      )}
      {isNew && (
        <TextInput label="Naam van de nieuwe collega" value={name} onChange={setName} required />
      )}
      <DateInput label="Start op" value={start} onChange={setStart} required />
      {onBudgetLine && (
        <CheckboxInput
          label="Plan de inzet meteen op de begrotingsregel"
          checked={plan}
          onChange={setPlan}
        />
      )}
    </FormSheet>
  );
}

/** Where this vacancy lives in the recruitment system. */
export function RecruitmentRefSheet({
  vacancy,
  current,
  open,
  onClose,
}: SheetProps & { current: RecruitmentRef | null | undefined }) {
  const [system, setSystem] = useState(current?.system ?? DEFAULT_RECRUITMENT_SYSTEM);
  const [reference, setReference] = useState(current?.reference ?? '');
  const [url, setUrl] = useState(current?.url ?? '');
  const change = useHireChange(
    vacancy.id,
    (body: { reference: string; url: string | null; system: string | null }) =>
      setRecruitmentRef(vacancy.id, body),
    onClose,
  );
  return (
    <FormSheet
      open={open}
      title="Verwijzing naar het wervingssysteem"
      submitText="Bewaar"
      onSubmit={() =>
        change.run({
          reference: reference.trim(),
          url: url.trim() || null,
          system: system.trim() || null,
        })
      }
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      <TextInput label="Systeem" value={system} onChange={setSystem} />
      <TextInput
        label="Kenmerk van de vacature"
        value={reference}
        onChange={setReference}
        optional
      />
      <TextInput
        label="Link in het wervingssysteem"
        hint="Voor recruiters. Het adres dat iedereen kan openen leg je vast bij Tekst."
        value={url}
        onChange={setUrl}
        keyboard="url"
        optional
      />
    </FormSheet>
  );
}

/** Takes the reference to the recruitment system away again. */
export function RemoveRecruitmentRef({ vacancy }: { vacancy: Vacancy }) {
  const change = useHireChange(
    vacancy.id,
    () => setRecruitmentRef(vacancy.id, { reference: '', url: null, system: null }),
    () => undefined,
  );
  return (
    <Button
      text="Verwijder de verwijzing"
      loading={change.busy}
      onClick={() => change.run(undefined)}
    />
  );
}

/** The hire does not go through after all. */
export function WithdrawHireSheet({ vacancy, open, onClose }: SheetProps) {
  const [reason, setReason] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useHireChange(
    vacancy.id,
    (text: string) => withdrawHire(vacancy.id, text),
    onClose,
  );
  return (
    <FormSheet
      open={open}
      title="Aanname gaat niet door"
      submitText="Trek aanname in"
      onSubmit={() => {
        setProblem(null);
        if (!reason.trim()) return setProblem('Vul in waarom de aanname niet doorgaat.');
        change.run(reason.trim());
      }}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      <TextInput label="Reden" value={reason} onChange={setReason} multiline required />
    </FormSheet>
  );
}

/** The vacancy lapses without being filled. */
export function WithdrawVacancySheet({ vacancy, open, onClose }: SheetProps) {
  const [note, setNote] = useState('');
  const change = useVacancyChange(
    vacancy.id,
    (text: string) => withdrawVacancy(vacancy.id, text || undefined),
    onClose,
  );
  return (
    <FormSheet
      open={open}
      title={`Vacature ${vacancy.function_title} intrekken`}
      submitText="Trek in"
      onSubmit={() => change.run(note.trim())}
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      <TextInput label="Reden" value={note} onChange={setNote} multiline optional />
    </FormSheet>
  );
}
