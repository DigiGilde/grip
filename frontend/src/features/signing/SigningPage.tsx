import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { Button, TextInput } from '@/features/assignments/ui';
import { Fingerprint } from '@/features/quotes/QuoteCard';
import { QuoteContentTable } from '@/features/quotes/QuoteContentTable';
import { formatDateTime } from '@/features/quotes/format';
import { CheckboxInput, DocumentLink } from '@/features/quotes/ui';
import { useInstance } from '@/layout/useInstance';
import { formatDate, formatEuro } from '@/lib/format';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, Page, Quiet, Section, Stack } from '@/ui/layout';
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
      supporting-text="Vraag de opdrachtnemer om een uitnodiging voor de nieuwe offerte."
    />
  );
}

/** Who offers what, in one quiet line. */
function byline(quote: SigningQuote): string {
  return [
    quote.client_name ? `Aan ${quote.client_name}` : null,
    quote.reference ? `kenmerk ${quote.reference}` : null,
    quote.content.client_reference ? `uw kenmerk ${quote.content.client_reference}` : null,
    quote.content.valid_until ? `geldig t/m ${formatDate(quote.content.valid_until)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * One quote, for the person invited to sign it. The page a director signs
 * on: the quote, the amount, who offers it, and one decision.
 */
export function SigningPage() {
  const { quoteId = '' } = useParams();
  const instance = useInstance();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: signingKeys.quote(quoteId),
    queryFn: () => fetchSigningQuote(quoteId),
    retry: false,
  });

  const [sheet, setSheet] = useState<'accept' | 'reject' | null>(null);
  const [signerFunction, setSignerFunction] = useState('');
  const [organisationName, setOrganisationName] = useState('');
  const [mandate, setMandate] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: (action: () => Promise<SigningQuote>) => action(),
    onSuccess: (updated) => {
      queryClient.setQueryData(signingKeys.quote(quoteId), updated);
      setSheet(null);
      setError(null);
    },
    onError: (failure) => setError(errorMessage(failure)),
  });

  const quote = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const title = quote ? `Offerte ${quote.content.name}` : 'Offerte tekenen';
  const client = quote?.client_name ?? null;
  const open = (next: 'accept' | 'reject') => {
    setError(null);
    setSheet(next);
  };

  return (
    <>
      <Page title={title} instanceName={instance?.name} width="960px">
        {query.isPending ? <Loading /> : null}
        {query.isError && notFound ? (
          <EmptyNotice
            text="Deze offerte staat niet voor je klaar"
            supportingText="De link klopt niet, de uitnodiging is verlopen of ingetrokken, of je bent ingelogd met een ander e-mailadres dan waarop je bent uitgenodigd."
          />
        ) : null}
        {query.isError && !notFound ? <ErrorNotice message={errorMessage(query.error)} /> : null}

        {quote ? (
          <>
            {quote.status !== 'issued' ? <Decided quote={quote} /> : null}
            <Stack gap="close">
              <nldd-title
                size={3}
                heading-level={2}
                overline={`${quote.contractor_name} biedt aan`}
                text={formatEuro(quote.content.total_cents)}
              />
              <Quiet>{byline(quote)}</Quiet>
            </Stack>

            <QuoteContentTable content={quote.content} label="Regels van de offerte" />

            {quote.content.conditions ? (
              <Section title="Voorwaarden" level={2}>
                <nldd-text>{quote.content.conditions}</nldd-text>
              </Section>
            ) : null}

            <nldd-container layout="row" gap="16" vertical-alignment="center">
              <DocumentLink href={signingDocumentUrl(quote.id)} text="Bekijk als document" newTab />
              <DocumentLink href={signingDocumentUrl(quote.id, true)} text="Download pdf" />
              <Fingerprint hash={quote.snapshot_hash} />
            </nldd-container>

            {quote.status === 'issued' ? (
              <Stack gap="related">
                <nldd-text>
                  Met je akkoord gaat {client ?? 'je organisatie'} deze opdracht aan voor dit
                  bedrag. Vastgelegd wordt wie je bent, namens wie je tekent en wanneer.
                </nldd-text>
                <nldd-button-group>
                  <Button text="Geef akkoord" appearance="primary" onClick={() => open('accept')} />
                  <Button text="Wijs af" onClick={() => open('reject')} />
                </nldd-button-group>
              </Stack>
            ) : null}
          </>
        ) : null}
      </Page>

      <FormSheet
        open={sheet === 'accept'}
        title="Akkoord geven"
        submitText="Geef akkoord"
        busy={decide.isPending && sheet === 'accept'}
        error={sheet === 'accept' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => {
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
          decide.mutate(() =>
            acceptQuote(quote.id, {
              quote_hash: quote.snapshot_hash,
              signer_function: signerFunction.trim() || null,
              organisation_name: client ? null : organisationName.trim(),
              confirm_mandate: true,
            }),
          );
        }}
      >
        <nldd-text>
          Je geeft akkoord op offerte {quote?.reference ?? ''} van{' '}
          {quote ? formatEuro(quote.content.total_cents) : ''}. Een akkoord is niet terug te
          draaien.
        </nldd-text>
        <TextInput label="Je functie" value={signerFunction} onChange={setSignerFunction} optional />
        {quote && !client ? (
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
      </FormSheet>

      <FormSheet
        open={sheet === 'reject'}
        title="Offerte afwijzen"
        submitText="Wijs af"
        busy={decide.isPending && sheet === 'reject'}
        error={sheet === 'reject' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => {
          if (!quote) return;
          decide.mutate(() =>
            rejectQuote(quote.id, {
              quote_hash: quote.snapshot_hash,
              reason: reason.trim() || null,
            }),
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
