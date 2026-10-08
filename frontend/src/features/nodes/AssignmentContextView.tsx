import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { EmptyNotice, ErrorNotice, InlineSelect, Loading } from '@/features/assignments/ui';
import { formatDate } from '@/lib/format';
import { fetchAssignmentContext, nodeKeys } from './api';
import { NodeSummary } from './NodeSummary';
import './register';

interface AssignmentContextViewProps {
  assignmentId: string;
  /** How many context URIs the assignment carries; zero skips the request. */
  count?: number;
}

/**
 * The context of an assignment, resolved: per node its type, title and the
 * chain up to the political input, as of today or as of the day the quote
 * was accepted. Nodes change after an assignment is given; the acceptance
 * date shows what both parties saw then. A URI that cannot be resolved
 * stays visible as a URI.
 *
 * Works for any assignment the person may read, on the client side and on
 * the contractor side.
 */
export function AssignmentContextView({ assignmentId, count }: AssignmentContextViewProps) {
  const [moment, setMoment] = useState('');
  const query = useQuery({
    queryKey: nodeKeys.context(assignmentId, moment),
    queryFn: () => fetchAssignmentContext(assignmentId, moment),
    enabled: count === undefined || count > 0,
  });

  if (count === 0) {
    return (
      <EmptyNotice
        text="Deze opdracht heeft geen context"
        supportingText="Er zijn geen nodes aan gekoppeld. Dat mag: niet elke opdracht volgt uit een vastgelegde wens."
      />
    );
  }
  const data = query.data;
  const items = data?.items ?? [];
  return (
    <nldd-container gap="16">
      {data?.acceptance_date ? (
        <InlineSelect
          label="Peildatum van de context"
          value={moment}
          onChange={setMoment}
          width="320px"
          options={[
            { value: '', label: 'Zoals het nu is' },
            {
              value: 'acceptance',
              label: `Bij akkoord op ${formatDate(data.acceptance_date)}`,
            },
          ]}
        />
      ) : null}
      {query.isPending ? <Loading text="Bezig met ophalen van de context" /> : null}
      {query.isError ? <ErrorNotice message={errorMessage(query.error)} /> : null}
      {data ? (
        <nldd-text size="sm">
          Titel en status per {formatDate(data.peildatum)}. De keten is de keten van nu.
        </nldd-text>
      ) : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyNotice text="Deze opdracht heeft geen context" />
      ) : null}
      {items.length > 0 ? (
        <ul
          aria-label="Context van de opdracht"
          style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '16px' }}
        >
          {items.map((item) => (
            <li key={item.uri}>
              <NodeSummary item={item} />
            </li>
          ))}
        </ul>
      ) : null}
    </nldd-container>
  );
}
