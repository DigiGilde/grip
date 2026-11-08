import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError } from '@/api/client';
import {
  ACCEPTANCE_FORM_LABELS,
  QUOTE_STATUS_COLORS,
  QUOTE_STATUS_LABELS,
} from '@/features/quotes/api';
import { formatDateTime } from '@/features/quotes/format';
import {
  clearDraft,
  createDecisionIntent,
  readDraft,
  saveDraft,
  useDecisionReturn,
} from '@/features/quotes/proof';
import {
  QuoteDecisionView,
  type Decision,
  type DecisionDraft,
  type DecisionValues,
} from '@/features/quotes/QuoteDecisionView';
import { useInstance } from '@/layout/useInstance';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate } from '@/lib/format';
import {
  EmptyNotice,
  LoadError,
  Loading,
  NotFound,
  Page,
  Quiet,
  Section,
  Stack,
} from '@/ui/layout';
import { clientKeys, fetchReceivedQuote, type Delivery, type ReceivedQuoteDetail } from './api';
import { DELIVERY_COLORS, DELIVERY_SHORT, deliveryText } from './labels';
import { clientAssignmentPath, clientPath, receivedQuotePath } from './paths';
import './register';

function DecisionNotice({ detail }: { detail: ReceivedQuoteDetail }) {
  const { quote } = detail;
  if (quote.status === 'accepted') {
    const acceptance = quote.acceptance;
    const who = [acceptance?.signer_name, acceptance?.signer_function].filter(Boolean).join(', ');
    const form = acceptance ? (ACCEPTANCE_FORM_LABELS[acceptance.form] ?? acceptance.form) : '';
    return (
      <nldd-banner
        variant="success"
        text="Op deze offerte is akkoord gegeven"
        supporting-text={[
          acceptance?.signed_at ? `Op ${formatDateTime(acceptance.signed_at)}` : '',
          who ? `door ${who}` : '',
          form ? `(${form})` : '',
        ]
          .filter(Boolean)
          .join(' ')}
      />
    );
  }
  if (quote.status === 'rejected') {
    return (
      <nldd-banner
        variant="neutral"
        text="Deze offerte is afgewezen"
        supporting-text={[
          quote.rejection?.rejected_at ? `Op ${formatDateTime(quote.rejection.rejected_at)}.` : '',
          quote.rejection?.reason ? `Reden: ${quote.rejection.reason}` : '',
        ]
          .filter(Boolean)
          .join(' ')}
      />
    );
  }
  if (quote.status === 'superseded') {
    return (
      <nldd-banner
        variant="neutral"
        text="Deze offerte is vervangen door een nieuwere"
        supporting-text="Besluiten kan alleen op de nieuwste offerte."
      />
    );
  }
  return null;
}

function Standing({ detail }: { detail: ReceivedQuoteDetail }) {
  const { quote } = detail;
  return (
    <Stack gap="related">
      <div>
        <nldd-badge
          color={QUOTE_STATUS_COLORS[quote.status] ?? 'neutral'}
          text={QUOTE_STATUS_LABELS[quote.status] ?? quote.status}
        />
      </div>
      <Quiet>
        Dit is de offerte zoals {detail.contractor_name ?? 'de opdrachtnemer'} hem heeft uitgegeven;
        de inhoud kan niet meer veranderen.
      </Quiet>
      <DecisionNotice detail={detail} />
    </Stack>
  );
}

