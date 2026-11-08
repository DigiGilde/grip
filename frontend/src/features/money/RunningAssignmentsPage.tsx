import { useQuery } from '@tanstack/react-query';
import { referenceText } from '@/features/assignments/financeText';
import {
  fetchOverview,
  hasFigures,
  overviewKeys,
  type Overview,
  type OverviewRow,
} from '@/features/overview/api';
import {
  WHOLE_PERIOD,
  YEAR_FILTER_LABEL,
  periodLabel,
  yearOptions,
} from '@/features/overview/years';
import { fetchSteering, reportKeys } from '@/features/reports/api';
import { useReportYear } from '@/features/reports/useReportYear';
import { currentReportYear } from '@/features/reports/years';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import { EmptyNotice, LoadError, Loading, Page, Quiet } from '@/ui/layout';
import { AssignmentsSheet } from './AssignmentsSheet';
import { runningRows } from './moneyRows';

const YEARS = yearOptions();

/** The month every row is closed up to; undefined when the rows differ. */
function sharedStand(rows: readonly OverviewRow[]): string | null | undefined {
  const months = new Set(
    rows.filter((row) => hasFigures(row.figures)).map((row) => row.reference_month ?? null),
  );
  return months.size === 1 ? [...months][0] : undefined;
}

function periodSentence(year: string, own: boolean): string {
  const scope = own ? ', jouw opdrachten' : '';
  return year === WHOLE_PERIOD
    ? `De hele looptijd${scope}.`
    : `${year}${scope}. Van een opdracht over meer jaren tellen de maanden van dit jaar.`;
}

function leftOutText(overview: Overview, period: string): string | null {
  const count = overview.rows.filter((row) => row.in_year === false).length;
  if (count === 0) return null;
  return count === 1
    ? `1 opdracht loopt niet in ${period} en staat hier niet.`
    : `${count} opdrachten lopen niet in ${period} en staan hier niet.`;
}

/** The worksheet over running assignments: what a controller lays side by side. */
export function RunningAssignmentsPage() {
  const instance = useInstance();
  const [year, setYear] = useReportYear(YEARS);
  const query = useQuery({ queryKey: overviewKeys.list(year), queryFn: () => fetchOverview(year) });
  // Who the figures are of follows from the reader, not from the year.
  const thisYear = currentReportYear();
  const steering = useQuery({
    queryKey: reportKeys.steering(thisYear),
    queryFn: () => fetchSteering(thisYear),
  });
  const rows = runningRows(query.data);
  const period = periodLabel(year);
  const stand = sharedStand(rows);
  const leftOut = query.data ? leftOutText(query.data, period) : null;
  const total = query.data?.figures_active;

  return (
    <Page
      kind="worksheet"
      title="Lopende opdrachten"
      instanceName={instance?.name}
      back={{ href: PATHS.money, text: 'Terug naar Geld' }}
    >
      <ActionBar
        label="Lopende opdrachten: periode"
        filters={[
          {
            label: YEAR_FILTER_LABEL,
            value: year,
            onChange: setYear,
            options: YEARS,
            width: '180px',
          },
        ]}
      />
      {query.isPending && <Loading />}
      {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
      {query.isSuccess && !steering.isPending && (
        <nldd-container gap="8">
          <nldd-text>{periodSentence(year, steering.data?.turnover?.scope === 'own')}</nldd-text>
          {rows.length > 0 && stand !== undefined && <Quiet>{referenceText(stand)}</Quiet>}
        </nldd-container>
      )}
      {query.isSuccess && rows.length === 0 && (
        <EmptyNotice
          text={`Er lopen geen opdrachten in ${period}`}
          supportingText="Je ziet hier de opdrachten waarvan je de bedragen mag zien."
        />
      )}
      {rows.length > 0 && (
        <RouterLinks>
          <AssignmentsSheet
            rows={rows}
            total={hasFigures(total) ? total : undefined}
            label={`Lopende opdrachten, ${period}`}
            perRowStand={stand === undefined}
          />
        </RouterLinks>
      )}
      {leftOut && <Quiet>{leftOut}</Quiet>}
    </Page>
  );
}
