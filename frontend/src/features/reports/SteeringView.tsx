import { assignmentPath } from '@/features/assignments/paths';
import { EmptyNotice } from '@/ui/layout';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatEuro, formatFte, formatPercent, formatPeriod } from '@/lib/format';
import type { Billability, CostCoverage, OpenRoles, Pipeline, Turnover } from './api';
import { SERIES_COLORS } from './charts/colors';
import { MonthColumns } from './charts/MonthColumns';
import { VACANCY_STATUS_LABELS, monthName, scopeNote } from './labels';
import { Disclosure, Figures, MoneyCell, NumberCell, ReportBlock } from './ui';

const euros = (cents: number) => formatEuro(cents);

const count = (number: number, one: string, many: string) =>
  `${number} ${number === 1 ? one : many}`;

export function TurnoverBlock({
  turnover,
  year,
  bare,
}: {
  turnover: Turnover;
  year: number;
  bare?: boolean;
}) {
  const months = turnover.months ?? [];
  const hasPipeline = turnover.pipeline_cents > 0;
  const hasVerbal = turnover.verbal_cents > 0;
  const unpriced = turnover.unpriced_assignments ?? [];
  const figures = turnover.figures;
  return (
    <ReportBlock
      bare={bare}
      testId="turnover"
      title="Omzet"
      note={scopeNote(
        turnover.scope,
        `Alle opdrachten in ${year}.`,
        `Alleen de opdrachten die je beheert, in ${year}.`,
      )}
    >
      <Figures
        label="Omzet in het kort"
        figures={[
          {
            label: 'Verwacht totaal',
            value: euros(figures.expected_total_cents),
            ...(figures.overrun
              ? {
                  attention: 'Boven de begroting',
                  detail: `afwijking ${euros(figures.variance_cents)} op ${euros(figures.budgeted_cents)} begroot`,
                }
              : {
                  detail: `van ${euros(figures.budgeted_cents)} begroot, afwijking ${euros(figures.variance_cents)}`,
                }),
          },
          {
            label: 'Gerealiseerd',
            value: euros(figures.realised_total_cents),
            detail:
              figures.realised_pct === null
                ? 'afgesloten maanden en gemaakte kosten'
                : `uitputting ${formatPercent(figures.realised_pct)} van de begroting`,
            quiet: figures.realised_total_cents === 0,
          },
          {
            label: 'Nog gepland',
            value: euros(turnover.forecast_cents),
            detail: hasVerbal
              ? `waarvan ${euros(turnover.verbal_cents)} op mondeling akkoord`
              : 'geplande inzet van open maanden, met akkoord',
            quiet: turnover.forecast_cents === 0,
          },
          {
            label: 'Nog niet afgesproken',
            value: euros(turnover.pipeline_cents),
            detail: 'geplande inzet zonder akkoord, telt niet mee',
            quiet: !hasPipeline,
          },
        ]}
      />
      {unpriced.length > 0 && (
        <nldd-banner
          variant="warning"
          size="sm"
          text={`Niet meegeteld, omdat de bedragen niet te berekenen zijn: ${unpriced.join(', ')}.`}
        />
      )}
      <MonthColumns
        title={`Omzet per maand in ${year}`}
        months={months.map((month) => month.month)}
        formatValue={euros}
        series={[
          {
            key: 'realised',
            label: 'Gerealiseerd',
            color: SERIES_COLORS.first,
            values: months.map((month) => month.realised_cents),
          },
          {
            key: 'forecast',
            label: 'Nog gepland',
            color: SERIES_COLORS.second,
            values: months.map((month) => month.forecast_cents),
          },
        ]}
      />
      <Disclosure summary="Bedragen per maand als tabel">
        <nldd-table
          accessible-label={`Omzet per maand in ${year}`}
          columns={`minmax(140px,1fr) 150px 150px${hasVerbal ? ' 190px' : ''}${hasPipeline ? ' 170px' : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Maand" />
            <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
            <nldd-text-cell text="Nog gepland" horizontal-alignment="right" />
            {hasVerbal && (
              <nldd-text-cell text="Waarvan mondeling akkoord" horizontal-alignment="right" />
            )}
            {hasPipeline && <nldd-text-cell text="Nog niet afgesproken" horizontal-alignment="right" />}
          </nldd-table-row>
          {months.map((month) => (
            <nldd-table-row key={month.month}>
              <nldd-text-cell text={monthName(month.month)} />
              <MoneyCell cents={month.realised_cents} />
              <MoneyCell cents={month.forecast_cents} />
              {hasVerbal && <MoneyCell cents={month.verbal_cents} />}
              {hasPipeline && <MoneyCell cents={month.pipeline_cents} />}
            </nldd-table-row>
          ))}
          <nldd-table-row>
            <nldd-text-cell text="**Totaal**" />
            <MoneyCell cents={turnover.realised_cents} bold />
            <MoneyCell cents={turnover.forecast_cents} bold />
            {hasVerbal && <MoneyCell cents={turnover.verbal_cents} bold />}
            {hasPipeline && <MoneyCell cents={turnover.pipeline_cents} bold />}
          </nldd-table-row>
        </nldd-table>
      </Disclosure>
    </ReportBlock>
  );
}

export function PipelineBlock({
  pipeline,
  year,
  bare,
}: {
  pipeline: Pipeline;
  year: number;
  bare?: boolean;
}) {
  const byStatus = new Map((pipeline.statuses ?? []).map((status) => [status.status, status]));
  const of = (status: string) => byStatus.get(status) ?? { status, count: 0, total_cents: 0 };
  const issued = of('issued');
  const accepted = of('accepted');
  const rejected = of('rejected');
  const superseded = of('superseded');
  const waiting = pipeline.waiting ?? [];
  return (
    <ReportBlock
      bare={bare}
      testId="pipeline"
      title="Offertes"
      note={scopeNote(
        pipeline.scope,
        `Alle offertes die in ${year} zijn uitgegeven.`,
        `Offertes van de opdrachten die je beheert, uitgegeven in ${year}.`,
      )}
    >
      <Figures
        label="Offertes in het kort"
        figures={[
          {
            label: 'Wacht op akkoord',
            value: euros(issued.total_cents),
            detail: count(issued.count, 'offerte', 'offertes'),
            quiet: issued.count === 0,
          },
          {
            label: 'Akkoord',
            value: euros(accepted.total_cents),
            detail: count(accepted.count, 'offerte', 'offertes'),
            quiet: accepted.count === 0,
          },
          {
            label: 'Afgewezen',
            value: euros(rejected.total_cents),
            detail: count(rejected.count, 'offerte', 'offertes'),
            quiet: rejected.count === 0,
          },
        ]}
      />
      {waiting.length === 0 && (
        <EmptyNotice text="Er wacht geen offerte op akkoord" />
      )}
      {superseded.count > 0 && (
        <nldd-text size="sm" color="secondary">
          {count(superseded.count, 'offerte is', 'offertes zijn')} vervangen door een nieuwe en
          {superseded.count === 1 ? ' telt' : ' tellen'} hierboven niet mee.
        </nldd-text>
      )}
      {waiting.length > 0 && (
        <RouterLinks>
          <nldd-table
            accessible-label="Offertes die wachten op akkoord"
            columns="minmax(200px,1.5fr) minmax(160px,1fr) 150px 150px 150px"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Wacht op akkoord" />
              <nldd-text-cell text="Opdrachtgever" />
              <nldd-text-cell text="Uitgegeven" />
              <nldd-text-cell text="Geldig tot" />
              <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
            </nldd-table-row>
            {waiting.map((quote) => (
              <nldd-table-row key={quote.quote_id}>
                <nldd-cell>
                  <nldd-link href={assignmentPath(quote.assignment_id)} text={quote.assignment_name} />
                </nldd-cell>
                <nldd-text-cell text={quote.client_name ?? ''} />
                <nldd-text-cell text={formatDate(quote.issued_at)} />
                <nldd-text-cell
                  text={quote.valid_until ? formatDate(quote.valid_until) : 'Geen einddatum'}
                  {...(quote.valid_until ? {} : { color: 'secondary' })}
                />
                <MoneyCell cents={quote.total_cents} />
              </nldd-table-row>
            ))}
          </nldd-table>
        </RouterLinks>
      )}
    </ReportBlock>
  );
}

export function CostsBlock({
  costs,
  year,
  bare,
}: {
  costs: CostCoverage;
  year: number;
  bare?: boolean;
}) {
  return (
    <ReportBlock
      bare={bare}
      testId="costs"
      title="Kosten en dekking"
      note={scopeNote(
        costs.scope,
        `Alle kostenposten, met de facturen van ${year}.`,
        `De kostenposten die door je eigen opdrachten worden gedekt, met de facturen van ${year}.`,
      )}
    >
      <Figures
        label="Kosten in het kort"
        figures={[
          {
            label: 'Ongedekt',
            value: euros(costs.uncovered_cents),
            ...(costs.uncovered_cents > 0
              ? { attention: 'Geen begrotingsregel dekt dit', detail: `van ${euros(costs.forecast_cents)} verwachte kosten` }
              : { quiet: true, detail: 'alle kosten zijn gedekt' }),
          },
          { label: 'Verwachte kosten', value: euros(costs.forecast_cents), quiet: costs.forecast_cents === 0 },
          { label: 'Gedekt door begrotingsregels', value: euros(costs.covered_cents), quiet: costs.covered_cents === 0 },
        ]}
      />
      {(costs.items ?? []).length === 0 ? (
        <EmptyNotice text="Er zijn geen kostenposten" />
      ) : (
        <nldd-table
          accessible-label={`Kosten en dekking in ${year}`}
          columns="minmax(220px,1.5fr) 150px 150px 150px"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Kostenpost" />
            <nldd-text-cell text="Nog gepland" horizontal-alignment="right" />
            <nldd-text-cell text="Gedekt" horizontal-alignment="right" />
            <nldd-text-cell text="Ongedekt" horizontal-alignment="right" />
          </nldd-table-row>
          {(costs.items ?? []).map((item) => (
            <nldd-table-row key={item.cost_item_id}>
              <nldd-text-cell text={item.description} />
              <MoneyCell cents={item.forecast_cents} />
              <MoneyCell
                cents={item.covered_cents}
                {...(item.covered_cents === null ? { note: 'Meer dan 100% gedekt' } : {})}
              />
              <MoneyCell
                cents={item.uncovered_cents}
                {...((item.uncovered_cents ?? 0) > 0 ? { critical: true, note: 'Ongedekt' } : {})}
              />
            </nldd-table-row>
          ))}
          <nldd-table-row>
            <nldd-text-cell text="**Totaal**" />
            <MoneyCell cents={costs.forecast_cents} bold />
            <MoneyCell cents={costs.covered_cents} bold />
            <MoneyCell cents={costs.uncovered_cents} bold />
          </nldd-table-row>
        </nldd-table>
      )}
    </ReportBlock>
  );
}

/** Below target first, then the others, then whoever has no target. */
function byTargetGap(persons: Billability['persons']) {
  const gap = (person: Billability['persons'][number]) =>
    person.target_cents === null || person.realisation_cents === null
      ? Number.POSITIVE_INFINITY
      : person.realisation_cents - person.target_cents;
  return [...persons].sort(
    (a, b) => gap(a) - gap(b) || a.person_name.localeCompare(b.person_name, 'nl'),
  );
}

export function BillabilityBlock({
  billability,
  year,
  bare,
}: {
  billability: Billability;
  year: number;
  bare?: boolean;
}) {
  const persons = byTargetGap(billability.persons ?? []);
  const below = billability.below_target_count;
  return (
    <ReportBlock
      bare={bare}
      testId="billability"
      title="Declarabiliteit"
      note={scopeNote(
        billability.scope,
        `Iedereen met een target of inzet in ${year}.`,
        `Alleen de personen van wie je de KPI mag zien, in ${year}.`,
      )}
    >
      <Figures
        label="Declarabiliteit in het kort"
        figures={[
          below > 0
            ? {
                label: 'Verwacht onder target',
                value: count(below, 'persoon', 'mensen'),
                attention: 'Haalt het target niet',
                detail: `van ${billability.with_target_count} met een target`,
              }
            : {
                label: 'Verwacht onder target',
                value: 'Niemand',
                detail: `van ${billability.with_target_count} met een target`,
                quiet: true,
              },
          {
            label: `Verwacht in ${year}`,
            value: euros(billability.realisation_cents),
            detail: `${euros(billability.realised_cents)} gerealiseerd, ${euros(billability.forecast_cents)} nog gepland`,
          },
          {
            label: 'Target samen',
            value: euros(billability.target_cents),
            quiet: billability.target_cents === 0,
          },
        ]}
      />
      <nldd-table
        accessible-label={`Declarabiliteit per persoon in ${year}`}
        columns="minmax(180px,1.5fr) 190px 100px 150px 150px 150px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Persoon" />
          <nldd-text-cell text="Ten opzichte van target" horizontal-alignment="right" />
          <nldd-text-cell text="Target" horizontal-alignment="right" />
          <nldd-text-cell text="Targetbedrag" horizontal-alignment="right" />
          <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
          <nldd-text-cell text="Nog gepland" horizontal-alignment="right" />
        </nldd-table-row>
        {persons.map((person) => {
          const known = person.target_cents !== null && person.realisation_cents !== null;
          const gap = known ? (person.realisation_cents ?? 0) - (person.target_cents ?? 0) : null;
          return (
            <nldd-table-row key={person.person_id}>
              <nldd-text-cell
                text={person.person_name}
                {...(person.unavailable_reason ? { 'supporting-text': person.unavailable_reason } : {})}
              />
              {gap === null ? (
                <NumberCell text={person.unavailable_reason ? 'Niet berekend' : 'Geen target'} muted />
              ) : (
                <MoneyCell
                  cents={gap}
                  {...(gap < 0
                    ? { critical: true, note: 'Onder target' }
                    : { note: 'Op of boven target' })}
                />
              )}
              <NumberCell text={formatPercent(person.target_pct)} />
              <MoneyCell cents={person.target_cents} />
              <MoneyCell cents={person.realised_cents} />
              <MoneyCell cents={person.forecast_cents} />
            </nldd-table-row>
          );
        })}
        <nldd-table-row>
          <nldd-text-cell text="**Totaal**" />
          <nldd-text-cell />
          <nldd-text-cell />
          <MoneyCell cents={billability.target_cents} bold />
          <MoneyCell cents={billability.realised_cents} bold />
          <MoneyCell cents={billability.forecast_cents} bold />
        </nldd-table-row>
      </nldd-table>
    </ReportBlock>
  );
}

export function OpenRolesBlock({ openRoles, bare }: { openRoles: OpenRoles; bare?: boolean }) {
  return (
    <ReportBlock
      bare={bare}
      testId="open-roles"
      title="Open rollen"
      note={scopeNote(
        openRoles.scope,
        'Alle rollen die nu niet of niet helemaal zijn ingevuld.',
        'Rollen op je eigen opdrachten die nu niet of niet helemaal zijn ingevuld.',
      )}
    >
      <Figures
        label="Open rollen in het kort"
        figures={[
          {
            label: 'Nog in te vullen',
            value: `${formatFte(openRoles.unfilled_fte)} FTE`,
            detail: count((openRoles.roles ?? []).length, 'rol', 'rollen'),
            quiet: (openRoles.roles ?? []).length === 0,
          },
          {
            label: 'Zonder vacature',
            value: count(
              (openRoles.roles ?? []).filter((role) => !role.vacancy_status).length,
              'rol',
              'rollen',
            ),
            quiet: (openRoles.roles ?? []).every((role) => role.vacancy_status),
          },
        ]}
      />
      {(openRoles.roles ?? []).length === 0 ? (
        <EmptyNotice text="Er zijn geen open rollen" />
      ) : (
        <RouterLinks>
          <nldd-table
            accessible-label="Open rollen"
            columns="minmax(180px,1.5fr) minmax(160px,1fr) 100px minmax(200px,1fr) minmax(170px,1fr)"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Opdracht" />
              <nldd-text-cell text="Rol" />
              <nldd-text-cell text="Open (FTE)" horizontal-alignment="right" />
              <nldd-text-cell text="Periode" />
              <nldd-text-cell text="Vacature" />
            </nldd-table-row>
            {openRoles.roles.map((role, index) => (
              <nldd-table-row key={`${role.budget_line_id ?? 'los'}-${index}`}>
                <nldd-cell>
                  {role.assignment_id ? (
                    <nldd-link
                      href={assignmentPath(role.assignment_id)}
                      text={role.assignment_name ?? ''}
                    />
                  ) : (
                    <nldd-text color="secondary">Niet aan een opdracht gekoppeld</nldd-text>
                  )}
                </nldd-cell>
                <nldd-text-cell text={role.description} />
                <NumberCell text={formatFte(role.unfilled_fte)} />
                <nldd-text-cell text={formatPeriod(role.start_date, role.end_date)} />
                <nldd-text-cell
                  text={
                    role.vacancy_status
                      ? (VACANCY_STATUS_LABELS[role.vacancy_status] ?? role.vacancy_status)
                      : 'Geen vacature'
                  }
                  {...(role.vacancy_status ? {} : { color: 'secondary' })}
                />
              </nldd-table-row>
            ))}
            <nldd-table-row>
              <nldd-text-cell text="**Totaal**" />
              <nldd-text-cell />
              <NumberCell text={`**${formatFte(openRoles.unfilled_fte)}**`} />
              <nldd-text-cell />
              <nldd-text-cell />
            </nldd-table-row>
          </nldd-table>
        </RouterLinks>
      )}
    </ReportBlock>
  );
}
