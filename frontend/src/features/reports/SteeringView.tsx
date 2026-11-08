import { assignmentPath } from '@/features/assignments/paths';
import { EmptyNotice } from '@/ui/layout';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatEuro, formatPercent } from '@/lib/format';
import type { Pipeline, Turnover } from './api';
import { SERIES_COLORS } from './charts/colors';
import { MonthColumns } from './charts/MonthColumns';
import { monthName, scopeNote } from './labels';
import { Disclosure, Figures, MoneyCell, ReportBlock } from './ui';

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
            label: 'Gerealiseerde inzet',
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
            <nldd-text-cell text="Gerealiseerde inzet" horizontal-alignment="right" />
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

export function PotentialBlock({
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
      testId="potential"
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
            sm-columns="minmax(130px,1fr) 100px 100px"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Wacht op akkoord" />
              <nldd-text-cell hide-below="md" text="Opdrachtgever" />
              <nldd-text-cell hide-below="md" text="Uitgegeven" />
              <nldd-text-cell text="Geldig tot" />
              <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
            </nldd-table-row>
            {waiting.map((quote) => (
              <nldd-table-row key={quote.quote_id}>
                <nldd-cell>
                  <nldd-link href={assignmentPath(quote.assignment_id)} text={quote.assignment_name} />
                </nldd-cell>
                <nldd-text-cell hide-below="md" text={quote.client_name ?? ''} />
                <nldd-text-cell hide-below="md" text={formatDate(quote.issued_at)} />
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
