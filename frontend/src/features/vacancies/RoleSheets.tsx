import { useState } from 'react';
import { formatFte } from '@/lib/format';
import { FormSheet } from '@/ui/layout';
import {
  submitVacancy,
  updateVacancy,
  type Vacancy,
  type VacancyOptions,
  type VacancyType,
} from './api';
import { parseFte, todayIso, useVacancyChange } from './hooks';
import { missingRequestDetails } from './labels';
import { DateInput, Note, SelectInput, TextInput } from './ui';

interface EditSheetProps {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
  open: boolean;
  onClose: () => void;
}

export function EditSheet({ vacancy, options, open, onClose }: EditSheetProps) {
  const [title, setTitle] = useState(vacancy.function_title);
  const [fte, setFte] = useState(formatFte(vacancy.fte));
  const [start, setStart] = useState(vacancy.start_date ?? '');
  const [end, setEnd] = useState(vacancy.end_date ?? '');
  const [vacancyType, setVacancyType] = useState<string>(vacancy.vacancy_type ?? 'regulier');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useVacancyChange(
    vacancy.id,
    (body: Parameters<typeof updateVacancy>[1]) => updateVacancy(vacancy.id, body),
    onClose,
  );

  function submit() {
    setProblem(null);
    const fteValue = parseFte(fte);
    if (!title.trim()) return setProblem('Vul de functie in.');
    if (fteValue === null) {
      return setProblem('Het aantal fte is een getal groter dan nul, bijvoorbeeld 0,8.');
    }
    change.run({
      function_title: title.trim(),
      fte: fteValue,
      start_date: start || null,
      end_date: end || null,
      vacancy_type: vacancyType as VacancyType,
    });
  }

  return (
    <FormSheet
      open={open}
      title={`Vacature ${vacancy.function_title} bewerken`}
      submitText="Bewaar"
      onSubmit={submit}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      <TextInput label="Functie" value={title} onChange={setTitle} required />
      <TextInput label="Aantal fte" value={fte} onChange={setFte} keyboard="decimal" required />
      <DateInput label="Begindatum" value={start} onChange={setStart} optional />
      <DateInput label="Einddatum" value={end} onChange={setEnd} optional />
      <SelectInput
        label="Type vacature"
        value={vacancyType}
        onChange={setVacancyType}
        hint="Bepaalt de procedure: een vacature voor een beoogde of gerede kandidaat wordt niet opengesteld."
        options={options?.vacancy_types ?? []}
      />
    </FormSheet>
  );
}

export function SubmitSheet({
  vacancy,
  open,
  onClose,
}: {
  vacancy: Vacancy;
  open: boolean;
  onClose: () => void;
}) {
  const [day, setDay] = useState(todayIso());
  const missing = missingRequestDetails(vacancy);
  const change = useVacancyChange(
    vacancy.id,
    (requestedOn: string) => submitVacancy(vacancy.id, requestedOn),
    onClose,
  );
  return (
    <FormSheet
      open={open}
      title={`Vacature ${vacancy.function_title} aanvragen`}
      submitText="Vraag aan"
      onSubmit={() => change.run(day)}
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      {missing.length > 0 && (
        <Note>
          Het aanvraagformulier vraagt ook nog: {missing.join(', ')}. Je kunt nu aanvragen en dat
          tot het akkoord aanvullen.
        </Note>
      )}
      <DateInput label="Datum van de aanvraag" value={day} onChange={setDay} required />
    </FormSheet>
  );
}
