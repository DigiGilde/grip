import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { assignmentPath } from '@/features/assignments/paths';
import { EmptyNotice, ErrorNotice, Loading } from '@/features/assignments/ui';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatEuro, formatFte, formatPercent, formatPeriod } from '@/lib/format';
import type {
  Billability,
  CostCoverage,
  Occupancy,
  OpenRoles,
  Pipeline,
  Steering,
  Turnover,
} from './api';
import { fetchSteering, reportKeys } from './api';
import { SERIES_COLORS } from './charts/colors';
import { MonthColumns } from './charts/MonthColumns';
import {
  MONTH_ABBREVIATIONS,
  QUOTE_STATUS_LABELS,
  VACANCY_STATUS_LABELS,
  monthAbbreviation,
  monthName,
  scopeNote,
} from './labels';
import { MoneyCell, NumberCell, ReportBlock } from './ui';

const euros = (cents: number) => formatEuro(cents);

function TurnoverBlock({ turnover, year }: { turnover: Turnover; year: number }) {
  const months = turnover.months;
  const hasPipeline = turnover.pipeline_cents > 0;
  return (
    <ReportBlock
      testId="turnover"
      title="Omzet per maand"
      note={scopeNote(
        turnover.scope,
        `Alle opdrachten in ${year}.`,
        `Alleen de opdrachten die je beheert, in ${year}.`,
      )}
    >
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
            label: 'Prognose',
            color: SERIES_COLORS.second,
            values: months.map((month) => month.forecast_cents),
          },
        ]}
      />
      <nldd-table
        accessible-label={`Omzet per maand in ${year}`}
        columns={`minmax(140px,1fr) 150px 150px${hasPipeline ? ' 170px' : ''}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Maand" />
          <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
          <nldd-text-cell text="Prognose" horizontal-alignment="right" />
          {hasPipeline && <nldd-text-cell text="Nog niet afgesproken" horizontal-alignment="right" />}
        </nldd-table-row>
        {months.map((month) => (
          <nldd-table-row key={month.month}>
            <nldd-text-cell text={monthName(month.month)} />
            <MoneyCell cents={month.realised_cents} />
            <MoneyCell cents={month.forecast_cents} />
            {hasPipeline && <MoneyCell cents={month.pipeline_cents} />}
          </nldd-table-row>
        ))}
        <nldd-table-row>
          <nldd-text-cell text="**Totaal**" />
          <MoneyCell cents={turnover.realised_cents} bold />
          <MoneyCell cents={turnover.forecast_cents} bold />
          {hasPipeline && <MoneyCell cents={turnover.pipeline_cents} bold />}
        </nldd-table-row>
      </nldd-table>
      <nldd-text size="sm" color="secondary">
        Gerealiseerd is de vastgestelde inzet van afgesloten maanden. Prognose is de geplande inzet van open maanden op opdrachten met akkoord.
      </nldd-text>
      {turnover.unpriced_assignments.length > 0 && (
        <nldd-banner
          variant="warning"
          size="sm"
          text={`Niet meegeteld, omdat de bedragen niet te berekenen zijn: ${turnover.unpriced_assignments.join(', ')}.`}
        />
      )}
    </ReportBlock>
  );
}

/** The months in which a person is above 100 percent, in words. */
function overMonths(months: (string | null)[]): string {
  const over = months
    .map((value, index) => (value !== null && Number(value) > 100 ? MONTH_ABBREVIATIONS[index] : null))
    .filter((name): name is (typeof MONTH_ABBREVIATIONS)[number] => name !== null);
  return over.join(', ');
}

function OccupancyBlock({ occupancy, year }: { occupancy: Occupancy; year: number }) {
  const months = occupancy.months;
  return (
    <ReportBlock
      testId="occupancy"
      title="Bezetting"
      note={scopeNote(
        occupancy.scope,
        `Iedereen die in ${year} inzetbaar is. Beschikbaar is 1 FTE per persoon per maand.`,
        `Alleen de personen van wie je de inzet mag zien. Beschikbaar is 1 FTE per persoon per maand.`,
      )}
    >
      <MonthColumns
        title={`Bezetting per maand in ${year}`}
        months={months.map((month) => month.month)}
        formatValue={(value) => formatPercent(value)}
        reference={{ value: 100, label: '100%' }}
        series={[
          {
            key: 'occupancy',
            label: 'Bezetting',
            color: SERIES_COLORS.first,
            values: months.map((month) => (month.pct === null ? 0 : Number(month.pct))),
          },
        ]}
      />
      <nldd-table
        accessible-label={`Bezetting per maand in ${year}`}
        columns="minmax(140px,1fr) 110px 110px 110px 110px 110px 110px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Maand" />
          <nldd-text-cell text="Ingezet (FTE)" horizontal-alignment="right" />
          <nldd-text-cell text="Beschikbaar (FTE)" horizontal-alignment="right" />
          <nldd-text-cell text="Bezetting" horizontal-alignment="right" />
          <nldd-text-cell text="Onder 100%" horizontal-alignment="right" />
          <nldd-text-cell text="Op 100%" horizontal-alignment="right" />
          <nldd-text-cell text="Boven 100%" horizontal-alignment="right" />
        </nldd-table-row>
        {months.map((month) => (
          <nldd-table-row key={month.month}>
            <nldd-text-cell text={monthName(month.month)} />
            <NumberCell text={formatFte(month.allocated_fte)} />
            <NumberCell text={formatFte(month.available_fte)} />
            <NumberCell text={formatPercent(month.pct)} />
            <NumberCell text={String(month.under)} />
            <NumberCell text={String(month.full)} />
            <NumberCell text={String(month.over)} />
          </nldd-table-row>
        ))}
      </nldd-table>
      <nldd-table
        accessible-label={`Bezetting per persoon in ${year}, in procenten`}
        columns="minmax(170px,1.5fr) repeat(12, 62px) 90px minmax(120px,1fr)"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Persoon" />
          {months.map((month) => (
            <nldd-text-cell
              key={month.month}
              text={monthAbbreviation(month.month)}
              horizontal-alignment="right"
            />
          ))}
          <nldd-text-cell text="Gemiddeld" horizontal-alignment="right" />
          <nldd-text-cell text="Boven 100% in" />
        </nldd-table-row>
        {occupancy.persons.map((person) => (
          <nldd-table-row key={person.person_id}>
            <nldd-text-cell text={person.person_name} />
            {(person.months ?? []).map((value, index) => (
              <nldd-text-cell
                key={months[index]?.month ?? index}
                text={value === null ? '' : formatPercent(value)}
                horizontal-alignment="right"
                {...(value !== null && Number(value) > 100 ? { color: 'critical' } : {})}
              />
            ))}
            <NumberCell text={formatPercent(person.average_pct)} />
            <nldd-text-cell text={overMonths(person.months ?? [])} />
          </nldd-table-row>
        ))}
      </nldd-table>
      <nldd-text size="sm" color="secondary">
        Een lege maand betekent dat iemand in die maand niet inzetbaar was. Afgesloten maanden tellen met de vastgestelde inzet.
      </nldd-text>
    </ReportBlock>
  );
}

function PipelineBlock({ pipeline, year }: { pipeline: Pipeline; year: number }) {
  return (
    <ReportBlock
      testId="pipeline"
      title="Offertes"
      note={scopeNote(
        pipeline.scope,
        `Alle offertes die in ${year} zijn uitgegeven.`,
        `Offertes van de opdrachten die je beheert, uitgegeven in ${year}.`,
      )}
    >
      <nldd-table accessible-label={`Offertes per status in ${year}`} columns="minmax(220px,1fr) 110px 170px">
        <nldd-table-row slot="header">
          <nldd-text-cell text="Status" />
          <nldd-text-cell text="Aantal" horizontal-alignment="right" />
          <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
        </nldd-table-row>
        {pipeline.statuses.map((status) => (
          <nldd-table-row key={status.status}>
            <nldd-text-cell text={QUOTE_STATUS_LABELS[status.status] ?? status.status} />
            <NumberCell text={String(status.count)} />
            <MoneyCell cents={status.total_cents} />
          </nldd-table-row>
        ))}
      </nldd-table>
      {pipeline.waiting.length > 0 && (
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
            {pipeline.waiting.map((quote) => (
              <nldd-table-row key={quote.quote_id}>
                <nldd-cell>
                  <nldd-link href={assignmentPath(quote.assignment_id)} text={quote.assignment_name} />
                </nldd-cell>
                <nldd-text-cell text={quote.client_name ?? ''} />
                <nldd-text-cell text={formatDate(quote.issued_at)} />
                <nldd-text-cell text={formatDate(quote.valid_until)} />
                <MoneyCell cents={quote.total_cents} />
              </nldd-table-row>
            ))}
          </nldd-table>
        </RouterLinks>
      )}
    </ReportBlock>
  );
}

function CostsBlock({ costs, year }: { costs: CostCoverage; year: number }) {
  return (
    <ReportBlock
      testId="costs"
      title="Kosten en dekking"
      note={scopeNote(
        costs.scope,
        `Alle kostenposten, met de facturen van ${year}.`,
        `De kostenposten die door je eigen opdrachten worden gedekt, met de facturen van ${year}.`,
      )}
    >
      {costs.items.length === 0 ? (
        <EmptyNotice text="Er zijn geen kostenposten" />
      ) : (
        <nldd-table
          accessible-label={`Kosten en dekking in ${year}`}
          columns="minmax(220px,1.5fr) 150px 150px 150px"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Kostenpost" />
            <nldd-text-cell text="Prognose" horizontal-alignment="right" />
            <nldd-text-cell text="Gedekt" horizontal-alignment="right" />
            <nldd-text-cell text="Ongedekt" horizontal-alignment="right" />
          </nldd-table-row>
          {costs.items.map((item) => (
            <nldd-table-row key={item.cost_item_id}>
              <nldd-text-cell text={item.description} />
              <MoneyCell cents={item.forecast_cents} />
              <MoneyCell
                cents={item.covered_cents}
                {...(item.covered_cents === null ? { note: 'Meer dan 100% gedekt' } : {})}
              />
              <MoneyCell cents={item.uncovered_cents} />
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

function BillabilityBlock({ billability, year }: { billability: Billability; year: number }) {
  return (
    <ReportBlock
      testId="billability"
      title="Declarabiliteit"
      note={scopeNote(
        billability.scope,
        `Iedereen met een target of inzet in ${year}.`,
        `Alleen de personen van wie je de KPI mag zien, in ${year}.`,
      )}
    >
      <nldd-table
        accessible-label={`Declarabiliteit per persoon in ${year}`}
        columns="minmax(180px,1.5fr) 100px 150px 150px 150px 150px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Persoon" />
          <nldd-text-cell text="Target" horizontal-alignment="right" />
          <nldd-text-cell text="Targetbedrag" horizontal-alignment="right" />
          <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
          <nldd-text-cell text="Prognose" horizontal-alignment="right" />
          <nldd-text-cell text="Ten opzichte van target" horizontal-alignment="right" />
        </nldd-table-row>
        {billability.persons.map((person) => {
          const known = person.target_cents !== null && person.realisation_cents !== null;
          const gap = known ? (person.realisation_cents ?? 0) - (person.target_cents ?? 0) : null;
          return (
            <nldd-table-row key={person.person_id}>
              <nldd-text-cell
                text={person.person_name}
                {...(person.unavailable_reason ? { 'supporting-text': person.unavailable_reason } : {})}
              />
              <NumberCell text={formatPercent(person.target_pct)} />
              <MoneyCell cents={person.target_cents} />
              <MoneyCell cents={person.realised_cents} />
              <MoneyCell cents={person.forecast_cents} />
              <MoneyCell
                cents={gap}
                {...(gap !== null && gap < 0 ? { note: 'Onder target' } : {})}
                {...(gap !== null && gap >= 0 ? { note: 'Op of boven target' } : {})}
              />
            </nldd-table-row>
          );
        })}
        <nldd-table-row>
          <nldd-text-cell text="**Totaal**" />
          <nldd-text-cell />
          <MoneyCell cents={billability.target_cents} bold />
          <MoneyCell cents={billability.realised_cents} bold />
          <MoneyCell cents={billability.forecast_cents} bold />
          <nldd-text-cell />
        </nldd-table-row>
      </nldd-table>
    </ReportBlock>
  );
}

function OpenRolesBlock({ openRoles }: { openRoles: OpenRoles }) {
  return (
    <ReportBlock
      testId="open-roles"
      title="Open rollen"
      note={scopeNote(
        openRoles.scope,
        'Alle rollen die nu niet of niet helemaal zijn ingevuld.',
        'Rollen op je eigen opdrachten die nu niet of niet helemaal zijn ingevuld.',
      )}
    >
      {openRoles.roles.length === 0 ? (
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

const hasBlocks = (steering: Steering) =>
  Boolean(
    steering.turnover ||
      steering.occupancy ||
      steering.pipeline ||
      steering.costs ||
      steering.billability ||
      steering.open_roles,
  );

/** The steering overview of a year. Only the blocks the API sent are drawn. */
export function SteeringView({ year }: { year: string }) {
  const query = useQuery({ queryKey: reportKeys.steering(year), queryFn: () => fetchSteering(year) });
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  const steering = query.data;
  if (!hasBlocks(steering)) {
    return (
      <EmptyNotice
        text="Er is voor jou geen sturingsinformatie"
        supportingText="Je ziet hier de cijfers van opdrachten die je beheert en van personen aan wie je leiding geeft."
      />
    );
  }
  return (
    <nldd-container gap="32">
      {steering.turnover && <TurnoverBlock turnover={steering.turnover} year={steering.year} />}
      {steering.occupancy && <OccupancyBlock occupancy={steering.occupancy} year={steering.year} />}
      {steering.pipeline && <PipelineBlock pipeline={steering.pipeline} year={steering.year} />}
      {steering.costs && <CostsBlock costs={steering.costs} year={steering.year} />}
      {steering.billability && (
        <BillabilityBlock billability={steering.billability} year={steering.year} />
      )}
      {steering.open_roles && <OpenRolesBlock openRoles={steering.open_roles} />}
    </nldd-container>
  );
}
