import { useQuery } from '@tanstack/react-query';
import { fetchSteering, reportKeys, type Billability } from '@/features/reports/api';
import { useReportYear } from '@/features/reports/useReportYear';
import { scopeNote } from '@/features/reports/labels';
import { Figures } from '@/features/reports/ui';
import { reportYearOptions } from '@/features/reports/years';
import { useInstance } from '@/layout/useInstance';
import { formatEuro } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import { Loading, Page, Quiet } from '@/ui/layout';
import { KpiView } from './KpiView';
import { usePeopleViews } from './peopleTabs';

/** The short figures of the year; each amount is the server's. */
function BillabilityFigures({ billability, year }: { billability: Billability; year: number }) {
  const below = billability.below_target_count;
  const detail = `van ${billability.with_target_count} met een target`;
  return (
    <Figures
      label="Declarabiliteit in het kort"
      figures={[
        below > 0
          ? {
              label: 'Verwacht onder target',
              value: `${below} ${below === 1 ? 'persoon' : 'mensen'}`,
              attention: 'Haalt het target niet',
              detail,
            }
          : { label: 'Verwacht onder target', value: 'Niemand', detail, quiet: true },
        {
          label: `Verwacht in ${year}`,
          value: formatEuro(billability.realisation_cents),
          detail: `${formatEuro(billability.realised_cents)} gerealiseerde inzet, ${formatEuro(billability.forecast_cents)} nog gepland`,
        },
        {
          label: 'Target samen',
          value: formatEuro(billability.target_cents),
          quiet: billability.target_cents === 0,
        },
      ]}
    />
  );
}

/** Declarabiliteit: the year, whose figures these are, the short figures, and per person the outcome against the target. */
export function BillabilityPage() {
  const instance = useInstance();
  const { tabs, pending } = usePeopleViews('billability');
  const [year, setYear] = useReportYear();
  const steering = useQuery({
    queryKey: reportKeys.steering(year),
    queryFn: () => fetchSteering(year),
  });
  const billability = steering.data?.billability;
  return (
    <Page kind="worksheet" title="Declarabiliteit" instanceName={instance?.name} tabs={tabs}>
      {pending ? (
        <Loading />
      ) : (
        <>
          <ActionBar
            label="Declarabiliteit filteren"
            filters={[
              {
                label: 'Jaar',
                value: year,
                onChange: setYear,
                options: reportYearOptions(),
                width: '140px',
              },
            ]}
          />
          {billability && steering.data && (
            <>
              <Quiet>
                {scopeNote(
                  billability.scope,
                  `Iedereen met een target of inzet in ${steering.data.year}.`,
                  `Alleen de personen van wie je de KPI mag zien, in ${steering.data.year}.`,
                )}
              </Quiet>
              <BillabilityFigures billability={billability} year={steering.data.year} />
            </>
          )}
          <KpiView year={year} />
        </>
      )}
    </Page>
  );
}
