import { useState } from 'react';
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
import { QuoteContentTable } from '@/features/quotes/QuoteContentTable';
import { CheckboxInput, DocumentLink } from '@/features/quotes/ui';
import { formatDateTime } from '@/features/quotes/format';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import {
  acceptQuote,
  fetchSigningQuote,
  rejectQuote,
  signingDocumentUrl,
  signingKeys,
  type SigningQuote,
} from './api';

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
      supporting-text="Tekenen kan niet meer. Vraag de opdrachtnemer om een uitnodiging voor de nieuwe offerte."
    />
  );
}

/** One quote, for the person invited to sign it: read, then accept or reject. */
export function SigningPage() {
  const { quoteId = '' } = useParams();
  const instance = useInstance();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: signingKeys.quote(quoteId),
    queryFn: () => fetchSigningQuote(quoteId),
    retry: false,
  });

  const [signerFunction, setSignerFunction] = useState('');
  const [organisationName, setOrganisationName] = useState('');
  const [mandate, setMandate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [rejectError, setRejectError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: (action: () => Promise<SigningQuote>) => action(),
    onSuccess: (updated) => {
      queryClient.setQueryData(signingKeys.quote(quoteId), updated);
      setRejecting(false);
      setError(null);
    },
  });

  const quote = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const title = quote ? `Offerte ${quote.content.name}` : 'Offerte tekenen';
  const client = quote?.client_name ?? null;

  const accept = () => {
    if (!quote) return;
    if (!mandate) {
      setError('Bevestig dat je namens de opdrachtgever mag tekenen.');
      return;
    }
    if (!client && !organisationName.trim()) {
      setError('Vul de organisatie in namens wie je tekent.');
      return;
    }
    setError(null);
    decide.mutate(
      () =>
        acceptQuote(quote.id, {
          quote_hash: quote.snapshot_hash,
          signer_function: signerFunction.trim() || null,
          organisation_name: client ? null : organisationName.trim(),
          confirm_mandate: true,
        }),
      { onError: (failure) => setError(errorMessage(failure)) },
    );
  };

  return (
    <>
      <nldd-simple-section>
        <PageHeading text={title} instanceName={instance?.name} />
        {query.isPending ? <Loading /> : null}
        {query.isError && notFound ? (
          <EmptyNotice
            text="Deze offerte staat niet voor je klaar"
            supportingText="De link klopt niet, de uitnodiging is verlopen, of je bent ingelogd met een ander e-mailadres dan waarop je bent uitgenodigd."
          />
        ) : null}
        {query.isError && !notFound ? <ErrorNotice message={errorMessage(query.error)} /> : null}

        {quote ? (
          <nldd-container gap="16">
            {quote.status !== 'issued' ? <Decided quote={quote} /> : null}
            <nldd-text>
              Van {quote.contractor_name}
              {client ? ` aan ${client}` : ''}, uitgegeven op {formatDateTime(quote.issued_at)}
              {quote.content.valid_until
                ? `, geldig tot en met ${formatDate(quote.content.valid_until)}`
                : ''}
              .
            </nldd-text>
            <QuoteContentTable content={quote.content} label="Regels van de offerte" />
            {quote.content.conditions ? (
              <>
                <SectionHeading text="Voorwaarden" />
                <nldd-text>{quote.content.conditions}</nldd-text>
              </>
            ) : null}
            <nldd-container layout="wrap" gap="16">
              <DocumentLink
                href={signingDocumentUrl(quote.id)}
                text="Bekijk de offerte als document"
                newTab
              />
              <DocumentLink href={signingDocumentUrl(quote.id, true)} text="Download de offerte" />
            </nldd-container>
            <nldd-text size="sm">
              Controlegetal van deze offerte (SHA-256): {quote.snapshot_hash}. Hetzelfde getal
              staat onderaan het document. Je akkoord geldt voor precies deze inhoud.
            </nldd-text>
          </nldd-container>
        ) : null}
      </nldd-simple-section>

      {quote && quote.status === 'issued' ? (
        <nldd-simple-section>
          <SectionHeading text="Akkoord geven" />
          {error ? <nldd-banner variant="critical" size="sm" text={error} /> : null}
          <nldd-container gap="16">
            <TextInput
              label="Je functie"
              value={signerFunction}
              onChange={setSignerFunction}
              optional
            />
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
            <nldd-text size="sm">
              Met je akkoord leggen we vast wie je bent, namens welke organisatie je tekent en
              op welk moment. Een akkoord is niet terug te draaien.
            </nldd-text>
            <nldd-button-group>
              <Button
                text="Geef akkoord"
                appearance="primary"
                loading={decide.isPending && !rejecting}
                onClick={accept}
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

      <FormSheet
        open={rejecting}
        title="Offerte afwijzen"
        submitText="Wijs af"
        busy={decide.isPending && rejecting}
        error={rejectError}
        onClose={() => setRejecting(false)}
        onSubmit={() => {
          if (!quote) return;
          decide.mutate(
            () =>
              rejectQuote(quote.id, {
                quote_hash: quote.snapshot_hash,
                reason: reason.trim() || null,
              }),
            { onError: (failure) => setRejectError(errorMessage(failure)) },
          );
        }}
      >
        <nldd-text>
          De opdrachtnemer ziet dat de offerte is afgewezen, met de reden die je hier geeft.
          Afwijzen is niet terug te draaien.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} optional multiline />
      </FormSheet>
    </>
  );
}
