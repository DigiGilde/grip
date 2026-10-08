import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { assignmentKeys, fetchAssignments } from './api';
import { AssignmentFormSheet } from './AssignmentFormSheet';
import { STATUS_COLORS, statusLabel } from './labels';
import { assignmentPath } from './paths';
import { Button, EmptyNotice, ErrorNotice, Loading } from './ui';

export function AssignmentsPage() {
  const instance = useInstance();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [session, setSession] = useState(0);
  const tableRef = useRef<HTMLDivElement>(null);
  useRouterLinks(tableRef);

  const query = useQuery({ queryKey: assignmentKeys.list(), queryFn: fetchAssignments });
  const items = query.data?.items ?? [];
  const showAmounts = items.some((item) => 'quoted_amount_cents' in item);

  return (
    <nldd-simple-section>
      <PageHeading text="Opdrachten" instanceName={instance?.name} />
      <nldd-container gap="16">
        {query.data?.can_create && (
          <div>
            <Button
              text="Nieuwe opdracht"
              appearance="primary"
              onClick={() => {
                setSession((current) => current + 1);
                setCreating(true);
              }}
            />
          </div>
        )}
        {query.isPending && <Loading />}
        {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
        {query.isSuccess && items.length === 0 && (
          <EmptyNotice
            text="Er zijn geen opdrachten"
            supportingText="Je ziet hier de opdrachten waar je bij betrokken bent."
          />
        )}
        {items.length > 0 && (
          <div ref={tableRef}>
            <nldd-table
              accessible-label="Opdrachten"
              columns={`minmax(220px,2fr) 170px minmax(160px,1fr) minmax(200px,1fr) minmax(140px,1fr)${showAmounts ? ' 140px' : ''}`}
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Opdracht" />
                <nldd-text-cell text="Status" />
                <nldd-text-cell text="Opdrachtgever" />
                <nldd-text-cell text="Periode" />
                <nldd-text-cell text="Eigenaar" />
                {showAmounts && <nldd-text-cell text="Offertebedrag" horizontal-alignment="right" />}
              </nldd-table-row>
              {items.map((item) => (
                <nldd-table-row key={item.id}>
                  <nldd-cell>
                    <nldd-link href={assignmentPath(item.id)} text={item.name} />
                  </nldd-cell>
                  <nldd-cell>
                    <nldd-badge
                      color={STATUS_COLORS[item.status] ?? 'neutral'}
                      text={statusLabel(item.status)}
                    />
                  </nldd-cell>
                  <nldd-text-cell text={item.client_name ?? ''} />
                  <nldd-text-cell text={formatPeriod(item.start_date, item.end_date)} />
                  <nldd-text-cell text={item.owner_name ?? ''} />
                  {showAmounts && (
                    <nldd-text-cell
                      text={formatEuro(item.quoted_amount_cents)}
                      horizontal-alignment="right"
                    />
                  )}
                </nldd-table-row>
              ))}
            </nldd-table>
          </div>
        )}
      </nldd-container>
      <AssignmentFormSheet
        open={creating}
        session={session}
        onClose={() => setCreating(false)}
        onSaved={(saved) => {
          setCreating(false);
          navigate(assignmentPath(saved.id));
        }}
      />
    </nldd-simple-section>
  );
}
