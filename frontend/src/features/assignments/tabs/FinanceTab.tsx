import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { IconCell } from '@/ui/Icon';
import {
  KeyFigures,
  LoadError,
  Quiet,
  Section,
  type Signal as SignalItem,
  SignalList,
  Stack,
} from '@/ui/layout';
import type { YearChoice } from '@/features/overview/api';
import {
  YEAR_FILTER_LABEL,
  periodLabel,
  startingYear,
  yearOptions,
} from '@/features/overview/years';
import { MonthColumns } from '@/features/reports/charts/MonthColumns';
import { SERIES_COLORS } from '@/features/reports/charts/colors';
import { formatEuro, formatMonth, formatPercent, formatPeriod } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import {
  fetchAssignmentFinance,
  financeCsvPath,
  financeKeys,
  type AssignmentFinance,
  type FinanceLine,
} from '../financeApi';
import { FIGURE_LABELS, referenceText, rateCauseText, signalText } from '../financeText';
import { FIGURE_COLUMNS, FigureCells, FigureHeaderCells } from '../FigureCells';
import { useRateCards } from '../rateText';
import { useAssignmentShell } from '../shell';
import { EmptyNotice, Loading } from '../ui';

// The chevron turns with the row. Spread as a plain attribute because the
// package types do not list it on the icon cell.
const DISCLOSURE: object = { disclosure: '' };

/** Where the quote, the delivery and the invoices stand, as a few figures. */
function AgreementFigures({ finance }: { finance: AssignmentFinance }) {
  const key = finance.key_figures;
  const money = (cents: number | null) => (cents === null ? 'Niet bekend' : formatEuro(cents));
  const differs = key.agreed_minus_budgeted_cents;
  return (
    <Section title="Offerte en facturering">
      <KeyFigures
        label="Offerte, aangeleverd en gefactureerd"
        figures={[
          {
            label: 'Offerte met akkoord',
            value: key.agreed_cents === null ? 'Nog geen akkoord' : formatEuro(key.agreed_cents),
            // Said only when it differs; "gelijk" is no news.
            ...(differs !== null && differs !== 0
              ? {
                  detail:
                    differs > 0
                      ? `${formatEuro(differs)} hoger dan de begroting`
                      : `${formatEuro(-differs)} lager dan de begroting`,
                }
              : {}),
          },
          { label: 'Gerealiseerde inzet', value: money(key.realised_cents) },
          { label: 'Aangeleverd', value: formatEuro(key.delivered_cents) },
          { label: 'Nog aan te leveren', value: money(key.to_deliver_cents) },
          { label: 'Gefactureerd', value: formatEuro(key.invoiced_cents) },
          {
            label: 'Nog te factureren',
            value: formatEuro(key.to_invoice_cents),
            ...(key.to_invoice_cents < 0
              ? { detail: 'Meer gefactureerd dan aangeleverd', critical: true }
              : {}),
          },
        ]}
      />
    </Section>
  );
}

const TONE = { critical: 'critical', warning: 'warning', neutral: 'info' } as const;

/** What asks for attention, first on the tab: one list, the worst marked. */
function Signals({ finance }: { finance: AssignmentFinance }) {
  if (finance.signals.length === 0) return null;
  const signals: SignalItem[] = finance.signals.map((signal, index) => {
    const { variant, text } = signalText(signal, finance.free_room_threshold_pct);
    return {
      key: `${signal.kind}-${signal.budget_line_id ?? index}`,
      text,
      tone: TONE[variant as keyof typeof TONE] ?? 'info',
    };
  });
  return (
    <Section title="Aandachtspunten">
      <SignalList label="Aandachtspunten" signals={signals} />
    </Section>
  );
}

