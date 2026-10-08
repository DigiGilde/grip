import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { assignmentPath } from '@/features/assignments/paths';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatFte, formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import {
  VACANCY_KEYS,
  fetchVacancy,
  submitVacancy,
  updateVacancy,
  type ContractType,
  type Vacancy,
  type VacancyOptions,
  type VacancyType,
} from './api';
import { ClosingSection } from './ClosingSection';
import { DecisionsSection } from './DecisionsSection';
import { parseFte, parseScale, todayIso, useVacancyChange, useVacancyOptions } from './hooks';
import {
  CONTRACT_TYPE_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
  VACANCY_TYPE_LABELS,
  publishedOrigin,
} from './labels';
import { ProcedureSection } from './ProcedureSection';
import { RequestFormSection } from './RequestFormSection';
import { TextsSection } from './TextsSection';
import {
  Button,
  DateInput,
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  LinkButton,
  Loading,
  Note,
  Paragraphs,
  SectionHeading,
  SelectInput,
  TextInput,
} from './ui';

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <nldd-list-item>
      <nldd-text-cell overline={label} text={value} />
    </nldd-list-item>
  );
}

function Facts({ vacancy }: { vacancy: Vacancy }) {
  return (
    <RouterLinks>
      <nldd-list appearance="box-base" accessible-label="Gegevens van de vacature">
        <Fact label="Functie" value={vacancy.function_title} />
        <Fact label="FGR-functienaam" value={vacancy.fgr_function_name} />
        <Fact
          label="Schaal"
          value={
            vacancy.scale === null || vacancy.scale === undefined ? null : String(vacancy.scale)
          }
        />
        <Fact label="Aantal fte" value={formatFte(vacancy.fte)} />
        <Fact label="Periode" value={formatPeriod(vacancy.start_date, vacancy.end_date)} />
        {vacancy.assignment_id && vacancy.assignment_name ? (
          <nldd-list-item href={assignmentPath(vacancy.assignment_id)}>
            <nldd-text-cell overline="Opdracht" text={vacancy.assignment_name} />
          </nldd-list-item>
        ) : (
          <Fact label="Opdracht" value={vacancy.assignment_name} />
        )}
        {vacancy.declarable !== undefined && (
          <Fact label="Declarabel" value={vacancy.declarable ? 'Ja' : 'Nee'} />
        )}
        <Fact
          label="Type vacature"
          value={vacancy.vacancy_type ? VACANCY_TYPE_LABELS[vacancy.vacancy_type] : null}
        />
        <Fact
          label="Type contract"
          value={vacancy.contract_type ? CONTRACT_TYPE_LABELS[vacancy.contract_type] : null}
        />
        <Fact label="Aangevraagd door" value={vacancy.requester_name} />
        <Fact label="Aan" value={vacancy.addressee_name} />
        <Fact label="Aangevraagd op" value={formatDate(vacancy.requested_on)} />
      </nldd-list>
    </RouterLinks>
  );
}

interface EditSheetProps {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
  open: boolean;
  onClose: () => void;
}

