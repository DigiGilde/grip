import { Button } from '@/features/assignments/ui';
import { formatDate, formatEuro } from '@/lib/format';
import { Quiet, Stack } from '@/ui/layout';
import {
  QUOTE_STATUS_COLORS,
  QUOTE_STATUS_LABELS,
  quoteDocumentUrl,
  signedDocumentUrl,
  signingLink,
  type QuoteDetail,
  type QuoteOffer,
  type QuoteSummary,
} from './api';
import { formatDateTime } from './format';
import {
  invitationMessage,
  linkWorks,
  listedOffers,
  offerState,
  offerTitle,
  primaryAction,
  quoteSteps,
} from './offers';
import { CopyButton, DocumentLink, MenuAction } from './ui';
import './register';

export type CardAction =
  | { kind: 'offer' }
  | { kind: 'upload' }
  | { kind: 'reject' }
  | { kind: 'withdraw-link'; invitationId: string }
  | { kind: 'renew-link'; invitationId: string };

/** What the quote says about itself in one quiet line. */
function byline(quote: QuoteSummary): string {
  const parts = [
    quote.valid_until ? `Geldig t/m ${formatDate(quote.valid_until)}` : null,
    `Gemaakt op ${formatDate(quote.issued_at)}${quote.issued_by_name ? ` door ${quote.issued_by_name}` : ''}`,
  ];
  return parts.filter(Boolean).join(' · ');
}

function Decision({ quote }: { quote: QuoteSummary }) {
  const acceptance = quote.acceptance;
  if (acceptance) {
    const who = [
      acceptance.signer_name,
      acceptance.signer_function ? `(${acceptance.signer_function})` : null,
      acceptance.organisation_name ? `namens ${acceptance.organisation_name}` : null,
    ]
      .filter(Boolean)
      .join(' ');
    return (
      <nldd-text>
        Getekend op {formatDateTime(acceptance.signed_at)}
        {who ? ` door ${who}` : ''}.
      </nldd-text>
    );
  }
  if (quote.rejection) {
    return (
      <nldd-text>
        Afgewezen op {formatDateTime(quote.rejection.rejected_at)}
        {quote.rejection.reason ? `: ${quote.rejection.reason}` : '.'}
      </nldd-text>
    );
  }
  return null;
}

/** The fingerprint behind a quiet button: what it is for, the value, and a copy action. */
export function Fingerprint({ hash }: { hash: string }) {
  return (
    <nldd-button appearance="neutral-transparent" size="sm" text="Vingerafdruk" expandable>
      <nldd-popover slot="popup" accessible-label="Vingerafdruk van deze offerte" width="360px">
        <nldd-container padding="16" gap="8">
          <nldd-text size="sm">
            De vingerafdruk van deze offerte staat ook in het akkoord. Zo staat vast dat het
            akkoord over precies deze inhoud gaat.
          </nldd-text>
          <nldd-text size="xs" data-fingerprint>
            {hash}
          </nldd-text>
          <CopyButton text="Kopieer vingerafdruk" value={hash} size="sm" />
        </nldd-container>
      </nldd-popover>
    </nldd-button>
  );
}

function OfferRow({
  offer,
  quote,
  name,
  mayManage,
  onAction,
}: {
  offer: QuoteOffer;
  quote: QuoteSummary;
  name: string;
  mayManage: boolean;
  onAction: (action: CardAction) => void;
}) {
  const invitation = offer.invitation ?? null;
  const works = linkWorks(offer);
  const link = invitation ? signingLink(invitation.signing_path) : '';
  const open = quote.status === 'issued';
  return (
    <nldd-list-item>
      <nldd-text-cell
        text={offerTitle(offer)}
        supporting-text={`${offerState(offer, quote)} · aangeboden op ${formatDateTime(offer.offered_at)}`}
        {...(offer.delivery === 'refused' ? { color: 'critical' } : {})}
      />
      {mayManage && invitation && open ? (
        <nldd-cell width="fit-content">
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            {works ? (
              <>
                <CopyButton text="Kopieer tekenlink" value={link} size="sm" />
                <CopyButton
                  text="Kopieer bericht"
                  appearance="neutral-transparent"
                  size="sm"
                  value={invitationMessage({
                    reference: quote.reference,
                    name,
                    link,
                    email: offer.recipient,
                    expiresAt: invitation.expires_at,
                  })}
                />
              </>
            ) : null}
            <nldd-icon-button
              icon="more"
              size="sm"
              text={`Meer acties voor de tekenlink${offer.recipient ? ` aan ${offer.recipient}` : ''}`}
            >
              <nldd-menu slot="popup" placement="bottom-end">
                <MenuAction
                  text={works ? 'Verleng met 30 dagen' : 'Maak de tekenlink weer geldig'}
                  onSelect={() => onAction({ kind: 'renew-link', invitationId: invitation.id })}
                />
                {works ? (
                  <MenuAction
                    text="Trek de tekenlink in"
                    onSelect={() =>
                      onAction({ kind: 'withdraw-link', invitationId: invitation.id })
                    }
                  />
                ) : null}
              </nldd-menu>
            </nldd-icon-button>
          </nldd-container>
        </nldd-cell>
      ) : null}
    </nldd-list-item>
  );
}

interface QuoteCardProps {
  quote: QuoteSummary;
  /** The quote with its offers, once loaded. */
  detail: QuoteDetail | undefined;
  mayManage: boolean;
  busy: boolean;
  onAction: (action: CardAction) => void;
}