/** One line that opens to the amounts behind it. */
function LineDetail({ line }: { line: FinanceLine }) {
  const [expanded, setExpanded] = useState(false);
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', (event) => {
    // Only the row itself toggles; a click inside the opened detail does not.
    const target = event.target as Element | null;
    if (target?.closest('nldd-list-item') === ref.current) setExpanded((open) => !open);
  });
  const figures = line.figures;
  const summary = figures
    ? `${formatEuro(figures.realised_cents)} gerealiseerd, ${formatEuro(figures.planned_cents)} nog gepland, ${formatEuro(figures.costs_cents)} kosten`
    : (line.pricing_error ?? 'Niet berekend');
  return (
    <nldd-list-item ref={ref} button expanded={orUndef(expanded)}>
      <IconCell concept="open" {...DISCLOSURE} />
      <nldd-spacer-cell size="8" />
      <nldd-text-cell text={line.description} supporting-text={summary} />
      <nldd-text-cell
        width="fit-content"
        text={figures ? formatEuro(figures.expected_total_cents) : ''}
        supporting-text={figures ? FIGURE_LABELS.expected : ''}
        horizontal-alignment="right"
      />
      {line.persons.map((person) => (
        <nldd-list-item slot="children" key={person.allocation_id}>
          <nldd-spacer-cell size="44" />
          <nldd-text-cell
            text={person.person_name}
            supporting-text={[
              formatPeriod(person.start_date, person.end_date),
              person.category_mismatch ? 'andere categorie dan de regel aanneemt' : '',
            ]
              .filter(Boolean)
              .join(', ')}
          />
          <nldd-text-cell
            width="fit-content"
            text={formatEuro(person.total_cents)}
            supporting-text={`${formatEuro(person.realised_cents)} gerealiseerd, ${formatEuro(person.planned_cents)} gepland`}
            horizontal-alignment="right"
          />
        </nldd-list-item>
      ))}
      {line.persons_hidden > 0 && (
        <nldd-list-item slot="children">
          <nldd-spacer-cell size="44" />
          <nldd-text-cell
            color="secondary"
            text={
              line.persons_hidden === 1
                ? 'De inzet van 1 persoon zit in het totaal; het bedrag per persoon is voor jou niet zichtbaar'
                : `De inzet van ${line.persons_hidden} personen zit in het totaal; de bedragen per persoon zijn voor jou niet zichtbaar`
            }
          />
        </nldd-list-item>
      )}
      {line.costs.map((cost) => (
        <nldd-list-item slot="children" key={cost.cost_item_id}>
          <nldd-spacer-cell size="44" />
          <nldd-text-cell
            text={cost.description}
            supporting-text={`Kostenpost, ${formatPercent(cost.pct)} gedekt door deze regel`}
          />
          <nldd-text-cell
            width="fit-content"
            text={formatEuro(cost.total_cents)}
            supporting-text={`${formatEuro(cost.realised_cents)} gerealiseerd, ${formatEuro(cost.forecast_cents)} ingeschat`}
            horizontal-alignment="right"
          />
        </nldd-list-item>
      ))}
      {figures &&
        line.persons.length === 0 &&
        line.persons_hidden === 0 &&
        line.costs.length === 0 && (
          <nldd-list-item slot="children">
            <nldd-spacer-cell size="44" />
            <nldd-text-cell
              color="secondary"
              text="Op deze regel staat geen inzet en geen kostendekking"
            />
          </nldd-list-item>
        )}
    </nldd-list-item>
  );
}

function Months({ finance, period }: { finance: AssignmentFinance; period: string }) {
  const months = finance.months;
  if (months.length === 0) return null;
  const last = months.at(-1);
  return (
    <Section title="Inzet per maand">
      {finance.budgeted_outside_months_cents !== 0 && (
        <Quiet>
          Vaste regels en kosten hebben geen maand:{' '}
          {formatEuro(finance.budgeted_outside_months_cents)} van de begroting staat hier niet in.
        </Quiet>
      )}
      <MonthColumns
        title={`Verwachte inzet cumulatief tegen de begroting, ${period}`}
        months={months.map((month) => month.month.slice(0, 7))}
        series={[
          {
            key: 'realised',
            label: 'Gerealiseerd cumulatief',
            color: SERIES_COLORS.first,
            values: months.map((month) => month.cumulative_realised_cents),
          },
          {
            key: 'planned',
            label: 'Nog gepland cumulatief',
            color: SERIES_COLORS.second,
            values: months.map((month) => month.cumulative_planned_open_cents),
          },
        ]}
        formatValue={formatEuro}
        {...(last
          ? { reference: { value: last.cumulative_budgeted_cents, label: 'Begroot' } }
          : {})}
      />
      <nldd-table
        accessible-label={`Inzet per maand, ${period}`}
        columns="minmax(150px,1.2fr) 120px 120px 120px 150px 150px 140px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Maand" />
          <nldd-text-cell text="Begroot" horizontal-alignment="right" />
          <nldd-text-cell text="Gepland" horizontal-alignment="right" />
          <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
          <nldd-text-cell text="Begroot cumulatief" horizontal-alignment="right" />
          <nldd-text-cell text="Verwacht cumulatief" horizontal-alignment="right" />
          <nldd-text-cell text="Verschil cumulatief" horizontal-alignment="right" />
        </nldd-table-row>
        {months.map((month) => (
          <nldd-table-row key={month.month}>
            <nldd-text-cell
              text={formatMonth(month.month)}
              supporting-text={month.closed ? 'Afgesloten' : 'Open'}
            />
            <nldd-text-cell text={formatEuro(month.budgeted_cents)} horizontal-alignment="right" />
            <nldd-text-cell text={formatEuro(month.planned_cents)} horizontal-alignment="right" />
            <nldd-text-cell
              text={month.realised_cents === null ? '' : formatEuro(month.realised_cents)}
              horizontal-alignment="right"
            />
            <nldd-text-cell
              text={formatEuro(month.cumulative_budgeted_cents)}
              horizontal-alignment="right"
            />
            <nldd-text-cell
              text={formatEuro(month.cumulative_expected_cents)}
              horizontal-alignment="right"
            />
            <nldd-text-cell
              text={formatEuro(month.cumulative_variance_cents)}
              supporting-text={
                month.cumulative_variance_cents < 0
                  ? 'Boven de begroting'
                  : month.cumulative_variance_cents > 0
                    ? 'Onder de begroting'
                    : 'Gelijk'
              }
              horizontal-alignment="right"
              {...(month.cumulative_variance_cents < 0 ? { color: 'critical' } : {})}
            />
          </nldd-table-row>
        ))}
      </nldd-table>
    </Section>
  );
}