function Deliveries({ deliveries }: { deliveries: Delivery[] }) {
  return (
    <nldd-table
      accessible-label="Verzending van het besluit"
      columns="minmax(160px,1fr) minmax(90px,auto)"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Bericht" />
        <nldd-text-cell text="Stand" />
      </nldd-table-row>
      {deliveries.map((delivery, index) => (
        <nldd-table-row key={`${delivery.operation}-${index}`}>
          <nldd-text-cell
            text={deliveryText(delivery)}
            supporting-text={[
              `Klaargezet ${formatDateTime(delivery.queued_at)}`,
              delivery.sent_at ? `aangekomen ${formatDateTime(delivery.sent_at)}` : '',
              delivery.status === 'pending' && (delivery.attempts ?? 0) > 0
                ? `${delivery.attempts} keer geprobeerd`
                : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          />
          <nldd-cell>
            <nldd-badge
              color={DELIVERY_COLORS[delivery.status] ?? 'neutral'}
              text={DELIVERY_SHORT[delivery.status] ?? delivery.status}
            />
          </nldd-cell>
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

/**
 * A quote a contractor sent: the frozen content as it was issued, the
 * decision of a tekenbevoegde, and whether the decision reached the
 * contractor. The page is the one an invited signer gets.
 */
export function ReceivedQuotePage() {
  const { quoteId = '' } = useParams();
  const instance = useInstance();

  const query = useQuery({
    queryKey: clientKeys.receivedQuote(quoteId),
    queryFn: () => fetchReceivedQuote(quoteId),
    retry: false,
    // While a decision is on its way, look again until it arrived.
    refetchInterval: (state) =>
      (state.state.data?.deliveries ?? []).some((delivery) => delivery.status === 'pending')
        ? 10_000
        : false,
  });

  const back = useDecisionReturn();
  // What was filled in before leaving for the login; only needed when the
  // browser comes back without a decision.
  const [draft] = useState(() => readDraft<DecisionDraft & Record<string, unknown>>(quoteId));
  if (back.evidenceId) clearDraft(quoteId);

  const detail = query.data;
  const quote = detail?.quote;
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const contractor = detail?.contractor_name ?? 'de opdrachtnemer';
  const deliveries = detail?.deliveries ?? [];

  // Asking for the intent decides nothing: the decision is made when the
  // browser is back from the identity provider.
  const createIntent = (decision: Decision, values: DecisionValues) => {
    saveDraft(quoteId, { decision, ...values });
    return createDecisionIntent({
      kind: decision === 'accept' ? 'accept_received' : 'reject_received',
      quote_id: quoteId,
      quote_hash: quote?.snapshot_hash ?? '',
      signer_function: values.signerFunction.trim() || null,
      note: decision === 'reject' ? values.reason.trim() || null : null,
      return_path: receivedQuotePath(quoteId),
    });
  };

  if (!detail || !quote) {
    return (
      <Page
        kind="document"
        title="Ontvangen offerte"
        instanceName={instance?.name}
        back={{ href: clientPath('offertes'), text: 'Terug naar ontvangen offertes' }}
      >
        {query.isPending ? <Loading /> : null}
        {query.isError && notFound ? <NotFound what="Deze offerte" /> : null}
        {query.isError && !notFound ? (
          <LoadError error={query.error} retry={() => void query.refetch()} />
        ) : null}
      </Page>
    );
  }

  const content = quote.content ?? null;
  return (
    <QuoteDecisionView
      title={`Offerte ${detail.assignment_name}`}
      instanceName={instance?.name}
      back={{ href: clientPath('offertes'), text: 'Terug naar ontvangen offertes' }}
      receipt={back.evidenceId ? { scope: 'proof', evidenceId: back.evidenceId } : null}
      notice={<Standing detail={detail} />}
      failure={
        back.errorCode && detail.may_decide ? { code: back.errorCode, dismiss: back.dismiss } : null
      }
      contractorName={contractor}
      signerLabel="je organisatie"
      content={content}
      unreadable={
        <EmptyNotice
          text="Je ziet de inhoud van deze offerte niet"
          supportingText="Bedragen en regels zijn zichtbaar voor de eigenaar van de aanvraag, een tekenbevoegde, een lezer en de beheerder."
        />
      }
      byline={[
        quote.reference ? `kenmerk ${quote.reference}` : null,
        `uitgegeven op ${formatDate(quote.issued_at)}`,
        quote.valid_until ? `geldig t/m ${formatDate(quote.valid_until)}` : null,
      ]
        .filter(Boolean)
        .join(' · ')}
      reference={quote.reference}
      documentHref={`/api/quotes/${quote.id}/document`}
      hash={quote.snapshot_hash}
      fileHash={quote.document_sha256}
      fileNote={quote.document_note}
      canDecide={detail.may_decide === true}
      draft={draft}
      createIntent={createIntent}
    >
      <RouterLinks>
        <nldd-link href={clientAssignmentPath(detail.assignment_id)} text="Bekijk de aanvraag" />
      </RouterLinks>
      {deliveries.length > 0 ? (
        <Section title="Verzending naar de opdrachtnemer">
          <Deliveries deliveries={deliveries} />
        </Section>
      ) : null}
    </QuoteDecisionView>
  );
}
