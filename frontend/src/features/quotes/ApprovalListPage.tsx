import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro } from '@/lib/format';
import { EmptyNotice, ErrorNotice, Loading, Page } from '@/ui/layout';
import { approvalKeys, approvalPath, fetchWaitingApprovals } from './approval';
import { formatDateTime } from './format';
import './register';

/** The quotes that wait for the reader's approval, across assignments. */
export function ApprovalListPage() {
  const instance = useInstance();
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  const query = useQuery({
    queryKey: approvalKeys.waiting,
    queryFn: fetchWaitingApprovals,
    retry: false,
  });
  const items = query.data?.items ?? [];
  const noRight = query.error instanceof ApiError && query.error.status === 403;

  return (
    <Page title="Wacht op mijn goedkeuring" instanceName={instance?.name}>
      {query.isPending ? <Loading /> : null}
      {query.isError && noRight ? (
        <EmptyNotice
          text="Offertes goedkeuren is voor wie dat recht heeft"
          supportingText="Een beheerder kent het toe bij een collega onder Team."
        />
      ) : null}
      {query.isError && !noRight ? <ErrorNotice message={errorMessage(query.error)} /> : null}
      {query.data && items.length === 0 ? (
        <EmptyNotice text="Er wacht geen offerte op je goedkeuring" />
      ) : null}
      {items.length > 0 ? (
        <div ref={ref}>
          <nldd-table
            accessible-label="Offertes die op mijn goedkeuring wachten"
            columns="minmax(220px,2fr) minmax(160px,1.5fr) minmax(110px,max-content) minmax(200px,1.5fr) max-content"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Offerte" />
              <nldd-text-cell text="Opdrachtgever" />
              <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
              <nldd-text-cell text="Gevraagd" />
              <nldd-text-cell text="Actie" />
            </nldd-table-row>
            {items.map((item) => (
              <nldd-table-row key={item.quote_id}>
                <nldd-text-cell
                  text={item.assignment_name}
                  supporting-text={item.quote_reference ?? ''}
                />
                <nldd-text-cell text={item.client_name ?? ''} />
                <nldd-text-cell
                  text={item.total_cents !== undefined ? formatEuro(item.total_cents) : ''}
                  horizontal-alignment="right"
                />
                <nldd-text-cell
                  text={formatDateTime(item.requested_at)}
                  supporting-text={
                    item.requested_by_name ? `door ${item.requested_by_name}` : ''
                  }
                />
                <nldd-cell>
                  <nldd-link
                    href={approvalPath(item.quote_id)}
                    text={item.may_decide === false ? 'Bekijk' : 'Beoordeel'}
                    size="md"
                    accessible-label={`${item.may_decide === false ? 'Bekijk' : 'Beoordeel'} offerte ${
                      item.quote_reference ?? ''
                    } voor ${item.assignment_name}`}
                  />
                </nldd-cell>
              </nldd-table-row>
            ))}
          </nldd-table>
        </div>
      ) : null}
    </Page>
  );
}
