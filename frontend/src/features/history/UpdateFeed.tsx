import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useInstance } from '@/layout/useInstance';
import { ActionBar, type ActionBarFilter } from '@/ui/ActionBar';
import { EmptyNotice, LoadError, Loading, Page } from '@/ui/layout';
import {
  ALL,
  NO_FILTER,
  UPDATE_KEYS,
  fetchUpdateFilters,
  filterChoices,
  filterOf,
  isFiltered,
  unknownFilters,
  withFilter,
  type UpdateFilter,
  type UpdateFilterKey,
} from './updates';
import { UpdateTimeline } from './UpdateTimeline';
import { useUpdateFeed } from './useUpdateFeed';

interface UpdateFeedProps {
  /** How many items to show. */
  limit?: number;
  /** Whether the reader can page back with "Toon eerder". */
  paged?: boolean;
  /** The level of the day headings: 2 on a page of its own, 3 inside a section. */
  level?: 2 | 3;
  /** What the feed is narrowed to. */
  filter?: UpdateFilter;
}

/** What happened since the reader last looked, as a timeline per day. */
export function UpdateFeed({
  limit = 10,
  paged = false,
  level = 3,
  filter = NO_FILTER,
}: UpdateFeedProps) {
  const { query, items } = useUpdateFeed(limit, true, filter);

  if (query.isPending) return <Loading />;
  if (query.isError) return <LoadError error={query.error} retry={() => void query.refetch()} />;
  if (items.length === 0)
    return <EmptyNotice text={isFiltered(filter) ? 'Niets gevonden' : 'Niets nieuws'} />;
  return (
    <UpdateTimeline
      items={items}
      level={level}
      after={
        paged && query.hasNextPage ? (
          <ActionBar
            label="Verder terug"
            filters={[]}
            actions={[
              {
                text: 'Toon eerder',
                onClick: () => void query.fetchNextPage(),
                loading: query.isFetchingNextPage,
              },
            ]}
          />
        ) : undefined
      }
    />
  );
}

const WIDTHS: Record<UpdateFilterKey, string> = { opdracht: '280px', persoon: '220px' };

/** The page "Wat is er gebeurd": the whole feed, paging back, to narrow by assignment or person. */
export function UpdatesPage() {
  const instance = useInstance();
  const [params, setParams] = useSearchParams();
  const filter = useMemo(() => filterOf(params), [params]);
  const options = useQuery({ queryKey: UPDATE_KEYS.filters, queryFn: fetchUpdateFilters });

  // An id the options do not hold finds nothing (hidden from this reader, or
  // not there) or changes nothing (every item has it). The address drops it,
  // so what the selects say is what the list shows.
  const unknown = useMemo(
    () => (options.data ? unknownFilters(filter, options.data) : []),
    [filter, options.data],
  );
  useEffect(() => {
    if (unknown.length === 0) return;
    setParams(
      (current) => unknown.reduce((next, key) => withFilter(next, key, ALL), current),
      { replace: true },
    );
  }, [unknown, setParams]);

  const filters: ActionBarFilter[] = (
    options.data ? filterChoices(options.data, filter) : []
  ).map(({ key, ...choice }) => ({
    ...choice,
    onChange: (value: string) =>
      setParams((current) => withFilter(current, key, value), { replace: true }),
    width: WIDTHS[key],
  }));
  return (
    <Page kind="list" title="Wat is er gebeurd" instanceName={instance?.name}>
      {options.isError && (
        <LoadError error={options.error} retry={() => void options.refetch()} />
      )}
      {filters.length > 0 && <ActionBar label="Nieuws filteren" filters={filters} />}
      <UpdateFeed limit={20} paged level={2} filter={filter} />
    </Page>
  );
}
