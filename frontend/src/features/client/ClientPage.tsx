import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { STATUS_COLORS, statusLabel } from '@/features/assignments/labels';
import { assignmentPath } from '@/features/assignments/paths';
import { Button } from '@/features/assignments/ui';
import { LinkRows } from '@/ui/LinkRows';
import { EmptyNotice, LoadError, Loading, Page } from '@/ui/layout';
import { QUOTE_STATUS_COLORS, QUOTE_STATUS_LABELS } from '@/features/quotes/api';
import { useInstance } from '@/layout/useInstance';
import { useViewer } from '@/layout/useViewer';
import { formatDateTime } from '@/features/quotes/format';
import { formatEuro, formatPeriod } from '@/lib/format';
import { PATHS } from '@/paths';
import { routesFor } from '@/routes';
import {
  clientKeys,
  fetchClientAssignments,
  fetchReceivedQuotes,
  fetchReceivedRequests,
} from './api';
import { DELIVERY_COLORS, DELIVERY_SHORT, deliveryText } from './labels';
import {
  CLIENT_VIEWS,
  clientAssignmentPath,
  clientPath,
  receivedQuotePath,
  type ClientView,
} from './paths';
import './register';

const VIEW_LABELS: Record<ClientView, { text: string; short: string }> = {
  mijn: { text: 'Mijn aanvragen', short: 'Mijn aanvragen' },
  offertes: { text: 'Ontvangen offertes', short: 'Offertes' },
  ontvangen: { text: 'Ontvangen aanvragen', short: 'Ontvangen' },
};

const FAILED_DELIVERY = new Set(['rejected', 'dead']);

/** The requests this instance sent to contractors, as client. */
function SentRequests() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: clientKeys.assignments(), queryFn: fetchClientAssignments });
  const items = query.data?.items ?? [];
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
          text="Je hebt nog geen aanvragen"
          supportingText={
            query.data.may_request
              ? 'Vraag een offerte aan bij een opdrachtnemer waarmee deze instantie is gekoppeld.'
              : 'Een aanvraag doen kan wie het recht aanvrager heeft.'
          }
        />
      ) : null}
      {items.length > 0 ? (
        <LinkRows
          label="Mijn aanvragen"
          rows={items.map((item) => {
            const delivery = item.request_delivery;
            // A request the other side does not have must not look like the rest.
            const failed = delivery && FAILED_DELIVERY.has(delivery.status) ? delivery : null;
            return {
              key: item.id,
              text: item.name,
              href: clientAssignmentPath(item.id),
              notice: [
                item.contractor_name,
                formatPeriod(item.start_date, item.end_date),
                failed ? statusLabel(item.status) : '',
                deliveryText(delivery),
              ]
                .filter(Boolean)
                .join(' · '),
              tag: failed
                ? {
                    text: DELIVERY_SHORT[failed.status] ?? failed.status,
                    color: DELIVERY_COLORS[failed.status] ?? 'critical',
                  }
                : { text: statusLabel(item.status), color: STATUS_COLORS[item.status] ?? 'neutral' },
              ...(item.latest_quote && 'total_cents' in item.latest_quote
                ? { end: formatEuro(item.latest_quote.total_cents) }
                : {}),
            };
          })}
        />
      ) : null}
    </nldd-container>
  );
}

/** The quotes contractors sent to this instance. */
function ReceivedQuotes() {
  const query = useQuery({ queryKey: clientKeys.receivedQuotes(), queryFn: fetchReceivedQuotes });
  const items = query.data?.items ?? [];
  return (
    <nldd-container gap="16">
      {query.isPending ? <Loading /> : null}
      {query.isError ? <LoadError error={query.error} retry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyNotice text="Er zijn geen ontvangen offertes" />
      ) : null}
      {items.length > 0 ? (
        <LinkRows
          label="Ontvangen offertes"
          rows={items.map((item) => ({
            key: item.id,
            text: item.assignment_name,
            href: receivedQuotePath(item.id),
            notice: [
              item.contractor_name,
              `uitgegeven op ${formatDateTime(item.issued_at)}`,
              item.may_decide ? 'Wacht op je besluit' : '',
            ]
              .filter(Boolean)
              .join(' · '),
            tag: {
              text: QUOTE_STATUS_LABELS[item.status] ?? item.status,
              color: QUOTE_STATUS_COLORS[item.status] ?? 'neutral',
            },
            ...('total_cents' in item ? { end: formatEuro(item.total_cents) } : {}),
          }))}
        />
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
        <LinkRows
          label="Ontvangen aanvragen"
          rows={items.map((item) => ({
            key: item.id,
            text: item.name,
            href: assignmentPath(item.id),
            notice: [
              item.client_name,
              formatPeriod(item.start_date, item.end_date),
              `Context: ${item.context_count ?? 0}`,
              `ontvangen op ${formatDateTime(item.received_at)}`,
            ]
              .filter(Boolean)
              .join(' · '),
            tag: { text: statusLabel(item.status), color: STATUS_COLORS[item.status] ?? 'neutral' },
            end: `${item.quote_count ?? 0} ${item.quote_count === 1 ? 'offerte' : 'offertes'}`,
          }))}
        />
      ) : null}
    </nldd-container>
  );
}

function parseView(value: string | null, views: readonly ClientView[]): ClientView {
  return (views as readonly string[]).includes(value ?? '') ? (value as ClientView) : 'mijn';
}

/**
 * Requests and quotes that travel between organisations, in both directions:
 * what this instance asked as client, the quotes that came back, and what
 * other organisations asked of this one.
 */
export function ClientPage() {
  const instance = useInstance();
  const viewer = useViewer();
  const [searchParams] = useSearchParams();
  // Requests that came in are for a contractor: who does not see Opdrachten has none.
  const contractor = routesFor(viewer).some((route) => route.path === PATHS.assignments);
  const views = CLIENT_VIEWS.filter((value) => value !== 'ontvangen' || contractor);
  const view = parseView(searchParams.get('weergave'), views);

  return (
    <Page
      kind="list"
      title="Aanvragen"
      instanceName={instance?.name}
      tabs={{
        label: 'Weergave van Aanvragen',
        current: view,
        narrow: 'bar',
        items: views.map((value) => ({
          key: value,
          text: VIEW_LABELS[value].text,
          short: VIEW_LABELS[value].short,
          href: clientPath(value),
        })),
      }}
    >
      {view === 'mijn' ? <SentRequests /> : null}
      {view === 'offertes' ? <ReceivedQuotes /> : null}
      {view === 'ontvangen' ? <ReceivedRequests /> : null}
    </Page>
  );
}
