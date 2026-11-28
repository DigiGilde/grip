import { useQuery } from '@tanstack/react-query';
import { costsKey, fetchCostItems } from '@/features/costs/api';
import { fetchOverview, overviewKeys } from '@/features/overview/api';
import { fetchInvestment, fetchSteering, reportKeys } from '@/features/reports/api';
import { currentReportYear } from '@/features/reports/years';
import { useInstance } from '@/layout/useInstance';
import { LinkRows } from '@/ui/LinkRows';
import { EmptyNotice, LoadError, Loading, Page } from '@/ui/layout';
import { moneyRows } from './moneyRows';

/**
 * Geld: one row per place, each saying what matters there. Each source is its
 * own request, so a problem with one never hides the rows of the others.
 */
export function MoneyPage() {
  const instance = useInstance();
  const year = currentReportYear();
  const steering = useQuery({
    queryKey: reportKeys.steering(year),
    queryFn: () => fetchSteering(year),
  });
  const investment = useQuery({
    queryKey: reportKeys.investment(year),
    queryFn: () => fetchInvestment(year),
  });
  const overview = useQuery({
    queryKey: overviewKeys.list(year),
    queryFn: () => fetchOverview(year),
  });
  // Only a reader without the block can still add a first cost item.
  const costs = useQuery({
    queryKey: costsKey(Number(year)),
    queryFn: () => fetchCostItems(Number(year)),
    enabled: steering.isSuccess && !steering.data.costs,
  });
  const queries = [steering, investment, overview, costs];
  const failed = queries.find((query) => query.isError);
  const rows = moneyRows({
    year,
    steering: steering.data,
    investment: investment.data,
    overview: overview.data,
    costs: costs.data,
  });

  return (
    <Page kind="list" title="Geld" instanceName={instance?.name}>
      {queries.some((query) => query.isPending && query.fetchStatus !== 'idle') ? (
        <Loading />
      ) : (
        <>
          {failed && <LoadError error={failed.error} retry={() => void failed.refetch()} />}
          {rows.length > 0 && <LinkRows label="Onderdelen van Geld" rows={rows} />}
          {!failed && rows.length === 0 && (
            <EmptyNotice
              text="Er zijn voor jou geen cijfers"
              supportingText="Je ziet hier de cijfers van opdrachten die je beheert."
            />
          )}
        </>
      )}
    </Page>
  );
}