/**
 * One quote as one card: the amount, where it stands, and the one thing to
 * do next. Everything else is quiet.
 */
export function QuoteCard({ quote, detail, mayManage, busy, onAction }: QuoteCardProps) {
  const offers = detail?.offers ?? [];
  const listed = listedOffers(offers);
  const steps = quoteSteps(quote, offers);
  const next = mayManage && detail ? primaryAction(quote, offers) : null;
  const open = quote.status === 'issued';
  const name = detail?.content?.name ?? '';
  const current = steps.findIndex((step) => step.status === 'current') + 1;
  // The link with its validity, for the offer that still waits on a signature.
  const waiting = listed.find((offer) => linkWorks(offer));

  return (
    <nldd-card accessible-label={`Offerte ${quote.reference ?? ''}`.trim()}>
      <nldd-container padding="24" gap="24">
        <Stack gap="close">
          <nldd-title
            size={3}
            heading-level={3}
            overline={quote.reference ? `Offerte ${quote.reference}` : 'Offerte'}
            text={quote.total_cents !== undefined ? formatEuro(quote.total_cents) : 'Offerte'}
          >
            <nldd-badge
              slot="end"
              color={QUOTE_STATUS_COLORS[quote.status] ?? 'neutral'}
              text={
                open && offers.length > 0
                  ? 'Aangeboden'
                  : (QUOTE_STATUS_LABELS[quote.status] ?? quote.status)
              }
            />
          </nldd-title>
          <Quiet>{byline(quote)}</Quiet>
          {quote.snapshot_hash !== undefined ? (
            <nldd-container layout="row" gap="16" vertical-alignment="center">
              <DocumentLink href={quoteDocumentUrl(quote.id)} text="Bekijk" newTab />
              <DocumentLink href={quoteDocumentUrl(quote.id, true)} text="Download pdf" />
              {quote.acceptance?.has_document ? (
                <DocumentLink href={signedDocumentUrl(quote.id)} text="Getekend exemplaar" />
              ) : null}
              <Fingerprint hash={quote.snapshot_hash} />
            </nldd-container>
          ) : null}
        </Stack>

        <nldd-step-bar
          {...{ current: current > 0 ? current : steps.length + 1 }}
          accessible-label="Stappen van deze offerte"
          data-ready={detail ? 'true' : 'false'}
        >
          {steps.map((step) => (
            <nldd-step-bar-item key={step.text} text={step.text} />
          ))}
        </nldd-step-bar>

        <Decision quote={quote} />

        {listed.length > 0 ? (
          <Stack gap="close">
            <nldd-list accessible-label="Hoe deze offerte is aangeboden">
              {listed.map((offer) => (
                <OfferRow
                  key={offer.id}
                  offer={offer}
                  quote={quote}
                  name={name}
                  mayManage={mayManage}
                  onAction={onAction}
                />
              ))}
            </nldd-list>
            {mayManage && open && waiting?.invitation ? (
              <Quiet>
                Tekenlink: {signingLink(waiting.invitation.signing_path)}
                {waiting.invitation.expires_at
                  ? `, geldig t/m ${formatDate(waiting.invitation.expires_at)}`
                  : ''}
              </Quiet>
            ) : null}
          </Stack>
        ) : null}

        {mayManage && open && detail ? (
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            {next === 'offer' ? (
              <Button
                text="Bied aan"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: 'offer' })}
              />
            ) : null}
            {next === 'record-signed' ? (
              <Button
                text="Leg getekende pdf vast"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: 'upload' })}
              />
            ) : null}
            <nldd-icon-button icon="more" text="Meer acties voor deze offerte">
              <nldd-menu slot="popup" placement="bottom-start">
                {next !== 'offer' ? (
                  <MenuAction text="Bied opnieuw aan" onSelect={() => onAction({ kind: 'offer' })} />
                ) : null}
                {next !== 'record-signed' ? (
                  <MenuAction
                    text="Leg getekende pdf vast"
                    onSelect={() => onAction({ kind: 'upload' })}
                  />
                ) : null}
                <MenuAction text="Leg afwijzing vast" onSelect={() => onAction({ kind: 'reject' })} />
              </nldd-menu>
            </nldd-icon-button>
          </nldd-container>
        ) : null}
      </nldd-container>
    </nldd-card>
  );
}

/** An earlier quote in one line: its reference, date, amount and how it ended. */
export function EarlierQuoteRow({ quote }: { quote: QuoteSummary }) {
  const title = [quote.reference, formatDate(quote.issued_at)].filter(Boolean).join(' · ');
  return (
    <nldd-list-item>
      <nldd-text-cell
        text={title}
        supporting-text={QUOTE_STATUS_LABELS[quote.status] ?? quote.status}
      />
      {quote.total_cents !== undefined ? (
        <nldd-text-cell
          width="fit-content"
          horizontal-alignment="right"
          text={formatEuro(quote.total_cents)}
        />
      ) : null}
      {quote.snapshot_hash !== undefined ? (
        <nldd-cell width="fit-content">
          <nldd-link
            href={quoteDocumentUrl(quote.id)}
            text="Bekijk"
            size="md"
            target="_blank"
            accessible-label={`Bekijk offerte ${quote.reference ?? formatDate(quote.issued_at)}`}
          />
        </nldd-cell>
      ) : null}
    </nldd-list-item>
  );
}
