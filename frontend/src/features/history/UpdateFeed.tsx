import { useEffect, useMemo, useRef } from 'react';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { ActionBar } from '@/ui/ActionBar';
import { EmptyNotice, LoadError, Loading, Page, Quiet, SectionHeading, Stack } from '@/ui/layout';
import { UPDATE_KEYS, byDay, fetchUpdates, markUpdatesSeen, type UpdateItem } from './updates';

/** One sentence; the thing it is about is a link to where it is to be seen. */
function Sentence({ item }: { item: UpdateItem }) {
  return (
    <nldd-text size="md" {...(item.new ? { weight: 'bold' } : {})}>
      {item.parts.map((part, index) =>
        part.href ? (
          <nldd-link key={index} href={part.href} text={part.text} />
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </nldd-text>
  );
}

interface UpdateFeedProps {
  /** How many items to show. */
  limit?: number;
  /** Whether the reader can page back with "Toon eerder". */
  paged?: boolean;
  /** The level of the day headings: 2 on a page of its own, 3 inside a section. */
  level?: 2 | 3;
}

/**
 * What happened since the reader last looked: one sentence per row, the time
 * at the right, grouped by day. Showing it marks it as seen.
 */
export function UpdateFeed({ limit = 10, paged = false, level = 3 }: UpdateFeedProps) {
  const queryClient = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: UPDATE_KEYS.list(limit),
    queryFn: ({ pageParam }) => fetchUpdates(limit, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next ?? undefined,
  });
  const days = useMemo(
    () => byDay(query.data?.pages.flatMap((page) => page.items) ?? []),
    [query.data],
  );

  // Seen is when the feed was shown, once; what was new stays marked on
  // this screen until the reader comes back.
  const marked = useRef(false);
  const shown = query.isSuccess;
  useEffect(() => {
    if (!shown || marked.current) return;
    marked.current = true;
    void markUpdatesSeen().then(() =>
      queryClient.invalidateQueries({ queryKey: ['updates', 'count'] }),
    );
  }, [shown, queryClient]);

  if (query.isPending) return <Loading />;
  if (query.isError) return <LoadError error={query.error} retry={() => void query.refetch()} />;
  if (days.length === 0) return <EmptyNotice text="Niets nieuws" />;
  return (
    <RouterLinks>
      <Stack gap="group">
        {days.map((day) => (
          <Stack key={day.day} gap="close">
            <SectionHeading text={day.day} level={level} />
            <nldd-list accessible-label={`Wat er gebeurde: ${day.day}`} appearance="box-base">
              {day.items.map((item) => (
                <nldd-list-item key={item.id}>
                  <nldd-cell width="full">
                    <Sentence item={item} />
                  </nldd-cell>
                  <nldd-cell horizontal-alignment="right">
                    <Quiet>{item.new ? `nieuw · ${item.when_text}` : item.when_text}</Quiet>
                  </nldd-cell>
                </nldd-list-item>
              ))}
            </nldd-list>
          </Stack>
        ))}
        {paged && query.hasNextPage && (
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
        )}
      </Stack>
    </RouterLinks>
  );
}

/** The page "Wat is er gebeurd": the whole feed, paging back. */
export function UpdatesPage() {
  const instance = useInstance();
  return (
    <Page title="Wat is er gebeurd" instanceName={instance?.name}>
      <UpdateFeed limit={20} paged level={2} />
    </Page>
  );
}
