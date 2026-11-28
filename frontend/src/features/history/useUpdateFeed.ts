import { useEffect, useMemo, useRef } from 'react';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import {
  NO_FILTER,
  UPDATE_KEYS,
  fetchUpdates,
  isFiltered,
  markUpdatesSeen,
  type UpdateFilter,
} from './updates';

/**
 * The feed, paging back. Showing all of it marks it as seen; a few rows do
 * not, and neither does the part a filter leaves.
 */
export function useUpdateFeed(
  limit: number,
  markSeen: boolean,
  filter: UpdateFilter = NO_FILTER,
) {
  const queryClient = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: UPDATE_KEYS.list(limit, filter),
    queryFn: ({ pageParam }) => fetchUpdates(limit, pageParam, filter),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next ?? undefined,
  });
  const items = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);

  // Seen is when the feed was shown, once; what was new stays marked on
  // this screen until the reader comes back.
  const marked = useRef(false);
  const shown = query.isSuccess && !isFiltered(filter);
  useEffect(() => {
    if (!markSeen || !shown || marked.current) return;
    marked.current = true;
    void markUpdatesSeen().then(() =>
      queryClient.invalidateQueries({ queryKey: ['updates', 'count'] }),
    );
  }, [markSeen, shown, queryClient]);

  return { query, items };
}
