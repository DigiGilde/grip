import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError } from '@/api/client';
import { TextInput } from '@/features/assignments/ui';
import { formatDateTime } from '@/features/quotes/format';
import {
  QuoteDecisionView,
  type Decision,
  type DecisionDraft,
  type DecisionValues,
} from '@/features/quotes/QuoteDecisionView';
import {
  clearDraft,
  createSigningIntent,
  readDraft,
  saveDraft,
  useDecisionReturn,
} from '@/features/quotes/proof';
import { CheckboxInput } from '@/features/quotes/ui';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { LoadError, Loading, Page, StateNotice } from '@/ui/layout';
import { fetchSigningQuote, signingDocumentUrl, signingKeys, type SigningQuote } from './api';

function Decided({ quote }: { quote: SigningQuote }) {
  if (quote.status === 'accepted') {
    return (
      <nldd-banner
        variant="success"
        text="Deze offerte is getekend"
        supporting-text={
          quote.decided_at ? `Akkoord gegeven op ${formatDateTime(quote.decided_at)}.` : ''
        }
      />
    );
  }
  if (quote.status === 'rejected') {
    return (
      <nldd-banner
        variant="neutral"
        text="Deze offerte is afgewezen"
        supporting-text={
          quote.decided_at ? `Afgewezen op ${formatDateTime(quote.decided_at)}.` : ''
        }
      />
    );
  }
  return (
    <nldd-banner
      variant="neutral"
      text="Deze offerte is vervangen door een nieuwere"
      supporting-text="Vraag de opdrachtnemer om een uitnodiging voor de nieuwe offerte."
    />
  );
}

/** Who offers what, in one quiet line. */
function byline(quote: SigningQuote): string {
  return [
    quote.client_name ? `Aan ${quote.client_name}` : null,
    quote.reference ? `kenmerk ${quote.reference}` : null,
    quote.content.client_reference ? `jouw kenmerk ${quote.content.client_reference}` : null,
    quote.content.valid_until ? `geldig t/m ${formatDate(quote.content.valid_until)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

interface SigningDraft extends DecisionDraft, Record<string, unknown> {
  organisationName?: string;
}

/**
 * One quote, for the person invited to sign it. The page a director signs
 * on: the quote, the amount, who offers it, and one decision.
 */
export function SigningPage() {
  const { quoteId = '' } = useParams();
  const instance = useInstance();
  const query = useQuery({
    queryKey: signingKeys.quote(quoteId),
    queryFn: () => fetchSigningQuote(quoteId),
    retry: false,
  });

  const back = useDecisionReturn();
  // What was filled in before leaving for the login; only needed when the
  // browser comes back without a decision.
  const [draft] = useState(() => readDraft<SigningDraft>(quoteId));
  const [organisationName, setOrganisationName] = useState(draft?.organisationName ?? '');
  const [mandate, setMandate] = useState(false);
  if (back.evidenceId !== null) clearDraft(quoteId);

  const quote = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const client = quote?.client_name ?? null;

  // Asking for the intent decides nothing: the decision is made when the
  // browser is back from the identity provider.
  const createIntent = (decision: Decision, values: DecisionValues) => {
    if (!quote) return Promise.reject(new Error('De offerte is nog niet geladen.'));
    saveDraft(quoteId, { decision, ...values, organisationName });
    return createSigningIntent(quoteId, {
      decision,
      quote_hash: quote.snapshot_hash,
      return_path: `/tekenen/${quoteId}`,
      ...(decision === 'accept'
        ? {
            signer_function: values.signerFunction.trim() || null,
            organisation_name: client ? null : organisationName.trim(),
            confirm_mandate: true,
          }
        : { reason: values.reason.trim() || null }),
    });
  };

  const checkAccept = () => {
    if (!mandate) return 'Bevestig dat je namens de opdrachtgever mag tekenen.';
    if (!client && !organisationName.trim()) return 'Vul de organisatie in namens wie je tekent.';
    return null;
  };

  if (!quote) {
    return (
      <Page kind="document" title="Offerte tekenen" instanceName={instance?.name}>
        {query.isPending ? <Loading /> : null}
        {query.isError && notFound ? (
          <StateNotice
            state="not-found"
            text="Deze offerte staat niet voor je klaar"
            detail="De link klopt niet, de uitnodiging is verlopen of ingetrokken, of je bent ingelogd met een ander e-mailadres dan waarop je bent uitgenodigd."
          />
        ) : null}
        {query.isError && !notFound ? (
          <LoadError error={query.error} retry={() => void query.refetch()} />
        ) : null}
      </Page>
    );
  }

  return (
    <QuoteDecisionView
      title={`Offerte ${quote.content.name}`}
      instanceName={instance?.name}
      receipt={back.evidenceId ? { scope: 'signing', evidenceId: back.evidenceId } : null}
      notice={quote.status !== 'issued' ? <Decided quote={quote} /> : null}
      failure={
        back.errorCode && quote.status === 'issued'
          ? { code: back.errorCode, dismiss: back.dismiss }
          : null
      }
      contractorName={quote.contractor_name}
      signerLabel={client ?? 'je organisatie'}
      content={quote.content}
      byline={byline(quote)}
      reference={quote.reference}
      documentHref={signingDocumentUrl(quote.id)}
      hash={quote.snapshot_hash}
      fileHash={quote.document_sha256}
      fileNote={quote.document_note}
      canDecide={quote.status === 'issued'}
      draft={draft}
      createIntent={createIntent}
      checkAccept={checkAccept}
      acceptFields={
        <>
          {!client ? (
            <TextInput
              label="Organisatie namens wie je tekent"
              value={organisationName}
              onChange={setOrganisationName}
              required
            />
          ) : null}
          <CheckboxInput
            label={`Ik ben bevoegd om namens ${client ?? 'de opdrachtgever'} akkoord te geven op deze offerte`}
            checked={mandate}
            onChange={setMandate}
            required
          />
        </>
      }
    />
  );
}
