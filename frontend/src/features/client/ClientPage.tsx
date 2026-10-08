import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { STATUS_COLORS, statusLabel } from '@/features/assignments/labels';
import { assignmentPath } from '@/features/assignments/paths';
import { Button } from '@/features/assignments/ui';
import { EmptyNotice, LoadError, Loading } from '@/ui/layout';
import { QUOTE_STATUS_COLORS, QUOTE_STATUS_LABELS } from '@/features/quotes/api';
import { formatDateTime } from '@/features/quotes/format';
import { Segments } from '@/features/team/ui/controls';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import {
  clientKeys,
  fetchClientAssignments,
  fetchReceivedQuotes,
  fetchReceivedRequests,
} from './api';
import { DELIVERY_COLORS, DELIVERY_SHORT } from './labels';
import {
  CLIENT_VIEWS,
  clientAssignmentPath,
  clientPath,
  receivedQuotePath,
  type ClientView,
} from './paths';
import './register';

const VIEW_LABELS: Record<ClientView, string> = {
  uitgezet: 'Uitgezette aanvragen',
  offertes: 'Ontvangen offertes',
  ontvangen: 'Ontvangen aanvragen',
};

/** The requests this instance sent to contractors, as client. */
function SentRequests() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: clientKeys.assignments(), queryFn: fetchClientAssignments });
  const items = query.data?.items ?? [];
  const showAmounts = items.some((item) => item.latest_quote && 'total_cents' in item.latest_quote);
  return (
    <nldd-container gap="16">
      {query.data?.may_request ? (
        <div>
          <Button
            text="Offerte aanvragen"
            appearance="primary"
            onClick={() => navigate(PATHS.clientRequest)}
          />
        </div>
      ) : null}
      {query.isPending ? <Loading /> : null}
      {query.isError ? <LoadError error={query.error} retry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyNotice
          text="Er zijn geen uitgezette aanvragen"
          supportingText={
            query.data.may_request
              ? 'Vraag een offerte aan bij een opdrachtnemer waarmee deze instantie is gekoppeld.'
              : 'Een aanvraag doen kan wie het recht aanvrager heeft.'
          }
        />
      ) : null}
      {items.length > 0 ? (
        <nldd-table
          accessible-label="Uitgezette aanvragen"
          columns={`minmax(220px,2fr) 170px minmax(160px,1fr) minmax(190px,1fr) 180px${showAmounts ? ' 140px' : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Opdracht" />
            <nldd-text-cell text="Status" />
            <nldd-text-cell text="Opdrachtnemer" />
            <nldd-text-cell text="Periode" />
            <nldd-text-cell text="Verzending aanvraag" />
            {showAmounts ? <nldd-text-cell text="Offerte" horizontal-alignment="right" /> : null}
          </nldd-table-row>
          {items.map((item) => (
            <nldd-table-row key={item.id}>
              <nldd-cell>
                <nldd-link href={clientAssignmentPath(item.id)} text={item.name} />
              </nldd-cell>
              <nldd-cell>
                <nldd-badge
                  color={STATUS_COLORS[item.status] ?? 'neutral'}
                  text={statusLabel(item.status)}
                />
              </nldd-cell>
              <nldd-text-cell text={item.contractor_name ?? ''} />
              <nldd-text-cell text={formatPeriod(item.start_date, item.end_date)} />
              <nldd-cell>
                {item.request_delivery ? (
                  <nldd-badge
                    color={DELIVERY_COLORS[item.request_delivery.status] ?? 'neutral'}
                    text={
                      DELIVERY_SHORT[item.request_delivery.status] ?? item.request_delivery.status
                    }
                  />
                ) : (
                  <nldd-text size="sm">Niet verstuurd</nldd-text>
                )}
              </nldd-cell>
              {showAmounts ? (
                <nldd-text-cell
                  text={formatEuro(item.latest_quote?.total_cents)}
                  horizontal-alignment="right"
                />
              ) : null}
            </nldd-table-row>
          ))}
        </nldd-table>
      ) : null}
    </nldd-container>
  );
}

/** The quotes contractors sent to this instance. */
function ReceivedQuotes() {
  const query = useQuery({ queryKey: clientKeys.receivedQuotes(), queryFn: fetchReceivedQuotes });
  const items = query.data?.items ?? [];
  const showAmounts = items.some((item) => 'total_cents' in item);
  return (
    <nldd-container gap="16">
      {query.isPending ? <Loading /> : null}
      {query.isError ? <LoadError error={query.error} retry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyNotice text="Er zijn geen ontvangen offertes" />
      ) : null}
      {items.length > 0 ? (
        <nldd-table
          accessible-label="Ontvangen offertes"
          columns={`minmax(220px,2fr) minmax(160px,1fr) 170px 190px${showAmounts ? ' 140px' : ''} 170px`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Offerte voor" />
            <nldd-text-cell text="Opdrachtnemer" />
            <nldd-text-cell text="Status" />
            <nldd-text-cell text="Uitgegeven" />
            {showAmounts ? <nldd-text-cell text="Bedrag" horizontal-alignment="right" /> : null}
            <nldd-text-cell text="Aan jou" />
          </nldd-table-row>
          {items.map((item) => (
            <nldd-table-row key={item.id}>
              <nldd-cell>
                <nldd-link href={receivedQuotePath(item.id)} text={item.assignment_name} />
              </nldd-cell>
              <nldd-text-cell text={item.contractor_name ?? ''} />
              <nldd-cell>
                <nldd-badge
                  color={QUOTE_STATUS_COLORS[item.status] ?? 'neutral'}
                  text={QUOTE_STATUS_LABELS[item.status] ?? item.status}
                />
              </nldd-cell>
              <nldd-text-cell text={formatDateTime(item.issued_at)} />
              {showAmounts ? (
                <nldd-text-cell text={formatEuro(item.total_cents)} horizontal-alignment="right" />
              ) : null}
              <nldd-text-cell text={item.may_decide ? 'Wacht op je besluit' : ''} />
            </nldd-table-row>
          ))}
        </nldd-table>
      ) : null}
    </nldd-container>
  );
}

/** The requests other organisations sent to this instance, as contractor. */
function ReceivedRequests() {
  const query = useQuery({
    queryKey: clientKeys.receivedRequests(),
    queryFn: fetchReceivedRequests,
  });
  const items = query.data?.items ?? [];
  return (
    <nldd-container gap="16">
      {query.isPending ? <Loading /> : null}
      {query.isError ? <LoadError error={query.error} retry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyNotice text="Er zijn geen ontvangen aanvragen" />
      ) : null}
      {items.length > 0 ? (
        <nldd-table
          accessible-label="Ontvangen aanvragen"
          columns="minmax(220px,2fr) 170px minmax(160px,1fr) minmax(190px,1fr) 110px 110px 190px"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Aanvraag" />
            <nldd-text-cell text="Status" />
            <nldd-text-cell text="Opdrachtgever" />
            <nldd-text-cell text="Gewenste periode" />
            <nldd-text-cell text="Context" horizontal-alignment="right" />
            <nldd-text-cell text="Offertes" horizontal-alignment="right" />
            <nldd-text-cell text="Ontvangen" />
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
              <nldd-text-cell text={String(item.context_count ?? 0)} horizontal-alignment="right" />
              <nldd-text-cell text={String(item.quote_count ?? 0)} horizontal-alignment="right" />
              <nldd-text-cell text={formatDateTime(item.received_at)} />
            </nldd-table-row>
          ))}
        </nldd-table>
      ) : null}
    </nldd-container>
  );
}

function parseView(value: string | null): ClientView {
  return (CLIENT_VIEWS as readonly string[]).includes(value ?? '')
    ? (value as ClientView)
    : 'uitgezet';
}

/**
 * Requests and quotes that travel between organisations, in both directions:
 * what this instance asked as client, the quotes that came back, and what
 * other organisations asked of this one.
 */
export function ClientPage() {
  const instance = useInstance();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const view = parseView(searchParams.get('weergave'));
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);

  return (
    <nldd-simple-section>
      <PageHeading text="Aanvragen" instanceName={instance?.name} />
      <nldd-container gap="16">
        <Segments
          label="Weergave"
          value={view}
          onChange={(next) => navigate(clientPath(parseView(next)), { replace: true })}
          options={CLIENT_VIEWS.map((value) => ({ value, label: VIEW_LABELS[value] }))}
        />
        <div ref={ref}>
          {view === 'uitgezet' ? <SentRequests /> : null}
          {view === 'offertes' ? <ReceivedQuotes /> : null}
          {view === 'ontvangen' ? <ReceivedRequests /> : null}
        </div>
      </nldd-container>
    </nldd-simple-section>
  );
}