function EditSheet({ vacancy, options, open, onClose }: EditSheetProps) {
  const [title, setTitle] = useState(vacancy.function_title);
  const [fte, setFte] = useState(formatFte(vacancy.fte));
  const [start, setStart] = useState(vacancy.start_date ?? '');
  const [end, setEnd] = useState(vacancy.end_date ?? '');
  const [vacancyType, setVacancyType] = useState<string>(vacancy.vacancy_type ?? 'regulier');
  const [contractType, setContractType] = useState<string>(vacancy.contract_type ?? '');
  const [fgr, setFgr] = useState(vacancy.fgr_function_name ?? '');
  const [scale, setScale] = useState(
    vacancy.scale === null || vacancy.scale === undefined ? '' : String(vacancy.scale),
  );
  const [addressee, setAddressee] = useState(vacancy.addressee_name ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useVacancyChange(
    vacancy.id,
    (body: Parameters<typeof updateVacancy>[1]) => updateVacancy(vacancy.id, body),
    onClose,
  );

  function submit() {
    setProblem(null);
    const fteValue = parseFte(fte);
    const scaleValue = parseScale(scale);
    if (!title.trim()) return setProblem('Vul de functie in.');
    if (fteValue === null) {
      return setProblem('Het aantal fte is een getal groter dan nul, bijvoorbeeld 0,8.');
    }
    if (scaleValue === undefined) {
      return setProblem('De schaal is een heel getal van 1 tot en met 19.');
    }
    change.run({
      function_title: title.trim(),
      fte: fteValue,
      start_date: start || null,
      end_date: end || null,
      vacancy_type: vacancyType as VacancyType,
      contract_type: (contractType || null) as ContractType | null,
      fgr_function_name: fgr.trim() || null,
      scale: scaleValue,
      addressee_name: addressee.trim() || null,
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
        options={options?.vacancy_types ?? []}
      />
      <SelectInput
        label="Type contract"
        value={contractType}
        onChange={setContractType}
        options={options?.contract_types ?? []}
        placeholder="Nog niet bekend"
        optional
      />
      <TextInput label="FGR-functienaam" value={fgr} onChange={setFgr} optional />
      <TextInput label="Schaal" value={scale} onChange={setScale} keyboard="numeric" optional />
      <TextInput
        label="Aan"
        hint="Wie akkoord moet geven op de aanvraag."
        value={addressee}
        onChange={setAddressee}
        optional
      />
    </FormSheet>
  );
}

function SubmitSheet({
  vacancy,
  open,
  onClose,
}: {
  vacancy: Vacancy;
  open: boolean;
  onClose: () => void;
}) {
  const [day, setDay] = useState(todayIso());
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
      <Note>
        Met de aanvraag vraag je akkoord om de vacature open te stellen. Daarna kunnen het advies
        van HR en concern control en het akkoord worden vastgelegd.
      </Note>
      <DateInput label="Datum van de aanvraag" value={day} onChange={setDay} required />
    </FormSheet>
  );
}

/** What everyone sees of a published vacancy: the facts and the established text. */
function PublicView({ vacancy }: { vacancy: Vacancy }) {
  return (
    <>
      <Facts vacancy={vacancy} />
      {vacancy.published_text && (
        <>
          <nldd-spacer size="24" />
          <SectionHeading text="Vacaturetekst" />
          <Paragraphs text={vacancy.published_text.body} />
          <nldd-spacer size="8" />
          <Note>{publishedOrigin(vacancy.published_text)}</Note>
        </>
      )}
    </>
  );
}

function Details({ vacancy, options }: { vacancy: Vacancy; options: VacancyOptions | undefined }) {
  const [sheet, setSheet] = useState<'edit' | 'submit' | null>(null);
  const editable = vacancy.permissions.can_edit && ['draft', 'requested'].includes(vacancy.status);
  return (
    <>
      <SectionHeading text="Gegevens" />
      <Facts vacancy={vacancy} />
      {(editable || (vacancy.permissions.can_edit && vacancy.status === 'draft')) && (
        <>
          <nldd-spacer size="8" />
          <nldd-button-group>
            {vacancy.permissions.can_edit && vacancy.status === 'draft' && (
              <Button text="Vraag aan" appearance="primary" onClick={() => setSheet('submit')} />
            )}
            {editable && <Button text="Bewerk gegevens" onClick={() => setSheet('edit')} />}
          </nldd-button-group>
        </>
      )}
      {vacancy.permissions.can_edit && !editable && (
        <Note>Na het akkoord liggen de gegevens van de aanvraag vast.</Note>
      )}
      {vacancy.permissions.can_edit && (
        <>
          <EditSheet
            // A fresh form per saved state, so the fields show what was saved.
            key={`${vacancy.id}-${vacancy.status}-${vacancy.function_title}-${vacancy.fte}`}
            vacancy={vacancy}
            options={options}
            open={sheet === 'edit'}
            onClose={() => setSheet(null)}
          />
          <SubmitSheet vacancy={vacancy} open={sheet === 'submit'} onClose={() => setSheet(null)} />
        </>
      )}
    </>
  );
}

export function VacancyDetailPage() {
  const { vacancyId = '' } = useParams();
  const instance = useInstance();
  const options = useVacancyOptions();
  const vacancy = useQuery({
    queryKey: VACANCY_KEYS.detail(vacancyId),
    queryFn: () => fetchVacancy(vacancyId),
    retry: false,
  });

  if (vacancy.isPending) {
    return (
      <nldd-simple-section>
        <PageHeading text="Vacature" instanceName={instance?.name} />
        <Loading />
      </nldd-simple-section>
    );
  }
  if (vacancy.isError) {
    const missing = vacancy.error instanceof ApiError && vacancy.error.status === 404;
    return (
      <nldd-simple-section>
        <PageHeading text="Vacature" instanceName={instance?.name} />
        {missing ? (
          <EmptyNotice
            text="Deze vacature is niet gevonden"
            supportingText="De vacature bestaat niet, of je kunt haar niet inzien."
          />
        ) : (
          <ErrorNotice message={errorMessage(vacancy.error)} />
        )}
        <nldd-spacer size="16" />
        <LinkButton text="Naar alle vacatures" href={PATHS.vacancies} />
      </nldd-simple-section>
    );
  }

  const data = vacancy.data;
  // Without the type the viewer got the public view only.
  const full = data.vacancy_type !== undefined;

  return (
    <>
      <nldd-simple-section>
        <PageHeading text={data.function_title} instanceName={instance?.name} />
        <nldd-tag color={STATUS_COLORS[data.status]} text={STATUS_LABELS[data.status]} />
        <nldd-spacer size="16" />
        {full ? <Details vacancy={data} options={options.data} /> : <PublicView vacancy={data} />}
      </nldd-simple-section>
      {full && (
        <>
          <nldd-simple-section>
            <DecisionsSection vacancy={data} />
          </nldd-simple-section>
          <nldd-simple-section>
            <ProcedureSection vacancy={data} options={options.data} />
          </nldd-simple-section>
          <nldd-simple-section>
            <TextsSection vacancy={data} options={options.data} />
          </nldd-simple-section>
          {data.permissions.can_download_form && (
            <nldd-simple-section>
              <RequestFormSection vacancy={data} options={options.data} />
            </nldd-simple-section>
          )}
          {(data.permissions.can_fill || data.permissions.can_withdraw) && (
            <nldd-simple-section>
              <ClosingSection vacancy={data} />
            </nldd-simple-section>
          )}
        </>
      )}
    </>
  );
}
