import { useCallback, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { InlineSelect } from '@/features/assignments/ui';
import { EmptyNotice, ErrorNotice } from '@/ui/layout';
import { formatDate } from '@/lib/format';
import { fetchAssignmentContext, fetchContextNode, nodeKeys, type NodeLookup } from './api';
import { NodeCard, NodeCardGrid } from './NodeCard';
import { NodeDetailSheet } from './NodeDetailSheet';
import './register';

interface AssignmentContextViewProps {
  assignmentId: string;
  /** How many context URIs the assignment carries; zero skips the request. */
  count?: number;
}

/**
 * The context of an assignment as cards: per linked node what it is and, in
 * one line, where it comes from. A card opens the detail with the paths up
 * to the political input. Works for any assignment the person may read, on
 * the client side and on the contractor side.
 */
export function AssignmentContextView({ assignmentId, count }: AssignmentContextViewProps) {
  const [moment, setMoment] = useState('');
  const [openUri, setOpenUri] = useState<string | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const query = useQuery({
    queryKey: nodeKeys.context(assignmentId, moment),
    queryFn: () => fetchAssignmentContext(assignmentId, moment),
    enabled: count === undefined || count > 0,
    // Keep the cards of the other date in place while the new ones load.
    placeholderData: (previous) => previous,
  });
  const fetchNode = useCallback(
    (uri: string) => fetchContextNode(assignmentId, uri, moment),
    [assignmentId, moment],
  );

  const close = () => {
    const opened = openUri;
    setOpenUri(null);
    // Back to the card the detail was opened from.
    if (opened) {
      const card = [...(gridRef.current?.querySelectorAll<HTMLElement>('nldd-card') ?? [])].find(
        (el) => el.dataset.nodeUri === opened,
      );
      card?.focus();
    }
  };

  if (count === 0) {
    return (
      <EmptyNotice
        text="Deze opdracht heeft geen context"
        supportingText="Koppel een doel of instrument om te laten zien waar de opdracht uit voortkomt."
      />
    );
  }
  const data = query.data;
  const items: NodeLookup[] = data?.items ?? [];
  const placeholders = query.isPending ? Math.max(1, Math.min(count ?? 1, 6)) : 0;

  return (
    <nldd-container gap="16">
      {data?.acceptance_date ? (
        <nldd-container layout="wrap" gap="8" horizontal-alignment="right">
          <InlineSelect
            label="Peildatum van de context"
            value={moment}
            onChange={setMoment}
            width="260px"
            options={[
              { value: '', label: 'Zoals het nu is' },
              { value: 'acceptance', label: `Bij akkoord, ${formatDate(data.acceptance_date)}` },
            ]}
          />
        </nldd-container>
      ) : null}
      {query.isError ? <ErrorNotice message={errorMessage(query.error)} /> : null}
      {data?.notice ? <nldd-banner variant="neutral" size="sm" text={data.notice} /> : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyNotice text="Deze opdracht heeft geen context" />
      ) : null}
      {items.length > 0 || placeholders > 0 ? (
        <div ref={gridRef}>
          <NodeCardGrid label="Context van de opdracht">
            {items.map((item) => (
              <NodeCard
                key={item.uri}
                item={item}
                hideReason={Boolean(data?.notice)}
                onOpen={setOpenUri}
              />
            ))}
            {Array.from({ length: placeholders }, (_, index) => (
              <NodeCard key={`pending-${index}`} item={{ uri: '', resolved: false }} pending />
            ))}
          </NodeCardGrid>
        </div>
      ) : null}
      <NodeDetailSheet
        uri={openUri}
        known={items}
        fetchNode={fetchNode}
        scope={`${assignmentId}:${moment}`}
        onClose={close}
      />
    </nldd-container>
  );
}
