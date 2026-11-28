import type { ReactNode } from 'react';
import { QUOTE_STATUS_COLORS, quoteDocumentUrl } from '@/features/quotes/api';
import { shortHash } from '@/features/quotes/format';
import { QuoteContentTable } from '@/features/quotes/QuoteContentTable';
import { formatDate, formatEuro } from '@/lib/format';
import { DocumentLink } from '@/ui/Icon';
import { Facts, NameLine, Quiet, Section, Stack, type Fact } from '@/ui/layout';
import type { StandQuote } from './api';
import {
  acceptanceTold,
  approvalTold,
  offerTold,
  rejectionTold,
  standQuoteLabel,
  type Told,
} from './words';

function ToldLines({ lines }: { lines: readonly Told[] }): ReactNode {
  if (lines.length === 0) return null;
  return (
    <Stack gap="close">
      {lines.map((line) => (
        <Stack key={`${line.text} ${line.note ?? ''}`} gap="tight">
          <nldd-text>
            <p>{line.text}</p>
          </nldd-text>
          {line.note ? <Quiet>{line.note}</Quiet> : null}
        </Stack>
      ))}
    </Stack>
  );
}

function quoteFacts(quote: StandQuote): Fact[] {
  const facts: Fact[] = [
    { label: 'Offertebedrag', value: formatEuro(quote.total_cents) },
    { label: 'Gemaakt', value: formatDate(quote.issued_at) },
    { label: 'Geldig t/m', value: formatDate(quote.valid_until) },
    { label: 'Echtheidskenmerk', value: shortHash(quote.snapshot_hash) },
    {
      label: 'Bestandskenmerk',
      value: quote.has_document ? shortHash(quote.document_sha256 ?? undefined) : '',
    },
  ];
  const told = (label: string, lines: readonly Told[]) => {
    if (lines.length > 0) facts.push({ label, value: <ToldLines lines={lines} /> });
  };
  told('Interne goedkeuring', (quote.approvals ?? []).map(approvalTold));
  told('Aangeboden', (quote.offers ?? []).map(offerTold));
  told('Akkoord', quote.acceptance ? [acceptanceTold(quote.acceptance)] : []);
  told('Afwijzing', quote.rejection ? [rejectionTold(quote.rejection)] : []);
  return facts.filter((fact) => fact.value !== '');
}

function QuoteAtMoment({ quote }: { quote: StandQuote }) {
  const name = quote.reference ? `Offerte ${quote.reference}` : 'Offerte';
  const facts = quoteFacts(quote);
  return (
    <Stack gap="related">
      <NameLine
        badges={
          <nldd-badge
            color={QUOTE_STATUS_COLORS[quote.status] ?? 'neutral'}
            text={standQuoteLabel(quote)}
          />
        }
      >
        <nldd-text>
          <span>{name}</span>
        </nldd-text>
      </NameLine>
      {facts.length > 0 && <Facts label={`Gegevens van ${name}`} facts={facts} omitEmpty />}
      {/* Only a document that existed then: the live route could otherwise lay one out now. */}
      {quote.has_document && (
        <nldd-container layout="row">
          <DocumentLink href={quoteDocumentUrl(quote.id)} text="Bekijk pdf" kind="view" />
        </nldd-container>
      )}
      {quote.content && <QuoteContentTable content={quote.content} label={`Regels van ${name}`} />}
    </Stack>
  );
}

function replacedText(quote: StandQuote): string {
  const name = quote.reference ?? 'zonder kenmerk';
  return quote.total_cents !== undefined ? `${name} (${formatEuro(quote.total_cents)})` : name;
}

/** The quotes as they stood: what this moment changed first, the replaced ones in one line. */
export function StandQuotesPart({ quotes }: { quotes: readonly StandQuote[] }) {
  if (quotes.length === 0) return null;
  const current = quotes.filter((quote) => quote.status !== 'superseded');
  const replaced = quotes.filter((quote) => quote.status === 'superseded');
  const ordered = [
    ...current.filter((quote) => quote.changed),
    ...current.filter((quote) => !quote.changed),
  ];
  return (
    <Section title={ordered.length > 1 ? 'Offertes' : 'Offerte'} level={3}>
      <Stack gap="group">
        {ordered.map((quote) => (
          <QuoteAtMoment key={quote.id} quote={quote} />
        ))}
        {replaced.length > 0 && <Quiet>Vervangen: {replaced.map(replacedText).join(', ')}</Quiet>}
      </Stack>
    </Section>
  );
}