/**
 * What an analyst reads: what state the money is in, as of when, where it
 * deviates, and how it runs over time. Every number comes from the service.
 */
export function FinanceTab() {
  const assignment = useAssignmentShell();
  const rates = useRateCards();
  const assignmentId = assignment?.id ?? '';
  // Opens on this year when the assignment runs in it, otherwise on the
  // first year of the assignment: an assignment for next year has nothing
  // to show in this one.
  const [chosenYear, setYear] = useState<YearChoice | null>(null);
  const year = chosenYear ?? startingYear(assignment?.start_date, assignment?.end_date);
  const query = useQuery({
    queryKey: financeKeys.assignment(assignmentId, year),
    queryFn: () => fetchAssignmentFinance(assignmentId, year),
    enabled: assignmentId !== '',
  });
  if (!assignment) return null;
  const finance = query.data;
  const period = periodLabel(year);

  return (
    <nldd-simple-section>
      <nldd-container gap="24">
        <ActionBar
          label="Financieel: periode en export"
          filters={[
            {
              label: YEAR_FILTER_LABEL,
              value: year,
              onChange: setYear,
              options: yearOptions(),
              width: '180px',
            },
          ]}
          actions={[
            {
              text: 'Download regels (CSV)',
              href: financeCsvPath(assignment.id, year, 'lines'),
              kind: 'download',
            },
            {
              text: 'Download maanden (CSV)',
              href: financeCsvPath(assignment.id, year, 'months'),
              kind: 'download',
            },
          ]}
        />
        {assignment.phase === 'potential' && (
          <nldd-banner
            variant="warning"
            size="sm"
            text="Deze opdracht is nog niet akkoord"
            supporting-text="De bedragen hieronder zijn een verwachting. Ze tellen pas mee als opbrengst wanneer de opdrachtgever de offerte heeft getekend."
          />
        )}
        {query.isPending && <Loading />}
        {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
        {finance && (
          <>
            <Quiet>{referenceText(finance.reference_month)}</Quiet>
            <Stack gap="section">
              <Signals finance={finance} />
              <Section title={`Stand per begrotingsregel, ${period}`}>
                {finance.lines.length === 0 ? (
                  <EmptyNotice text="Deze opdracht heeft nog geen begrotingsregels" />
                ) : (
                  <nldd-table
                    accessible-label={`Stand per begrotingsregel, ${period}`}
                    columns={`minmax(200px,2fr) ${FIGURE_COLUMNS}`}
                  >
                    <nldd-table-row slot="header">
                      <nldd-text-cell text="Begrotingsregel" />
                      <FigureHeaderCells />
                    </nldd-table-row>
                    {finance.lines.map((line) => (
                      <nldd-table-row key={line.budget_line_id}>
                        <nldd-text-cell
                          text={line.description}
                          {...(line.rate_category || rateCauseText(line)
                            ? {
                                // The cause of a rate difference next to the line it explains.
                                'supporting-text': [
                                  line.rate_category ? rates.name(line.rate_category) : '',
                                  rateCauseText(line),
                                ]
                                  .filter(Boolean)
                                  .join('. '),
                              }
                            : {})}
                        />
                        <FigureCells figures={line.figures} error={line.pricing_error} />
                      </nldd-table-row>
                    ))}
                    <nldd-table-row>
                      <nldd-text-cell text="**Totaal**" />
                      <FigureCells figures={finance.totals} error={finance.pricing_error} bold />
                    </nldd-table-row>
                  </nldd-table>
                )}
              </Section>
              <AgreementFigures finance={finance} />
              {finance.lines.length > 0 && (
                <Section title="Onderbouwing per regel">
                  <nldd-list
                    type="tree"
                    appearance="box-base"
                    accessible-label="Onderbouwing per begrotingsregel"
                  >
                    {finance.lines.map((line) => (
                      <LineDetail key={line.budget_line_id} line={line} />
                    ))}
                  </nldd-list>
                </Section>
              )}
              <Months finance={finance} period={period} />
            </Stack>
          </>
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
