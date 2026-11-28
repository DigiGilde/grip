import { MonthColumns } from '@/features/reports/charts/MonthColumns';
import { SERIES_COLORS } from '@/features/reports/charts/colors';
import { formatEuro, formatMonth } from '@/lib/format';
import { DocumentLink } from '@/ui/Icon';
import { Quiet, Section, Stack } from '@/ui/layout';
import { financeCsvPath, type AssignmentFinance } from '../financeApi';

const COLUMNS =
  'minmax(150px,1.2fr) repeat(3,minmax(104px,1fr)) repeat(2,minmax(130px,1fr)) minmax(150px,1.2fr)';

const capitalised = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

function Months({ finance, period }: { finance: AssignmentFinance; period: string }) {
  const months = finance.months;
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
            label: 'Gerealiseerde inzet cumulatief',
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
      <nldd-table accessible-label={`Inzet per maand, ${period}`} columns={COLUMNS}>
        <nldd-table-row slot="header">
          <nldd-text-cell text="Maand" />
          <nldd-text-cell text="Begroot" horizontal-alignment="right" />
          <nldd-text-cell text="Gepland" horizontal-alignment="right" />
          <nldd-text-cell text="Gerealiseerde inzet" horizontal-alignment="right" />
          <nldd-text-cell text="Begroot cumulatief" horizontal-alignment="right" />
          <nldd-text-cell text="Verwacht cumulatief" horizontal-alignment="right" />
          <nldd-text-cell text="Verschil cumulatief" horizontal-alignment="right" />
        </nldd-table-row>
        {months.map((month) => (
          <nldd-table-row key={month.month}>
            <nldd-text-cell
              row-header
              text={capitalised(formatMonth(month.month))}
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

interface MonthlyEffortProps {
  finance: AssignmentFinance;
  /** The chosen period in words, for the names of the chart and the table. */
  period: string;
  /** The chosen year or the whole period, for the downloads. */
  year: string;
}

interface CsvDownloadsProps {
  assignmentId: string;
  /** The chosen year or the whole period. */
  year: string;
  lines: boolean;
  months: boolean;
}

/** The two tables of the budget as a download. */
export function CsvDownloads({ assignmentId, year, lines, months }: CsvDownloadsProps) {
  if (!lines && !months) return null;
  return (
    <nldd-container layout="wrap" gap="16">
      {lines && (
        <DocumentLink
          kind="download"
          size="sm"
          text="Download regels (csv)"
          href={financeCsvPath(assignmentId, year, 'lines')}
        />
      )}
      {months && (
        <DocumentLink
          kind="download"
          size="sm"
          text="Download maanden (csv)"
          href={financeCsvPath(assignmentId, year, 'months')}
        />
      )}
    </nldd-container>
  );
}

/** The effort per month as a chart and a table, and both tables as a download. */
export function MonthlyEffort({ finance, period, year }: MonthlyEffortProps) {
  const hasMonths = finance.months.length > 0;
  const hasLines = finance.lines.length > 0;
  if (!hasMonths && !hasLines) return null;
  return (
    <Stack gap="related">
      {hasMonths && <Months finance={finance} period={period} />}
      <CsvDownloads
        assignmentId={finance.assignment_id}
        year={year}
        lines={hasLines}
        months={hasMonths}
      />
    </Stack>
  );
}
