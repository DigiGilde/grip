import { PATHS } from '@/paths';
import { LinkRows } from '@/ui/LinkRows';
import { LoadError, Section } from '@/ui/layout';
import type { UpdateItem } from './updates';
import { useUpdateFeed } from './useUpdateFeed';

/**
 * "Nieuw" for the start page: the last few things as rows, each leading to
 * what it is about, and the way to the rest. Without anything new it is not
 * there.
 */
export function NewUpdates({ limit = 3 }: { limit?: number }) {
  const { query, items } = useUpdateFeed(limit, false);
  if (query.isPending) return null;
  if (query.isError)
    return (
      <Section title="Nieuw">
        <LoadError error={query.error} retry={() => void query.refetch()} />
      </Section>
    );
  if (items.length === 0) return null;
  const hrefOf = (item: UpdateItem) => item.parts.find((part) => part.href)?.href;
  return (
    <Section title="Nieuw">
      <LinkRows
        label="Wat er gebeurde"
        rows={[
          ...items.map((item) => {
            const href = hrefOf(item);
            return {
              key: item.id,
              text: item.text,
              notice: item.new ? `nieuw · ${item.when_text}` : item.when_text,
              ...(href ? { href } : {}),
            };
          }),
          { key: 'all', text: 'Alles wat er gebeurd is', href: PATHS.updates },
        ]}
      />
    </Section>
  );
}
