import { useCourses } from '@/features/tasks/course';
import { courseLine } from '@/ui/course';
import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { assignmentKeys, fetchPersonOptions } from '@/features/assignments/api';
import { formatDate, formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import {
  ROLE_PARAM,
  VACANCY_KEYS,
  createVacancy,
  fetchFilledRoles,
  fetchUnfilledRoles,
  fetchVacancies,
  type FilledRole,
  type UnfilledRole,
  type VacancyOptions,
  type VacancySummary,
  type VacancyType,
} from './api';
import { parseFte, useVacancyOptions } from './hooks';
import { STATUS_COLORS, VACANCY_TYPE_LABELS, scaleAndFte } from './labels';
import { ORDER_OPTIONS, orderVacancies, standingOf, statusWord, type ListOrder } from './list';
import {
  FILLED_GROUP,
  KNOWN_CANDIDATE,
  filledHint,
  filledRoleLabel,
  roleLabel,
  typeConsequence,
} from './newVacancy';
import { DateInput, SelectInput, TextInput, Note } from './ui';
import { FormSheet, LoadError, Loading, Page } from '@/ui/layout';
import { useVacancyViewFilter } from './views';
import { OpenRow } from '@/ui/RowActions';

const NO_BUDGET_LINE = 'none';

function summaryLine(vacancy: VacancySummary): string {
  return [
    vacancy.assignment_name,
    scaleAndFte(vacancy.scale, vacancy.fte),
    formatPeriod(vacancy.start_date, vacancy.end_date),
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * The vacancies as a table: every column starts at the same place on every
 * row, so status and next step can be read down the page. On a narrow
 * screen the type and the status column go, and the status moves above the
 * next step.
 */
function VacancyTable({
  vacancies,
  emptyText,
}: {
  vacancies: VacancySummary[];
  emptyText: string;
}) {
  const navigate = useNavigate();
  const open = (id: string) => navigate(PATHS.vacancyDetail.replace(':vacancyId', id));
  // A reader who only gets the published vacancies has no type or step.
  const withType = vacancies.some((vacancy) => vacancy.vacancy_type !== undefined);
  const withStep = vacancies.some((vacancy) => vacancy.step !== undefined);
  // Where each vacancy stands and whose move it is, in the words of its page.
  const courses = useCourses(
    'vacancy',
    withStep ? vacancies.map((vacancy) => vacancy.id) : [],
  ).byId;
  const wide = [
    'minmax(240px,2fr)',
    ...(withType ? ['150px'] : []),
    ...(withStep ? ['minmax(260px,1.6fr)'] : ['150px']),
  ].join(' ');
  // The name gets the larger share: a long function name must fit beside the step.
  const narrow = withStep ? 'minmax(0,1.3fr) minmax(0,1fr)' : 'minmax(0,1fr) 130px';
  return (
    <nldd-table accessible-label="Vacatures" columns={wide} sm-columns={narrow}>
      <nldd-table-row slot="header">
        <nldd-text-cell text="Vacature" />
        {withType && <nldd-text-cell text="Type" hide-below="md" />}
        {withStep ? <nldd-text-cell text="Stand" /> : <nldd-text-cell text="Status" />}
      </nldd-table-row>
      {vacancies.map((vacancy) => {
        const line = courseLine(courses.get(vacancy.id)?.course);
        const fallback = standingOf(vacancy);
        // The course when it is known; until then what the list itself says.
        const standing = line
          ? { step: line.step, detail: line.who }
          : { step: fallback.step || statusWord(vacancy), detail: fallback.detail };
        const status = statusWord(vacancy);
        return (
          <OpenRow key={vacancy.id} onOpen={() => open(vacancy.id)}>
            {/* A real address on the name, so it opens in a new tab too; a
                click anywhere else in the row goes to the same place. */}
            <nldd-cell>
              <nldd-container gap="4">
                <nldd-link
                  href={PATHS.vacancyDetail.replace(':vacancyId', vacancy.id)}
                  text={vacancy.function_title}
                />
                <nldd-text size="sm" color="secondary">
                  {summaryLine(vacancy)}
                </nldd-text>
              </nldd-container>
            </nldd-cell>
            {withType && (
              <nldd-text-cell
                hide-below="md"
                text={vacancy.vacancy_type ? VACANCY_TYPE_LABELS[vacancy.vacancy_type] : ''}
              />
            )}
            {withStep ? (
              <nldd-text-cell
                text={standing.step}
                {...(standing.detail ? { 'supporting-text': standing.detail } : {})}
              />
            ) : (
              <nldd-cell>
                <nldd-badge color={STATUS_COLORS[vacancy.status]} text={status} />
              </nldd-cell>
            )}
          </OpenRow>
        );
      })}
      <nldd-inline-dialog slot="empty" text="Nog geen vacatures" supporting-text={emptyText} />
    </nldd-table>
  );
}

interface CreateSheetProps {
  open: boolean;
  onClose: () => void;
  options: VacancyOptions | undefined;
  roles: UnfilledRole[];
  /** Fully staffed roles: a vacancy there starts a replacement or a successor. */
  filled: FilledRole[];
  /** The budget line to start with, when the visitor came from a role. */
  initialLine?: string | null;
  /** Roles a vacancy already runs for: not offered again, and said so. */
  running: VacancySummary[];
}

/** "Ontwerper (Opdracht Alfa 2026)" for each role that already has a vacancy. */
function runningText(running: VacancySummary[]): string {
  const names = running.map((vacancy) =>
    vacancy.assignment_name
      ? `${vacancy.function_title} (${vacancy.assignment_name})`
      : vacancy.function_title,
  );
  return running.length === 1
    ? `Voor ${names[0]} loopt al een vacature; die staat in de lijst.`
    : `Voor ${names.join(', ')} lopen al vacatures; die staan in de lijst.`;
}

function CreateSheet({
  open,
  onClose,
  options,
  roles,
  filled,
  initialLine,
  running,
}: CreateSheetProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const withoutLine = options?.can_create_without_budget_line ?? false;
  const [line, setLine] = useState(initialLine ?? '');
  const [title, setTitle] = useState('');
  const [fte, setFte] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [vacancyType, setVacancyType] = useState<VacancyType>('regulier');
  // Empty until chosen; the line's intended person is the proposal.
  const [candidate, setCandidate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lineOptions = [
    ...roles.map((role) => ({ value: role.budget_line_id, label: roleLabel(role) })),
    ...(withoutLine
      ? [{ value: NO_BUDGET_LINE, label: 'Geen begrotingsregel (niet declarabel)' }]
      : []),
    ...filled.map((role) => ({
      value: role.budget_line_id,
      label: filledRoleLabel(role),
      group: FILLED_GROUP,
    })),
  ];
  const loose = line === NO_BUDGET_LINE;
  const chosenRole = [...roles, ...filled].find((role) => role.budget_line_id === line);
  const chosenFilled = filled.find((role) => role.budget_line_id === line);
  // Under the select: who fills the chosen role (the closed select cuts a
  // long option off), or why the list of open roles is short.
  const roleHint = chosenFilled
    ? filledHint(chosenFilled)
    : roles.length === 0
      ? 'Alle rollen op je begrotingen zijn ingevuld.'
      : '';
  const forCandidate = KNOWN_CANDIDATE.has(vacancyType) && !loose;
  const intended = chosenRole?.intended_person_id ?? '';
  const candidateId = candidate || intended;
  const people = useQuery({
    queryKey: assignmentKeys.personOptions,
    queryFn: fetchPersonOptions,
    enabled: open && forCandidate,
    retry: false,
  });

  async function submit() {
    setError(null);
    if (!line) {
      setError('Kies de rol waarvoor je een vacature opent.');
      return;
    }
    const fteValue = loose ? parseFte(fte) : null;
    if (loose && !title.trim()) {
      setError('Vul de functie in.');
      return;
    }
    if (loose && fteValue === null) {
      setError('Het aantal fte is een getal groter dan nul, bijvoorbeeld 0,8.');
      return;
    }
    if (forCandidate && !candidateId) {
      setError('Kies de kandidaat voor wie deze vacature is.');
      return;
    }
    setBusy(true);
    try {
      const vacancy = await createVacancy({
        ...(loose
          ? {
              function_title: title.trim(),
              fte: fteValue ?? undefined,
              start_date: start || null,
              end_date: end || null,
            }
          : { budget_line_id: line }),
        vacancy_type: vacancyType,
        ...(forCandidate && candidateId ? { candidate_person_id: candidateId } : {}),
      });
      void queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      onClose();
      navigate(PATHS.vacancyDetail.replace(':vacancyId', vacancy.id));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormSheet
      open={open}
      title="Nieuwe vacature"
      submitText="Maak vacature"
      onSubmit={() => void submit()}
      onClose={onClose}
      busy={busy}
      error={error}
    >
      <SelectInput
        label="Rol"
        {...(roleHint ? { hint: roleHint } : {})}
        value={line}
        onChange={setLine}
        options={lineOptions}
        placeholder="Kies een rol"
        required
      />
      {running.length > 0 ? <Note>{runningText(running)}</Note> : null}
      {loose && (
        <>
          <TextInput label="Functie" value={title} onChange={setTitle} required />
          <TextInput label="Aantal fte" value={fte} onChange={setFte} keyboard="decimal" required />
          <DateInput label="Begindatum" value={start} onChange={setStart} optional />
          <DateInput label="Einddatum" value={end} onChange={setEnd} optional />
        </>
      )}
      <SelectInput
        label="Type vacature"
        value={vacancyType}
        onChange={(value) => setVacancyType(value as VacancyType)}
        {...(typeConsequence(vacancyType) ? { hint: typeConsequence(vacancyType) } : {})}
        options={options?.vacancy_types ?? []}
      />
      {forCandidate && (
        <SelectInput
          label="Kandidaat"
          hint={
            candidateId && candidateId !== intended
              ? 'Wordt ook de beoogde persoon van de begrotingsregel.'
              : candidateId
                ? 'De beoogde persoon van de begrotingsregel.'
                : undefined
          }
          value={candidateId}
          onChange={setCandidate}
          placeholder="Kies de kandidaat"
          options={(people.data ?? []).map((person) => ({
            value: person.id,
            label: person.starts_on
              ? `${person.name}, start op ${formatDate(person.starts_on)}`
              : person.name,
          }))}
          required
        />
      )}
    </FormSheet>
  );
}

export function VacanciesPage() {
  const instance = useInstance();
  const containerRef = useRef<HTMLDivElement>(null);
  useRouterLinks(containerRef);
  // Inzet links here with the budget line of an unfilled role: open the
  // form for that role straight away.
  const [searchParams] = useSearchParams();
  const requestedLine = searchParams.get(ROLE_PARAM);
  const [creating, setCreating] = useState(requestedLine !== null);
  const [order, setOrder] = useState<ListOrder>('waiting');
  const viewFilter = useVacancyViewFilter('list');

  const vacancies = useQuery({ queryKey: VACANCY_KEYS.list, queryFn: fetchVacancies });
  const roles = useQuery({ queryKey: VACANCY_KEYS.unfilledRoles, queryFn: fetchUnfilledRoles });
  const filledRoles = useQuery({
    queryKey: VACANCY_KEYS.filledRoles,
    queryFn: fetchFilledRoles,
    retry: false,
  });
  const options = useVacancyOptions();

  const unfilled = roles.data ?? [];
  const filled = Array.isArray(filledRoles.data) ? filledRoles.data : [];
  const canCreate =
    unfilled.length > 0 ||
    filled.length > 0 ||
    (options.data?.can_create_without_budget_line ?? false);

  return (
    <div ref={containerRef}>
      <Page title="Vacatures" instanceName={instance?.name}>
        <ActionBar
          label="Vacatures ordenen en acties"
          filters={[
            viewFilter,
            {
              label: 'Volgorde',
              value: order,
              onChange: (value) => setOrder(value as ListOrder),
              options: ORDER_OPTIONS,
              width: '200px',
            },
          ]}
          actions={[
            ...(canCreate
              ? [{ text: 'Nieuwe vacature', onClick: () => setCreating(true), primary: true }]
              : []),
          ]}
        />
        {vacancies.isPending && <Loading />}
        {vacancies.isError && (
          <LoadError error={vacancies.error} retry={() => void vacancies.refetch()} />
        )}
        {vacancies.data && (
          <VacancyTable
            vacancies={orderVacancies(vacancies.data, order)}
            emptyText={
              canCreate
                ? 'Open een vacature voor een rol op een begroting die nog niet is ingevuld.'
                : 'Er staan geen vacatures open die je kunt inzien.'
            }
          />
        )}
      </Page>
      <CreateSheet
        open={creating}
        onClose={() => setCreating(false)}
        options={options.data}
        roles={unfilled}
        filled={filled}
        initialLine={requestedLine}
        running={(vacancies.data ?? []).filter(
          (vacancy) =>
            vacancy.budget_line_id &&
            ['draft', 'requested', 'approved', 'open'].includes(vacancy.status),
        )}
      />
    </div>
  );
}
