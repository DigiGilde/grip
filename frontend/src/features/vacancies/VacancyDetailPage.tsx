import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
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
  type Vacancy,
  type VacancyOptions,
  type VacancyType,
} from './api';
import { ClosingSection } from './ClosingSection';
import { DecisionsSection } from './DecisionsSection';
import { parseFte, todayIso, useVacancyChange, useVacancyOptions } from './hooks';
import {
  CONTRACT_TYPE_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
  VACANCY_TYPE_LABELS,
  budgetLineWarning,
  missingRequestDetails,
  publishedOrigin,
} from './labels';
import { PrepareRequestSheet } from './PrepareRequestSheet';
import { ProcedureSection } from './ProcedureSection';
import { RequestFormSection } from './RequestFormSection';
import {
  STEP_ANCHORS,
  requestItems,
  vacancySteps,
  type RequestItem,
  type StepAction,
} from './steps';
import { TextsSection } from './TextsSection';
import { Button, DateInput, LinkButton, Note, Paragraphs, SelectInput, TextInput } from './ui';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, SectionHeading } from '@/ui/layout';

const NOT_FILLED = 'Nog niet ingevuld';

interface FactProps {
  label: string;
  value: string | null | undefined;
  /** A line under the value, such as the function family. */
  detail?: string | null;
  /** Shown as "nog niet ingevuld" instead of being left out. */
  expected?: boolean;
  /** Makes the row a button that opens where the value is edited. */
  onEdit?: () => void;
}

/** One label and value. With `onEdit` the whole row is the way to change it. */
function Fact({ label, value, detail, expected, onEdit }: FactProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onEdit ? () => onEdit() : undefined);
  if (!value && !expected) return null;
  return (
    <nldd-list-item
      ref={ref}
      button={orUndef(Boolean(onEdit))}
      {...(onEdit ? { 'accessible-label': `${label}: ${value || NOT_FILLED}. Wijzig` } : {})}
    >
      <nldd-text-cell
        overline={label}
        text={value || NOT_FILLED}
        color={value ? 'content' : 'secondary'}
        {...(detail ? { 'supporting-text': detail } : {})}
      />
      {onEdit && (
        <>
          <nldd-spacer-cell size="8" />
          <nldd-icon-cell size="20" color="secondary" icon="pencil" />
        </>
      )}
    </nldd-list-item>
  );
}

interface FactsProps {
  vacancy: Vacancy;
  /** Set when the reader may change the role itself (function, fte, period, type). */
  onEditRole?: () => void;
  /** Set when the reader may change what the request form asks for. */
  onEditRequest?: () => void;
}

