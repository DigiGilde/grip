import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { formatFte, formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import {
  ROLE_PARAM,
  VACANCY_KEYS,
  createVacancy,
  fetchUnfilledRoles,
  fetchVacancies,
  type ContractType,
  type UnfilledRole,
  type VacancyOptions,
  type VacancySummary,
  type VacancyType,
} from './api';
import { parseFte, parseScale, useVacancyOptions } from './hooks';
import { STATUS_COLORS, STATUS_LABELS, scaleAndFte } from './labels';
import {
  Button,
  DateInput,
  ErrorNotice,
  FormSheet,
  LinkButton,
  Loading,
  SelectInput,
  TextInput,
} from './ui';

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

function stepLine(vacancy: VacancySummary): string | undefined {
  if (vacancy.next_step && ['draft', 'requested', 'approved', 'open'].includes(vacancy.status)) {
    return `Volgende stap: ${vacancy.next_step}`;
  }
  return vacancy.current_step ? `Laatste stap: ${vacancy.current_step}` : undefined;
}

function VacancyRow({ vacancy }: { vacancy: VacancySummary }) {
  const status = STATUS_LABELS[vacancy.status];
  const step = stepLine(vacancy);
  return (
    <nldd-list-item href={PATHS.vacancyDetail.replace(':vacancyId', vacancy.id)}>
      <nldd-text-cell text={vacancy.function_title} supporting-text={summaryLine(vacancy)} />
      <nldd-spacer-cell size="8" />
      <nldd-cell>
        <nldd-badge color={STATUS_COLORS[vacancy.status]} decorative />
      </nldd-cell>
      <nldd-spacer-cell size="8" />
      <nldd-text-cell
        width="fit-content"
        text={status}
        {...(step ? { 'supporting-text': step } : {})}
      />
      <nldd-spacer-cell size="8" />
      <nldd-icon-cell size="20" color="secondary" icon="chevron-right" />
    </nldd-list-item>
  );
}

interface CreateSheetProps {
  open: boolean;
  onClose: () => void;
  options: VacancyOptions | undefined;
  roles: UnfilledRole[];
  /** The budget line to start with, when the visitor came from an unfilled role. */
  initialLine?: string | null;
}

function roleLabel(role: UnfilledRole): string {
  return `${role.assignment_name}: ${role.role ?? role.description} (${formatFte(role.unfilled_fte)} fte open)`;
}

function CreateSheet({ open, onClose, options, roles, initialLine }: CreateSheetProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const withoutLine = options?.can_create_without_budget_line ?? false;
  const [line, setLine] = useState(initialLine ?? '');
  const [title, setTitle] = useState('');
  const [fte, setFte] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [vacancyType, setVacancyType] = useState<VacancyType>('regulier');
  const [contractType, setContractType] = useState('');
  const [fgr, setFgr] = useState('');
  const [scale, setScale] = useState('');
  const [addressee, setAddressee] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lineOptions = [
    ...roles.map((role) => ({ value: role.budget_line_id, label: roleLabel(role) })),
    ...(withoutLine
      ? [{ value: NO_BUDGET_LINE, label: 'Geen begrotingsregel (niet declarabel)' }]
      : []),
  ];
  const loose = line === NO_BUDGET_LINE;

  async function submit() {
    setError(null);
    if (!line) {
      setError('Kies de rol waarvoor je een vacature opent.');
      return;
    }
    const scaleValue = parseScale(scale);
    if (scaleValue === undefined) {
      setError('De schaal is een heel getal van 1 tot en met 19.');
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
        contract_type: (contractType || null) as ContractType | null,
        fgr_function_name: fgr.trim() || null,
        scale: scaleValue,
        addressee_name: addressee.trim() || null,
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
        hint="Een rol op een begroting die nog niet is ingevuld. Functie, fte en periode komen van de begrotingsregel."
        value={line}
        onChange={setLine}
        options={lineOptions}
        placeholder="Kies een rol"
        required
      />
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

export function VacanciesPage() {
  const instance = useInstance();
  const containerRef = useRef<HTMLDivElement>(null);
  useRouterLinks(containerRef);
  // Inzet links here with the budget line of an unfilled role: open the
  // form for that role straight away.
  const [searchParams] = useSearchParams();
  const requestedLine = searchParams.get(ROLE_PARAM);
  const [creating, setCreating] = useState(requestedLine !== null);

  const vacancies = useQuery({ queryKey: VACANCY_KEYS.list, queryFn: fetchVacancies });
  const roles = useQuery({ queryKey: VACANCY_KEYS.unfilledRoles, queryFn: fetchUnfilledRoles });
  const options = useVacancyOptions();

  const unfilled = roles.data ?? [];
  const canCreate = unfilled.length > 0 || (options.data?.can_create_without_budget_line ?? false);

  return (
    <div ref={containerRef}>
      <nldd-simple-section>
        <PageHeading text="Vacatures" instanceName={instance?.name} />
        <nldd-button-group>
          {canCreate && (
            <Button text="Nieuwe vacature" appearance="primary" onClick={() => setCreating(true)} />
          )}
          <LinkButton text="Open rollen" href={PATHS.vacancyOpenRoles} />
          {options.data?.can_manage_setup && (
            <LinkButton text="Formulier en taalmodel" href={PATHS.vacancySetup} />
          )}
        </nldd-button-group>
        <nldd-spacer size="16" />
        {vacancies.isPending && <Loading />}
        {vacancies.isError && <ErrorNotice message={errorMessage(vacancies.error)} />}
        {vacancies.data && (
          <nldd-list appearance="box-base" accessible-label="Vacatures">
            {vacancies.data.map((vacancy) => (
              <VacancyRow key={vacancy.id} vacancy={vacancy} />
            ))}
            <nldd-inline-dialog
              slot="empty"
              text="Nog geen vacatures"
              supporting-text={
                canCreate
                  ? 'Open een vacature voor een rol op een begroting die nog niet is ingevuld.'
                  : 'Er staan geen vacatures open die je kunt inzien.'
              }
            />
          </nldd-list>
        )}
      </nldd-simple-section>
      <CreateSheet
        open={creating}
        onClose={() => setCreating(false)}
        options={options.data}
        roles={unfilled}
        initialLine={requestedLine}
      />
    </div>
  );
}
