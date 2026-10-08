import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { Button, TextInput } from '@/features/assignments/ui';
import { useInstance } from '@/layout/useInstance';
import { formatEuro } from '@/lib/format';
import {
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  Loading,
  Page,
  Quiet,
  Section,
  Stack,
} from '@/ui/layout';
import {
  approvalKeys,
  approvalLine,
  approvalPath,
  approverDocumentUrl,
  fetchApproverQuote,
  type ApproverQuote,
} from './approval';
import { DecisionFailed, DecisionReceipt } from './DecisionReceipt';
import { formatDateTime } from './format';
import {
  beforeLeaving,
  clearDraft,
  createDecisionIntent,
  leaveForDecision,
  readDraft,
  saveDraft,
  useDecisionReturn,
} from './proof';
import { QuoteContentTable } from './QuoteContentTable';
import { QuoteDetails } from './QuoteDetails';
import { DocumentLink } from './ui';

type Choice = 'approve' | 'send_back';

/** For whom, under which reference, and who asks. */
function byline(quote: ApproverQuote): string {
  const request = quote.approval.current;
  return [
    quote.client_name ? `Voor ${quote.client_name}` : null,
    quote.quote_reference ? `kenmerk ${quote.quote_reference}` : null,
    request?.requested_by_name
      ? `gevraagd door ${request.requested_by_name} op ${formatDateTime(request.requested_at)}`
      : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * One quote, for whoever approves it inside the organisation before it goes
 * to the client: the quote as the client will see it, who asks, and one
 * decision. The sibling of the page a client signs on.
 */
export function ApprovalPage() {
  const { quoteId = '' } = useParams();
  const instance = useInstance();
  const query = useQuery({
    queryKey: approvalKeys.approverQuote(quoteId),
    queryFn: () => fetchApproverQuote(quoteId),
    retry: false,
  });

  const [sheet, setSheet] = useState<Choice | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const back = useDecisionReturn();
  const [draft] = useState(() => readDraft<{ decision?: Choice; note?: string }>(quoteId));
  // Asking for the intent decides nothing: the decision is made when the
  // browser is back from the identity provider.
  const decide = useMutation({
    mutationFn: (decision: Choice) => {
      saveDraft(quoteId, { decision, note });
      return createDecisionIntent({
        kind: decision,
        quote_id: quoteId,
        quote_hash: query.data?.snapshot_hash ?? '',
        note: note.trim() || null,
        return_path: approvalPath(quoteId),
      });
    },
    onSuccess: leaveForDecision,
    onError: (failure) => setError(errorMessage(failure)),
  });
  if (back.evidenceId) clearDraft(quoteId);

  const quote = query.data;
  const approval = quote?.approval;
  const hidden =
    query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 403);
  const open = (next: Choice, keep = '') => {
    setError(null);
    setNote(keep);
    setSheet(next);
  };
  const waiting = approval?.status === 'requested';

  return (
    <>
      <Page
        title={quote ? `Offerte ${quote.assignment_name}` : 'Offerte goedkeuren'}
        instanceName={instance?.name}
        width="960px"
      >
        {query.isPending ? <Loading /> : null}
        {query.isError && hidden ? (
          <EmptyNotice
            text="Deze offerte staat niet voor je klaar"
            supportingText="Er is geen goedkeuring voor gevraagd, of je hebt het recht om offertes goed te keuren niet."
          />
        ) : null}
        {query.isError && !hidden ? <ErrorNotice message={errorMessage(query.error)} /> : null}

        {quote && approval ? (
          <>
            {back.evidenceId ? (
              <DecisionReceipt scope="proof" evidenceId={back.evidenceId} />
            ) : null}
            {back.errorCode && waiting ? (
              <DecisionFailed
                code={back.errorCode}
                onRetry={() => {
                  back.dismiss();
                  open(draft?.decision ?? 'approve', draft?.note ?? '');
                }}
              />
            ) : null}
            {approval.status === 'approved' && !back.evidenceId ? (
              <nldd-banner
                variant="success"
                text="Deze offerte is goedgekeurd"
                supporting-text={approvalLine(approval) ?? ''}
              />
            ) : null}
            {approval.status === 'sent_back' && !back.evidenceId ? (
              <nldd-banner
                variant="neutral"
                text="Deze offerte is teruggestuurd"
                supporting-text={approvalLine(approval) ?? ''}
              />
            ) : null}
            {approval.status === 'withdrawn' || approval.status === 'none' ? (
              <nldd-banner variant="neutral" text="Er wordt nu geen goedkeuring gevraagd" />
            ) : null}

            <Stack gap="close">
              <nldd-title
                size={3}
                heading-level={2}
                overline="Ter goedkeuring"
                text={quote.total_cents !== undefined ? formatEuro(quote.total_cents) : 'Offerte'}
              />
              <Quiet>{byline(quote)}</Quiet>
            </Stack>

            {approval.current?.request_note ? (
              <Section title="Toelichting bij de aanvraag" level={2}>
                <nldd-text>{approval.current.request_note}</nldd-text>
              </Section>
            ) : null}

            {quote.content ? (
              <QuoteContentTable content={quote.content} label="Regels van de offerte" />
            ) : null}

            {quote.content?.conditions ? (
              <Section title="Voorwaarden" level={2}>
                <nldd-text>{quote.content.conditions}</nldd-text>
              </Section>
            ) : null}

            <nldd-container layout="row" gap="16" vertical-alignment="center">
              <DocumentLink href={approverDocumentUrl(quote.quote_id)} text="Bekijk pdf" newTab />
              {quote.snapshot_hash ? (
                <QuoteDetails
                  hash={quote.snapshot_hash}
                  documentHref={approverDocumentUrl(quote.quote_id)}
                  facts={[{ label: 'Kenmerk', value: quote.quote_reference ?? '' }]}
                />
              ) : null}
            </nldd-container>

            {waiting && approval.may_decide_approval ? (
              <Stack gap="related">
                <nldd-text>
                  Na je goedkeuring kan de offerte naar de opdrachtgever. Vastgelegd wordt wie
                  goedkeurde en wanneer; de opdrachtgever ziet dat niet.
                </nldd-text>
                <nldd-button-group>
                  <Button text="Keur goed" appearance="primary" onClick={() => open('approve')} />
                  <Button text="Stuur terug" onClick={() => open('send_back')} />
                </nldd-button-group>
              </Stack>
            ) : null}
            {waiting && !approval.may_decide_approval ? (
              <Quiet>Je vroeg deze goedkeuring zelf; een andere collega beslist.</Quiet>
            ) : null}
          </>
        ) : null}
      </Page>

      <FormSheet
        open={sheet === 'approve'}
        title="Offerte goedkeuren"
        submitText="Log in en keur goed"
        busy={decide.isPending && sheet === 'approve'}
        error={sheet === 'approve' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => decide.mutate('approve')}
      >
        <nldd-text>
          Je keurt offerte {quote?.quote_reference ?? ''} van{' '}
          {quote?.total_cents !== undefined ? formatEuro(quote.total_cents) : ''} goed.
        </nldd-text>
        <nldd-text>{beforeLeaving('approve', Boolean(decide.data?.passkey))}</nldd-text>
        <TextInput label="Opmerking" value={note} onChange={setNote} optional multiline />
      </FormSheet>

      <FormSheet
        open={sheet === 'send_back'}
        title="Offerte terugsturen"
        submitText="Log in en stuur terug"
        busy={decide.isPending && sheet === 'send_back'}
        error={sheet === 'send_back' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => {
          if (!note.trim()) {
            setError('Schrijf op wat er anders moet.');
            return;
          }
          decide.mutate('send_back');
        }}
      >
        <nldd-text>
          Wie de offerte maakte leest je toelichting en maakt een nieuwe offerte.
        </nldd-text>
        <nldd-text>{beforeLeaving('send_back', Boolean(decide.data?.passkey))}</nldd-text>
        <TextInput label="Wat moet er anders" value={note} onChange={setNote} required multiline />
      </FormSheet>
    </>
  );
}
