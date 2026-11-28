import { useQuery } from '@tanstack/react-query';
import { fetchInvestment, fetchSteering, reportKeys } from '@/features/reports/api';
import { OccupancyBlock } from '@/features/reports/occupancy/OccupancyBlock';
import { TimeRoom } from '@/features/reports/occupancy/TimeRoom';
import { useReportYear } from '@/features/reports/useReportYear';
import { reportYearOptions } from '@/features/reports/years';
import { useInstance } from '@/layout/useInstance';
import { ActionBar } from '@/ui/ActionBar';
import { LoadError, Loading, Page, Quiet } from '@/ui/layout';
import { usePeopleViews } from './peopleTabs';

/** Bezetting: who has room and who is overbooked, and what that room is worth in time. */
export function OccupancyPage() {
  const instance = useInstance();
  const { tabs, pending } = usePeopleViews('occupancy');
  const [year, setYear] = useReportYear();
  const steering = useQuery({
    queryKey: reportKeys.steering(year),
    queryFn: () => fetchSteering(year),
  });
  const investment = useQuery({
    queryKey: reportKeys.investment(year),
    queryFn: () => fetchInvestment(year),
    retry: false,
  });
  const occupancy = steering.data?.occupancy;
  return (
    <Page kind="worksheet" title="Bezetting" instanceName={instance?.name} tabs={tabs}>
      {pending ? (
        <Loading />
      ) : (
        <>
          <ActionBar
            label="Bezetting filteren op jaar"
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
          {steering.isPending && <Loading />}
          {steering.isError && (
            <LoadError error={steering.error} retry={() => void steering.refetch()} />
          )}
          {steering.data && !occupancy && !investment.data?.time && (
            <Quiet>{`Voor ${steering.data.year} zijn er geen bezettingsgegevens.`}</Quiet>
          )}
          {steering.data && occupancy && (
            <OccupancyBlock bare occupancy={occupancy} year={steering.data.year} />
          )}
          {investment.data?.time && <TimeRoom time={investment.data.time} />}
        </>
      )}
    </Page>
  );
}
