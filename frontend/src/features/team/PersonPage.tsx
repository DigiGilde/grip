import { documentTitle } from '@/brand/names';
import { iconOf } from '@/ui/icons';
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { useAuth } from '@/auth/context';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { boardKeys, fetchBoard, type BoardPerson } from '@/features/allocations/board/api';
import { buildGroups, toTimeline } from '@/features/allocations/board/model';
import { assignmentTabPath } from '@/features/assignments/paths';
import { WIES_KEYS, fetchReconciliation } from '@/features/wies/api';
import { formatDate, formatEuro, formatMonth, formatPercent, formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PAGE_HEADING_ID } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import { EmptyNotice, ErrorNotice, Loading, Quiet, Section, Stack } from '@/ui/layout';
import { ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';
import { Timeline } from '@/ui/timeline/Timeline';
import { barsInColumn } from '@/ui/timeline/layout';
import {
  FUNCTIONS,
  fetchLoginState,
  fetchPerson,
  fetchPersonKpi,
  fetchPersonRoles,
  functionLabel,
  loginKey,
  personKey,
  personKpiKey,
  personRolesKey,
  removeHire,
  scaleHistory,
  setFunction,
  today,
  unbindLogin,
  updatePerson,
  type FunctionGrant,
  type Hire,
  type Kpi,
  type Person,
  type Scale,
} from './api';
import {
  GrantForm,
  HireForm,
  IdentityForm,
  ManagerForm,
  RolesForm,
  ScaleForm,
  TargetForm,
} from './PersonForms';
import { useSave } from './useSave';
import {
  KPI_STANDING_TEXT,
  deploymentOf,
  engagementLabel,
  eventGroups,
  identityFacts,
  kpiStanding,
  type EventGroup,
  type EventItem,
  type PersonEvent,
} from './personView';
import { Button } from './ui/controls';
import { ConfirmDialog, Sheet } from './ui/overlays';

/**
 * A colleague: who this is, how they are deployed and whether they are on
 * track, and then what has a history (scale, hire, rights).
 *
 * The page is read first and acted on second. The first screenful answers
 * "how is this person doing": the deployment over the months as a picture
 * and the declarability against the target. What changes in a working life
 * (a promotion, a new manager, a hire contract, leaving) is offered as the
 * event it is, in one menu; each opens a sheet and nothing is open by
 * default.
 *
 * A part the reader may not see is not rendered at all: the response does
 * not carry its fields, and a section is drawn only for fields that are
 * there. The same page serves the beheerder, a line manager, a planner and
 * the person themselves.
 */
export function PersonPage() {
  const { personId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const requested = searchParams.get('peildatum');
  const day = requested && /^\d{4}-\d{2}-\d{2}$/.test(requested) ? requested : today();
  const { state } = useAuth();
  const mayManage = state.status === 'authenticated' && state.functions.includes('beheerder');

  const query = useQuery({
    queryKey: personKey(personId, day),
    queryFn: () => fetchPerson(personId, day),
    retry: false,
  });
  const person = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;

  if (person) return <PersonScreen person={person} day={day} mayManage={mayManage} />;
  return (
    <nldd-simple-section>
      <Heading name="Persoon" />
      {notFound ? (
        <EmptyNotice
          text="Deze persoon is niet gevonden"
          supportingText="De persoon bestaat niet, of je mag de gegevens niet inzien."
        />
      ) : query.isError ? (
        <ErrorNotice message={errorMessage(query.error)} />
      ) : (
        <Loading />
      )}
    </nldd-simple-section>
  );
}

// -- header ------------------------------------------------------------------------------------

interface HeadingProps {
  name: string;
  /** The one action of the page, at the end of the title line. */
  end?: React.ReactNode;
  children?: React.ReactNode;
}

/**
 * The way back above the name, the name, and under it who this is in one
 * line. Sits in the header slot of the section, so it keeps the design
 * system's distance to the content.
 */
function Heading({ name, end, children }: HeadingProps) {
  const instance = useInstance();
  const ref = useRef<HTMLElement>(null);
  useRouterLinks(ref);
  useEffect(() => {
    document.title = documentTitle(name, instance?.name);
  }, [name, instance?.name]);
  return (
    <nldd-container ref={ref} slot="header" gap="8">
      <nldd-breadcrumbs>
        <nldd-breadcrumbs-item href={PATHS.team} text="Team" />
        <nldd-breadcrumbs-item current text={name} />
      </nldd-breadcrumbs>
      <nldd-title size={2}>
        {/* tabIndex -1: focusable from script after navigation, not a tab stop. */}
        <h1 id={PAGE_HEADING_ID} tabIndex={-1}>
          {name}
        </h1>
        {end}
      </nldd-title>
      {children}
    </nldd-container>
  );
}

function EventMenuItem({ item, onChoose }: { item: EventItem; onChoose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', onChoose);
  return <nldd-menu-item ref={ref} text={item.text} destructive={orUndef(item.destructive)} />;
}

/** Everything that can change about this person, named as what happened. */
function ChangeMenu({
  groups,
  onChoose,
}: {
  groups: EventGroup[];
  onChoose: (event: PersonEvent) => void;
}) {
  return (
    <nldd-button slot="end" appearance="primary" expandable text="Leg een verandering vast">
      <nldd-menu slot="popup" placement="bottom-end">
        {groups.map((group) => (
          <nldd-menu-group key={group.title} text={group.title}>
            {group.items.map((item) => (
              <EventMenuItem key={item.event} item={item} onChoose={() => onChoose(item.event)} />
            ))}
          </nldd-menu-group>
        ))}
      </nldd-menu>
    </nldd-button>
  );
}

const PROPOSAL_STATES: Record<string, string> = {
  open: 'Voorgesteld aan Wies, nog niet overgenomen',
  confirmed: 'Overgenomen door Wies',
  declined: 'Afgewezen door Wies',
  withdrawn: 'Voorstel aan Wies ingetrokken',
};

/** Where the proposal "new colleague" to Wies stands, for the beheerder. */
function useWiesProposal(person: Person, enabled: boolean): string | null {
  const reconciliation = useQuery({
    queryKey: WIES_KEYS.reconciliation,
    queryFn: fetchReconciliation,
    enabled,
    retry: false,
  });
  const outgoing =
    (reconciliation.data as { outgoing?: { person_id: string; state: string }[] } | undefined)
      ?.outgoing ?? [];
  const proposal = outgoing.find((entry) => entry.person_id === person.id);
  return proposal ? (PROPOSAL_STATES[proposal.state] ?? proposal.state) : null;
}

// -- the page ------------------------------------------------------------------------------------

type Open = null | Exclude<PersonEvent, 'return'> | { removeHire: Hire };

interface ScreenProps {
  person: Person;
  day: string;
  mayManage: boolean;
}

function PersonScreen({ person, day, mayManage }: ScreenProps) {
  const [open, setOpen] = useState<Open>(null);
  const close = () => setOpen(null);
  const year = Number(day.slice(0, 4));
  const bodyRef = useRef<HTMLDivElement>(null);
  useRouterLinks(bodyRef);

  const kpi = useQuery({
    queryKey: personKpiKey(person.id, year),
    queryFn: () => fetchPersonKpi(person.id, year),
    retry: false,
  });
  // The roles follow the reader's right to see staffing; without it the
  // request is refused and nothing about roles is shown.
  const roles = useQuery({
    queryKey: personRolesKey(person.id),
    queryFn: () => fetchPersonRoles(person.id),
    enabled: 'functions' in person,
    retry: false,
  });
  const login = useQuery({
    queryKey: loginKey(person.id),
    queryFn: () => fetchLoginState(person.id),
    enabled: mayManage,
    retry: false,
  });
  // The board already decides per bar and per row what this reader may see.
  const board = useQuery({
    queryKey: boardKeys.board(''),
    queryFn: () => fetchBoard(''),
    enabled: 'current_assignment_count' in person,
    retry: false,
  });
  const proposal = useWiesProposal(person, mayManage && person.stage === 'prospective');
  const direct = useSave(close);

  const grants = person.function_grants ?? [];
  const groups = eventGroups({
    person,
    day,
    year,
    canGrant: FUNCTIONS.some((fn) => !grants.some((grant) => grant.function === fn.id)),
    loginBound: login.data?.bound === true,
  });
  const choose = (event: PersonEvent) => {
    direct.setError(null);
    if (event === 'return') direct.run(() => updatePerson(person.id, { is_active: true }));
    else setOpen(event);
  };
  const removedHire = typeof open === 'object' && open ? open.removeHire : null;
  const facts = identityFacts(person, roles.data?.items ?? null);
  const noRoles = mayManage && roles.data !== undefined && roles.data.items.length === 0;

  return (
    <nldd-simple-section>
      <Heading
        name={person.name}
        end={mayManage ? <ChangeMenu groups={groups} onChoose={choose} /> : null}
      >
        <nldd-container layout="wrap" gap="8" vertical-alignment="center">
          <nldd-tag text={engagementLabel(person, day)} />
          {person.is_active ? null : <nldd-tag color="warning" text="Inactief" />}
          {noRoles ? <Quiet>Nog geen rollen</Quiet> : null}
          {facts.map((fact) => (
            <Quiet key={fact}>{fact}</Quiet>
          ))}
          {person.manager_id ? (
            <nldd-link
              size="sm"
              href={`${PATHS.teamPerson.replace(':personId', person.manager_id)}?peildatum=${day}`}
              text={`Leidinggevende: ${person.manager_name ?? ''}`}
            />
          ) : person.manager_name ? (
            <Quiet>Leidinggevende: {person.manager_name}</Quiet>
          ) : null}
          {proposal ? <Quiet>{proposal}</Quiet> : null}
        </nldd-container>
      </Heading>

      <div ref={bodyRef}>
        <Stack gap="section">
          {direct.error && open === null ? <ErrorNotice message={direct.error} /> : null}
          {'current_assignment_count' in person ? (
            <DeploymentSection
              person={person}
              row={board.data?.persons.find((row) => row.person_id === person.id) ?? null}
              months={board.data?.months ?? []}
              currentMonth={board.data?.current_month ?? ''}
              loading={board.isPending}
            />
          ) : null}
          {kpi.data ? (
            <KpiSection kpi={kpi.data} mayManage={mayManage} onSet={() => setOpen('target')} />
          ) : null}
          {'scales' in person ? (
            <ScaleSection
              person={person}
              day={day}
              mayManage={mayManage}
              onAdd={() => setOpen('scale')}
            />
          ) : null}
          {(person.hires ?? []).some((hire) => hire.supplier) ? (
            <HireSection
              person={person}
              mayManage={mayManage}
              onRemove={(hire) => {
                direct.setError(null);
                setOpen({ removeHire: hire });
              }}
            />
          ) : null}
          {'function_grants' in person && grants.length > 0 ? (
            <RightsSection
              person={person}
              mayManage={mayManage}
              onRevoke={(grant) => direct.run(() => setFunction(person.id, grant.function, false))}
            />
          ) : null}
        </Stack>
      </div>

      {mayManage ? (
        <>
          <Sheet
            open={open === 'scale'}
            title={`Promotie of andere schaal van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <ScaleForm person={person} day={day} onDone={close} />
          </Sheet>
          <Sheet
            open={open === 'manager'}
            title={`Leidinggevende van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <ManagerForm person={person} day={day} onDone={close} />
          </Sheet>
          <Sheet
            open={open === 'hire'}
            title={`Inhuur van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <HireForm person={person} day={day} onDone={close} />
          </Sheet>
          <Sheet
            open={open === 'roles'}
            title={`Rollen van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <RolesForm person={person} roles={roles.data?.items ?? []} onDone={close} />
          </Sheet>
          <Sheet
            open={open === 'target'}
            title={`Target ${year} van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <TargetForm person={person} year={year} kpi={kpi.data ?? null} onDone={close} />
          </Sheet>
          <Sheet
            open={open === 'identity'}
            title={`Gegevens van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <IdentityForm person={person} onDone={close} />
          </Sheet>
          <Sheet
            open={open === 'grant'}
            title={`Recht toekennen aan ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <GrantForm person={person} onDone={close} />
          </Sheet>
          <ConfirmDialog
            open={open === 'leave'}
            destructive
            text={`${person.name} inactief maken?`}
            supportingText={
              direct.error ??
              `${person.name} kan daarna niet meer inloggen en wordt niet meer ingezet. Bestaande inzet en afgesloten maanden blijven staan.`
            }
            confirmText="Maak inactief"
            onClose={close}
            onConfirm={() => direct.run(() => updatePerson(person.id, { is_active: false }))}
          />
          <ConfirmDialog
            open={open === 'unbind'}
            text={`De login van ${person.name} ontkoppelen?`}
            supportingText={
              direct.error ??
              'Doe dit als de persoon niet meer kan inloggen omdat het account bij de identiteitsprovider is vervangen. De volgende keer inloggen met hetzelfde e-mailadres koppelt het nieuwe account.'
            }
            confirmText="Ontkoppel login"
            onClose={close}
            onConfirm={() => direct.run(() => unbindLogin(person.id))}
          />
          <ConfirmDialog
            open={removedHire !== null}
            destructive
            text={`De inhuur via ${removedHire?.supplier ?? ''} verwijderen?`}
            supportingText={
              direct.error ??
              'De periode en de kostprijs verdwijnen. Was dit een vergissing in de invoer, leg de inhuur daarna opnieuw vast.'
            }
            confirmText="Verwijder inhuur"
            onClose={close}
            onConfirm={() => {
              const id = removedHire?.id;
              if (id) direct.run(() => removeHire(person.id, id));
            }}
          />
        </>
      ) : null}
    </nldd-simple-section>
  );
}

// -- deployment (class C) ------------------------------------------------------------------------

interface DeploymentProps {
  person: Person;
  row: BoardPerson | null;
  months: string[];
  currentMonth: string;
  loading: boolean;
}

/**
 * The work of this person over the months: a bar per assignment, the total
 * per month against 100 percent, and above it in words where it stands and
 * where it ends. The assignments are listed under the picture as links, which
 * is also how a keyboard reaches them.
 */
function DeploymentSection({ person, row, months, currentMonth, loading }: DeploymentProps) {
  const navigate = useNavigate();
  const standing = deploymentOf(person, row);
  const groups = row
    ? toTimeline(
        buildGroups(
          {
            months,
            current_month: currentMonth,
            persons: [row],
            open_roles: [],
            can_add: false,
          },
          'person',
          'all',
        ),
        months,
        currentMonth,
      ).map((group) => ({
        ...group,
        // The row is this person; what it totals is all their assignments.
        rows: group.rows.map((entry) => ({
          ...entry,
          label: 'Alle opdrachten',
          summary: '',
        })),
      }))
    : [];
  const bars = [...(row?.bars ?? [])].sort((a, b) => (a.end_date < b.end_date ? -1 : 1));
  const openAssignment = (id: string | undefined) => {
    if (id) navigate(assignmentTabPath(id, 'staffing'));
  };
  const first = months[0];
  const last = months[months.length - 1];

  return (
    <Section title="Inzet">
      <Stack gap="tight">
        <nldd-text weight="medium">{standing.now}</nldd-text>
        {standing.ahead ? <Quiet>{standing.ahead}</Quiet> : null}
        {standing.attention ? (
          <nldd-text size="sm" color="warning">
            {standing.attention}
          </nldd-text>
        ) : null}
      </Stack>
      {loading ? <Loading /> : null}
      {row && bars.length > 0 && first && last ? (
        <>
          <Timeline
            label={`Inzet van ${person.name}, ${formatMonth(first)} t/m ${formatMonth(last)}`}
            rowHeader="Inzet"
            months={months}
            currentMonth={currentMonth}
            groups={groups}
            selected={null}
            onBar={(bar) => openAssignment(bar.data.allocation?.assignment_id)}
            onCell={(entry, column) => {
              const here = barsInColumn(entry, column);
              if (here.length === 1) openAssignment(here[0]?.data.allocation?.assignment_id);
            }}
            legend={['filled', 'established', 'tentative', 'over']}
          />
          <nldd-table
            accessible-label={`Opdrachten van ${person.name}`}
            columns="minmax(200px,2fr) minmax(140px,1fr) 80px minmax(200px,1fr)"
            sm-columns="minmax(160px,1fr) 80px"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Opdracht" />
              <nldd-text-cell text="Rol" hide-below="md" />
              <nldd-text-cell text="Inzet" horizontal-alignment="right" />
              <nldd-text-cell text="Periode" hide-below="md" />
            </nldd-table-row>
            {bars.map((bar) => (
              <nldd-table-row key={bar.allocation_id}>
                <nldd-cell>
                  {bar.assignment_id ? (
                    <nldd-link
                      href={assignmentTabPath(bar.assignment_id, 'staffing')}
                      text={bar.assignment_name ?? 'Opdracht'}
                    />
                  ) : (
                    <nldd-text>{bar.assignment_name ?? 'Opdracht'}</nldd-text>
                  )}
                </nldd-cell>
                <nldd-text-cell text={bar.role ?? bar.line_description ?? ''} hide-below="md" />
                <nldd-text-cell text={formatPercent(bar.fte_pct)} horizontal-alignment="right" />
                <nldd-text-cell
                  hide-below="md"
                  text={formatPeriod(bar.start_date, bar.end_date)}
                  {...(bar.tentative ? { 'supporting-text': 'Onder voorbehoud' } : {})}
                />
              </nldd-table-row>
            ))}
          </nldd-table>
        </>
      ) : null}
      <nldd-link
        size="sm"
        href={`${PATHS.allocations}?persoon=${person.id}`}
        text="Plan op het Inzet-bord"
      />
    </Section>
  );
}

// -- declarability (class F) ---------------------------------------------------------------------

/**
 * The expected total of the year against the target, as one figure and one
 * bar: what is established in closed months, and what is still planned.
 */
function KpiSection({
  kpi,
  mayManage,
  onSet,
}: {
  kpi: Kpi;
  mayManage: boolean;
  onSet: () => void;
}) {
  const title = `Declarabiliteit ${kpi.year}`;
  if (kpi.unavailable_reason) {
    return (
      <Section title={title}>
        <EmptyNotice text={kpi.unavailable_reason} />
      </Section>
    );
  }
  const standing = kpiStanding(kpi);
  const total = kpi.realisation_cents ?? 0;
  const target = kpi.target_cents;
  return (
    <Section title={title}>
      <nldd-title
        size={3}
        overline="Verwacht totaal"
        text={formatEuro(kpi.realisation_cents)}
        supporting-text={
          target === null
            ? 'Nog geen target'
            : `Target ${formatEuro(target)}, ${formatPercent(kpi.target_pct)} van het jaar`
        }
      >
        {standing === 'none' ? (
          mayManage ? (
            <Button slot="end" size="sm" text="Stel target in" onClick={onSet} />
          ) : null
        ) : (
          <nldd-tag
            slot="end"
            color={standing === 'on-track' ? 'success' : 'warning'}
            icon={iconOf(standing === 'on-track' ? 'done' : 'attention')}
            text={KPI_STANDING_TEXT[standing]}
          />
        )}
      </nldd-title>
      <nldd-progress-bar
        variant="progress"
        size="lg"
        max={Math.max(target ?? 0, total, 1)}
        value-display="none"
        accessible-label={`${title}: ${formatEuro(kpi.realised_cents)} gerealiseerd en ${formatEuro(kpi.forecast_cents)} nog gepland${target === null ? '' : `, target ${formatEuro(target)}`}`}
      >
        <nldd-progress-bar-segment-indicator
          value={kpi.realised_cents ?? 0}
          color="donkerblauw"
          name="Gerealiseerd"
          tooltip-text={`Gerealiseerd ${formatEuro(kpi.realised_cents)}`}
        />
        <nldd-progress-bar-segment-indicator
          value={kpi.forecast_cents ?? 0}
          color="hemelblauw"
          name="Nog gepland"
          tooltip-text={`Nog gepland ${formatEuro(kpi.forecast_cents)}`}
        />
      </nldd-progress-bar>
      {/* The legend carries the values, so the bar is never colour alone. */}
      <nldd-container layout="wrap" gap="8" vertical-alignment="center">
        <nldd-tag color="donkerblauw" size="sm" text="Gerealiseerd" />
        <nldd-text>{formatEuro(kpi.realised_cents)}</nldd-text>
        <nldd-spacer size="8" />
        <nldd-tag color="hemelblauw" size="sm" text="Nog gepland" />
        <nldd-text>{formatEuro(kpi.forecast_cents)}</nldd-text>
      </nldd-container>
    </Section>
  );
}

// -- billing scale (class D) -----------------------------------------------------------------------

function periodState(entry: Scale, day: string): string {
  if (entry.valid_from > day) return 'Komt eraan';
  if (entry.valid_to === null || entry.valid_to >= day) return 'Geldt nu';
  return '';
}

/** The scale as periods, newest first; a promotion reads as the step it was. */
function ScaleSection({
  person,
  day,
  mayManage,
  onAdd,
}: {
  person: Person;
  day: string;
  mayManage: boolean;
  onAdd: () => void;
}) {
  const history = scaleHistory(person.scales ?? []);
  const rate =
    typeof person.monthly_rate_cents === 'number'
      ? `Categorie ${person.rate_category}, ${formatEuro(person.monthly_rate_cents)} per FTE per maand`
      : person.rate_category
        ? `Categorie ${person.rate_category}`
        : '';
  if (history.length === 0) {
    return (
      <Section title="Inzetschaal">
        <nldd-container layout="row" gap="16" vertical-alignment="center">
          <nldd-text>Nog geen inzetschaal</nldd-text>
          {mayManage ? <Button size="sm" text="Leg een schaal vast" onClick={onAdd} /> : null}
        </nldd-container>
      </Section>
    );
  }
  return (
    <Section title="Inzetschaal">
      <nldd-table
        accessible-label={`Inzetschaal van ${person.name}`}
        columns="minmax(200px,1fr) minmax(200px,1fr) 120px"
        sm-columns="minmax(140px,1fr) 110px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Schaal" />
          <nldd-text-cell text="Periode" hide-below="md" />
          <nldd-text-cell text="Status" />
        </nldd-table-row>
        {history.map((entry) => {
          const state = periodState(entry, day);
          const step =
            entry.previous !== null && entry.previous !== entry.billing_scale
              ? `Schaal ${entry.billing_scale}, was ${entry.previous}`
              : `Schaal ${entry.billing_scale}`;
          return (
            <nldd-table-row key={entry.id}>
              <nldd-text-cell
                text={step}
                {...(state === 'Geldt nu' && rate ? { 'supporting-text': rate } : {})}
              />
              <nldd-text-cell
                hide-below="md"
                text={formatPeriod(entry.valid_from, entry.valid_to)}
              />
              <nldd-cell>
                {state ? (
                  <nldd-badge color={state === 'Geldt nu' ? 'success' : 'neutral'} text={state} />
                ) : null}
              </nldd-cell>
            </nldd-table-row>
          );
        })}
      </nldd-table>
      <nldd-link size="sm" href={PATHS.rates} text="Tarieven per categorie" />
    </Section>
  );
}

// -- hire (class C, the cost class E) --------------------------------------------------------------

function HireSection({
  person,
  mayManage,
  onRemove,
}: {
  person: Person;
  mayManage: boolean;
  onRemove: (hire: Hire) => void;
}) {
  const hires = (person.hires ?? [])
    .filter((hire) => hire.supplier)
    .sort((a, b) => ((a.valid_from ?? '') < (b.valid_from ?? '') ? 1 : -1));
  const withCost = hires.some((hire) => typeof hire.cost_monthly_rate_cents === 'number');
  const columns = [
    'minmax(200px,1fr)',
    'minmax(200px,1fr)',
    ...(withCost ? ['minmax(140px,1fr)'] : []),
    ...(mayManage ? [ROW_ACTIONS_COLUMN] : []),
  ].join(' ');
  return (
    <Section title="Inhuur">
      <nldd-table accessible-label={`Inhuur van ${person.name}`} columns={columns}>
        <nldd-table-row slot="header">
          <nldd-text-cell text="Leverancier" />
          <nldd-text-cell text="Periode" />
          {withCost ? (
            <nldd-text-cell text="Kostprijs per FTE per maand" horizontal-alignment="right" />
          ) : null}
          {mayManage ? <nldd-cell /> : null}
        </nldd-table-row>
        {hires.map((hire) => (
          <nldd-table-row key={hire.id ?? hire.valid_from}>
            <nldd-text-cell
              text={hire.supplier ?? ''}
              {...(hire.contract_reference
                ? {
                    'supporting-text': `Contractkenmerk ${hire.contract_reference}`,
                  }
                : {})}
            />
            <nldd-text-cell text={formatPeriod(hire.valid_from, hire.valid_to ?? null)} />
            {withCost ? (
              <nldd-text-cell
                horizontal-alignment="right"
                text={
                  typeof hire.cost_monthly_rate_cents === 'number'
                    ? formatEuro(hire.cost_monthly_rate_cents)
                    : ''
                }
              />
            ) : null}
            {mayManage ? (
              <RowActions
                name={`de inhuur via ${hire.supplier ?? ''}`}
                actions={
                  hire.id
                    ? [
                        {
                          text: 'Verwijder deze inhuur',
                          destructive: true,
                          onSelect: () => onRemove(hire),
                        },
                      ]
                    : []
                }
              />
            ) : null}
          </nldd-table-row>
        ))}
      </nldd-table>
      {typeof person.margin_monthly_cents === 'number' ? (
        <Quiet>Marge nu {formatEuro(person.margin_monthly_cents)} per FTE per maand</Quiet>
      ) : null}
    </Section>
  );
}

// -- rights in grip --------------------------------------------------------------------------------

function grantLine(grant: FunctionGrant): string {
  const by = grant.granted_by_name
    ? `door ${grant.granted_by_name}`
    : 'bij de inrichting van de instantie';
  return `Sinds ${formatDate(grant.since)}, toegekend ${by}`;
}

/**
 * What the person may do in grip. A right is revoked from the row, after a
 * confirmation; granting one is an event in the menu of the page.
 */
function RightsSection({
  person,
  mayManage,
  onRevoke,
}: {
  person: Person;
  mayManage: boolean;
  onRevoke: (grant: FunctionGrant) => void;
}) {
  const grants = person.function_grants ?? [];
  return (
    <Section title="Rechten in grip">
      <nldd-table
        accessible-label={`Rechten in grip van ${person.name}`}
        columns={
          mayManage
            ? `minmax(200px,1fr) minmax(200px,1fr) ${ROW_ACTIONS_COLUMN}`
            : 'minmax(200px,1fr) minmax(200px,1fr)'
        }
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Recht" />
          <nldd-text-cell text="Toegekend" />
          {mayManage ? <nldd-cell /> : null}
        </nldd-table-row>
        {grants.map((grant) => {
          const sole = grant.function === 'beheerder' && person.is_sole_beheerder === true;
          const label = functionLabel(grant.function);
          return (
            <nldd-table-row key={grant.function}>
              <nldd-text-cell
                text={label}
                supporting-text={
                  FUNCTIONS.find((fn) => fn.id === grant.function)?.description ?? ''
                }
              />
              <nldd-text-cell
                text={grantLine(grant)}
                {...(sole
                  ? {
                      'supporting-text': 'De enige beheerder: dit recht blijft',
                    }
                  : {})}
              />
              {mayManage ? (
                <RowActions
                  name={`het recht ${label}`}
                  actions={
                    sole
                      ? []
                      : [
                          {
                            text: 'Trek in',
                            destructive: true,
                            confirm: {
                              text: `Het recht ${label} van ${person.name} intrekken?`,
                              supportingText: `${person.name} kan daarna niet meer wat dit recht toestaat. De intrekking komt met jouw naam in de auditlog.`,
                              confirmText: 'Trek in',
                            },
                            onSelect: () => onRevoke(grant),
                          },
                        ]
                  }
                />
              ) : null}
            </nldd-table-row>
          );
        })}
      </nldd-table>
    </Section>
  );
}
