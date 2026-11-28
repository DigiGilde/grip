import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSteering, reportKeys, type Steering } from '@/features/reports/api';
import { useReportYear } from '@/features/reports/useReportYear';
import { reportYearOptions } from '@/features/reports/years';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import { LoadError, Loading, Page, Quiet } from '@/ui/layout';

/** A page under Geld whose figures follow one year; the year lives in the address. */
export function YearWorksheet({
  title,
  children,
}: {
  title: string;
  children: (year: string) => ReactNode;
}) {
  const instance = useInstance();
  const [year, setYear] = useReportYear();
  return (
    <RouterLinks>
      <Page
        kind="worksheet"
        title={title}
        instanceName={instance?.name}
        back={{ href: PATHS.money, text: 'Terug naar Geld' }}
      >
        <ActionBar
          label={`${title} filteren`}
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
        {children(year)}
      </Page>
    </RouterLinks>
  );
}

/** A block of the steering overview, or a line when the API sent none for this reader. */
export function SteeringContent({
  year,
  block,
}: {
  year: string;
  block: (steering: Steering) => ReactNode;
}) {
  const query = useQuery({
    queryKey: reportKeys.steering(year),
    queryFn: () => fetchSteering(year),
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <LoadError error={query.error} retry={() => void query.refetch()} />;
  return block(query.data) || <Quiet>{`Voor ${year} is hier niets te tonen.`}</Quiet>;
}
