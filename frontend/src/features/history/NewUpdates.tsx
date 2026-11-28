import { PATHS } from '@/paths';
import { LinkRows } from '@/ui/LinkRows';
import { LoadError, Section } from '@/ui/layout';
import { UpdateTimeline } from './UpdateTimeline';
import { useUpdateFeed } from './useUpdateFeed';

/**
 * "Nieuw" for the start page: the last few things on the timeline of the
 * feed, under their day, and the way to the rest. Without anything new it
 * is not there.
 */
export function NewUpdates({ limit = 5 }: { limit?: number }) {
  const { query, items } = useUpdateFeed(limit, false);
  if (query.isPending) return null;
  if (query.isError)
    return (
      <Section title="Nieuw">
        <LoadError error={query.error} retry={() => void query.refetch()} />
      </Section>
    );
  if (items.length === 0) return null;
  return (
    <Section title="Nieuw">
      <UpdateTimeline
        items={items}
        level={3}
        after={
          <LinkRows
            label="Meer nieuws"
            rows={[{ key: 'all', text: 'Alles wat er gebeurd is', href: PATHS.updates }]}
          />
        }
      />
    </Section>
  );
}
