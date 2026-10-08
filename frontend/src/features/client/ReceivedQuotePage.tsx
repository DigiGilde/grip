import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import {
  Button,
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  Loading,
  SectionHeading,
  TextInput,
} from '@/features/assignments/ui';
import {
  ACCEPTANCE_FORM_LABELS,
  QUOTE_STATUS_COLORS,
  QUOTE_STATUS_LABELS,
} from '@/features/quotes/api';
import { formatDateTime } from '@/features/quotes/format';
import { QuoteContentTable } from '@/features/quotes/QuoteContentTable';
import { ConfirmDialog } from '@/features/team/ui/overlays';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatDate } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import {
  acceptReceivedQuote,
  clientKeys,
  fetchReceivedQuote,
  rejectReceivedQuote,
  type Delivery,
  type ReceivedQuoteDetail,
} from './api';
import { DELIVERY_COLORS, DELIVERY_SHORT, deliveryText } from './labels';
import { clientAssignmentPath, clientPath } from './paths';
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

function Deliveries({ deliveries }: { deliveries: Delivery[] }) {
  return (
    <nldd-table
      accessible-label="Verzending van het besluit"
      columns="minmax(260px,2fr) 190px 190px"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Bericht" />
        <nldd-text-cell text="Stand" />
        <nldd-text-cell text="Klaargezet" />
      </nldd-table-row>
      {deliveries.map((delivery, index) => (
        <nldd-table-row key={`${delivery.operation}-${index}`}>
          <nldd-text-cell
            text={deliveryText(delivery)}
            {...(delivery.status === 'pending' && (delivery.attempts ?? 0) > 0
              ? { 'supporting-text': `${delivery.attempts} keer geprobeerd` }
              : {})}
          />
          <nldd-cell>
            <nldd-badge
              color={DELIVERY_COLORS[delivery.status] ?? 'neutral'}
              text={DELIVERY_SHORT[delivery.status] ?? delivery.status}
            />
          </nldd-cell>
          <nldd-text-cell
            text={formatDateTime(delivery.queued_at)}
            {...(delivery.sent_at
              ? { 'supporting-text': `Aangekomen ${formatDateTime(delivery.sent_at)}` }
              : {})}
          />
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

/**
 * A quote a contractor sent: the frozen content as it was issued, its hash,
 * the decision of a tekenbevoegde, and whether the decision reached the
 * contractor.
 */
export function ReceivedQuotePage() {
  const { quoteId = '' } = useParams();
  const instance = useInstance();
  const queryClient = useQueryClient();
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);

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

  const [signerFunction, setSignerFunction] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [rejectError, setRejectError] = useState<string | null>(null);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: clientKeys.all });
  };
  const accept = useMutation({
    mutationFn: () => acceptReceivedQuote(quoteId, signerFunction.trim() || null),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  const reject = useMutation({
    mutationFn: () => rejectReceivedQuote(quoteId, reason.trim() || null),
    onSuccess: () => {
      setRejecting(false);
      setRejectError(null);
      refresh();
    },
    onError: (failure) => setRejectError(errorMessage(failure)),
  });

  const detail = query.data;
  const quote = detail?.quote;
  const content = quote?.content ?? null;
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const contractor = detail?.contractor_name ?? 'de opdrachtnemer';
  const deliveries = detail?.deliveries ?? [];

  return (
    <div ref={ref}>
      <nldd-simple-section>
        <PageHeading
          text={detail ? `Offerte voor ${detail.assignment_name}` : 'Ontvangen offerte'}
          instanceName={instance?.name}
        />
        <nldd-container gap="16">
          <nldd-link href={clientPath('offertes')} text="Terug naar ontvangen offertes" />
          {query.isPending ? <Loading /> : null}
          {query.isError && notFound ? (
            <EmptyNotice
              text="Deze offerte is niet gevonden"
              supportingText="Hij bestaat niet, of je bent er niet bij betrokken."
            />
          ) : null}
          {query.isError && !notFound ? <ErrorNotice message={errorMessage(query.error)} /> : null}

          {detail && quote ? (
            <>
              <div>
                <nldd-badge
                  color={QUOTE_STATUS_COLORS[quote.status] ?? 'neutral'}
                  text={QUOTE_STATUS_LABELS[quote.status] ?? quote.status}
                />
              </div>
              <DecisionNotice detail={detail} />
              <nldd-text>
                Van {contractor}, uitgegeven op {formatDateTime(quote.issued_at)}
                {quote.valid_until ? `, geldig tot en met ${formatDate(quote.valid_until)}` : ''}.
                Dit is de offerte zoals de opdrachtnemer hem heeft uitgegeven; de inhoud kan niet
                meer veranderen.
              </nldd-text>
              <nldd-link
                href={clientAssignmentPath(detail.assignment_id)}
                text="Bekijk de aanvraag waar deze offerte bij hoort"
              />
              {content ? (
                <>
                  <QuoteContentTable content={content} label="Regels van de offerte" />
                  {content.conditions ? (
                    <>
                      <SectionHeading text="Voorwaarden" />
                      <nldd-text>{content.conditions}</nldd-text>
                    </>
                  ) : null}
                </>
              ) : (
                <EmptyNotice
                  text="Je ziet de inhoud van deze offerte niet"
                  supportingText="Bedragen en regels zijn zichtbaar voor de eigenaar van de aanvraag, een tekenbevoegde, een lezer en de beheerder."
                />
              )}
              {quote.snapshot_hash ? (
                <nldd-text size="sm">
                  Controlegetal van deze offerte (SHA-256): {quote.snapshot_hash}. De
                  opdrachtnemer heeft hetzelfde getal. Een akkoord geldt voor precies deze inhoud.
                </nldd-text>
              ) : null}
            </>
          ) : null}
        </nldd-container>
      </nldd-simple-section>

      {detail?.may_decide ? (
        <nldd-simple-section>
          <SectionHeading text="Besluiten" />
          <nldd-container gap="16">
            {error ? <nldd-banner variant="critical" size="sm" text={error} /> : null}
            <nldd-text>
              Je bent tekenbevoegd voor deze organisatie. Met je akkoord leggen we vast wie je
              bent, namens welke organisatie je tekent en op welk moment. Het akkoord wordt
              ondertekend met de sleutel van deze instantie en naar {contractor} gestuurd.
            </nldd-text>
            <TextInput
              label="Je functie"
              value={signerFunction}
              onChange={setSignerFunction}
              optional
              hint="Staat bij je akkoord, bijvoorbeeld Directeur."
            />
            <nldd-button-group>
              <Button
                text="Geef akkoord"
                appearance="primary"
                loading={accept.isPending}
                onClick={() => setConfirming(true)}
              />
              <Button
                text="Wijs af"
                onClick={() => {
                  setRejectError(null);
                  setRejecting(true);
                }}
              />
            </nldd-button-group>
          </nldd-container>
        </nldd-simple-section>
      ) : null}

      {deliveries.length > 0 ? (
        <nldd-simple-section>
          <SectionHeading text="Verzending naar de opdrachtnemer" />
          <Deliveries deliveries={deliveries} />
        </nldd-simple-section>
      ) : null}

      <ConfirmDialog
        open={confirming}
        text="Akkoord geven op deze offerte?"
        supportingText={`Je geeft namens deze organisatie akkoord aan ${contractor}. Een akkoord is niet terug te draaien.`}
        confirmText="Geef akkoord"
        onClose={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          accept.mutate();
        }}
      />
      <FormSheet
        open={rejecting}
        title="Offerte afwijzen"
        submitText="Wijs af"
        busy={reject.isPending}
        error={rejectError}
        onClose={() => setRejecting(false)}
        onSubmit={() => reject.mutate()}
      >
        <nldd-text>
          {contractor} ziet dat de offerte is afgewezen, met de reden die je hier geeft. Afwijzen
          is niet terug te draaien.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} optional multiline />
      </FormSheet>
    </div>
  );
}