function Facts({ vacancy, onEditRole, onEditRequest }: FactsProps) {
  // The request details are always listed for who sees the whole vacancy, so
  // someone looking for "schaal" finds it by reading the page.
  const full = vacancy.vacancy_type !== undefined;
  return (
    <RouterLinks>
      <nldd-list appearance="box-base" accessible-label="Gegevens van de vacature">
        <Fact label="Functie" value={vacancy.function_title} onEdit={onEditRole} />
        <Fact label="Aantal fte" value={formatFte(vacancy.fte)} onEdit={onEditRole} />
        <Fact
          label="Periode"
          value={formatPeriod(vacancy.start_date, vacancy.end_date)}
          expected={full && Boolean(onEditRole)}
          onEdit={onEditRole}
        />
        <Fact
          label="Type vacature"
          value={vacancy.vacancy_type ? VACANCY_TYPE_LABELS[vacancy.vacancy_type] : null}
          onEdit={onEditRole}
        />
        <Fact
          label="FGR-functienaam"
          value={vacancy.fgr_function_name}
          detail={
            vacancy.function_family_name
              ? `Functiefamilie ${vacancy.function_family_name}`
              : vacancy.fgr_function_name && vacancy.function_group_id === null
                ? 'Zelf ingevuld, niet uit het Functiegebouw Rijk'
                : null
          }
          expected={full}
          onEdit={onEditRequest}
        />
        <Fact
          label="Schaal"
          value={
            vacancy.scale === null || vacancy.scale === undefined ? null : String(vacancy.scale)
          }
          detail={
            vacancy.scale_deviation_reason
              ? `Wijkt af van de functiegroep: ${vacancy.scale_deviation_reason}`
              : null
          }
          expected={full}
          onEdit={onEditRequest}
        />
        <Fact
          label="Type contract"
          value={vacancy.contract_type ? CONTRACT_TYPE_LABELS[vacancy.contract_type] : null}
          expected={full}
          onEdit={onEditRequest}
        />
        {'addressee_name' in vacancy && (
          <Fact
            label="Aan"
            value={vacancy.addressee_name}
            detail={vacancy.addressee_name ? 'Geeft akkoord op de aanvraag' : null}
            expected
            onEdit={onEditRequest}
          />
        )}
        {vacancy.assignment_id && vacancy.assignment_name ? (
          <nldd-list-item href={assignmentPath(vacancy.assignment_id)}>
            <nldd-text-cell overline="Opdracht" text={vacancy.assignment_name} />
            <nldd-spacer-cell size="8" />
            <nldd-icon-cell size="20" color="secondary" icon="chevron-right" />
          </nldd-list-item>
        ) : (
          <Fact label="Opdracht" value={vacancy.assignment_name} />
        )}
        {vacancy.declarable !== undefined && (
          <Fact label="Declarabel" value={vacancy.declarable ? 'Ja' : 'Nee'} />
        )}
        <Fact label="Aangevraagd door" value={vacancy.requester_name} />
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
      <Note>
        Met de aanvraag vraag je akkoord om de vacature open te stellen. Daarna kunnen het advies
        van HR en concern control en het akkoord worden vastgelegd.
      </Note>
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

function scrollToSection(id: string) {
  const target = document.getElementById(id);
  if (!target) return;
  target.scrollIntoView({ block: 'start' });
  // Move focus too, so a keyboard or screen reader user lands there as well.
  const heading = target.querySelector<HTMLElement>('h2');
  if (heading) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
}

/** One line of the checklist: ticked when filled, and the way to fill it. */
function ChecklistItem({ item, onOpen }: { item: RequestItem; onOpen?: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onOpen ? () => onOpen() : undefined);
  const done = item.value !== null;
  const state = done ? 'ingevuld' : item.optional ? 'nog open, mag later' : 'nog niet ingevuld';
  return (
    <nldd-list-item
      ref={ref}
      size="sm"
      button={orUndef(Boolean(onOpen))}
      {...(onOpen ? { 'accessible-label': `${item.label}: ${state}. ${done ? 'Wijzig' : 'Vul in'}` } : {})}
    >
      <nldd-icon-cell
        size="20"
        icon={done ? 'check-circle-filled' : 'circle'}
        color={done ? 'success' : 'secondary'}
      />
      <nldd-spacer-cell size="8" />
      <nldd-text-cell
        text={item.label}
        supporting-text={
          done ? (item.value ?? '') : item.optional ? 'Nog open; kan ook na de aanvraag' : NOT_FILLED
        }
      />
      {onOpen && (
        <>
          <nldd-spacer-cell size="8" />
          <nldd-icon-cell size="20" color="secondary" icon="chevron-right" />
        </>
      )}
    </nldd-list-item>
  );
}

const ACTION_TEXT: Record<StepAction, string> = {
  prepare: 'Bereid aanvraag voor',
  submit: 'Vraag aan',
  decide: 'Naar advies en akkoord',
  open: 'Naar openstellen',
  fill: 'Naar afronden',
};

type SheetName = 'edit' | 'submit' | 'prepare' | null;

/** Where the vacancy stands, what to do now, and what the request still needs. */
function NextStep({ vacancy, onSheet }: { vacancy: Vacancy; onSheet: (sheet: SheetName) => void }) {
  const steps = vacancySteps(vacancy);
  if (!steps) return null;
  const editable = vacancy.permissions.can_edit && ['draft', 'requested'].includes(vacancy.status);
  const items = requestItems(vacancy);
  const open = items.filter((item) => item.value === null && !item.optional).length;
  // The checklist belongs to the request: shown until the approval fixes it.
  const showChecklist = ['draft', 'requested'].includes(vacancy.status);

  function act(action: StepAction) {
    if (action === 'prepare') onSheet('prepare');
    else if (action === 'submit') onSheet('submit');
    else scrollToSection(STEP_ANCHORS[action]);
  }

  return (
    <nldd-container gap="12">
      <SectionHeading text="Volgende stap" />
      <nldd-step-bar {...{ current: steps.current }} accessible-label="Stappen van de vacature">
        {steps.items.map((text) => (
          <nldd-step-bar-item key={text} text={text} />
        ))}
      </nldd-step-bar>
      <nldd-text>{steps.advice}</nldd-text>
      {showChecklist && (
        <nldd-list
          appearance="box-base"
          accessible-label={
            open > 0
              ? `Voor het aanvraagformulier, nog ${open} in te vullen`
              : 'Voor het aanvraagformulier, alles ingevuld'
          }
        >
          {items.map((item) => (
            <ChecklistItem
              key={item.key}
              item={item}
              onOpen={
                !editable
                  ? undefined
                  : item.where === 'sheet'
                    ? () => onSheet('prepare')
                    : () => scrollToSection(STEP_ANCHORS.texts)
              }
            />
          ))}
        </nldd-list>
      )}
      {steps.action && (
        <nldd-button-group>
          <Button
            text={ACTION_TEXT[steps.action]}
            appearance="primary"
            onClick={() => act(steps.action as StepAction)}
          />
          {/* The request can be made before everything is filled in. */}
          {steps.action === 'prepare' && (
            <Button text="Vraag nu al aan" onClick={() => onSheet('submit')} />
          )}
        </nldd-button-group>
      )}
    </nldd-container>
  );
}

function Details({ vacancy, options }: { vacancy: Vacancy; options: VacancyOptions | undefined }) {
  const [sheet, setSheet] = useState<SheetName>(null);
  const editable = vacancy.permissions.can_edit && ['draft', 'requested'].includes(vacancy.status);
  const warning =
    vacancy.scale_fits_budget_line === false
      ? budgetLineWarning(vacancy.scale, vacancy.budget_line_scales)
      : null;
  return (
    <>
      <NextStep vacancy={vacancy} onSheet={setSheet} />
      <nldd-spacer size="24" />
      <SectionHeading text="Gegevens" />
      {editable && <Note>Kies een regel om die te wijzigen.</Note>}
      <Facts
        vacancy={vacancy}
        {...(editable
          ? { onEditRole: () => setSheet('edit'), onEditRequest: () => setSheet('prepare') }
          : {})}
      />
      {warning && <nldd-banner variant="warning" size="sm" text={warning} />}
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
          <PrepareRequestSheet
            // A fresh form per saved state of what it edits.
            key={`prepare-${vacancy.function_group_id}-${vacancy.fgr_function_name}-${vacancy.scale}-${vacancy.contract_type}-${vacancy.addressee_name}`}
            vacancy={vacancy}
            options={options}
            open={sheet === 'prepare'}
            onClose={() => setSheet(null)}
          />
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
          <nldd-simple-section id={STEP_ANCHORS.decide}>
            <DecisionsSection vacancy={data} />
          </nldd-simple-section>
          <nldd-simple-section id={STEP_ANCHORS.open}>
            <ProcedureSection vacancy={data} options={options.data} />
          </nldd-simple-section>
          <nldd-simple-section id={STEP_ANCHORS.texts}>
            <TextsSection vacancy={data} options={options.data} />
          </nldd-simple-section>
          {data.permissions.can_download_form && (
            <nldd-simple-section>
              <RequestFormSection vacancy={data} options={options.data} />
            </nldd-simple-section>
          )}
          {(data.permissions.can_fill || data.permissions.can_withdraw) && (
            <nldd-simple-section id={STEP_ANCHORS.fill}>
              <ClosingSection vacancy={data} />
            </nldd-simple-section>
          )}
        </>
      )}
    </>
  );
}
