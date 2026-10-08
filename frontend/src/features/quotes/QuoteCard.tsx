import { DocumentLink as SharedDocumentLink, MoreButton } from '@/ui/Icon';
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
import { APPROVER_RIGHT, approvalLine, awaitsApproval, type ApprovalState } from './approval';
import { formatDateTime } from './format';
import {
  invitationMessage,
  linkWorks,
  listedOffers,
  mailLine,
  offerState,
  offerTitle,
  primaryAction,
} from './offers';
import { bundleUrl, statementPageUrl, type QuoteEvidenceRow } from './proof';
import { QuoteDetails } from './QuoteDetails';
import { CopyButton, DocumentLink, MenuAction } from './ui';
import './register';

export type CardAction =
  | { kind: 'offer' }
  | { kind: 'upload' }
  | { kind: 'reject' }
  | { kind: 'request-approval' }
  | { kind: 'withdraw-approval' }
  | { kind: 'review' }
  | { kind: 'new-quote' }
  | { kind: 'grant-right' }
  | { kind: 'withdraw-link'; invitationId: string }
  | { kind: 'renew-link'; invitationId: string }
  | { kind: 'resend-mail'; invitationId: string };

function madeText(quote: QuoteSummary): string {
  return `Gemaakt op ${formatDate(quote.issued_at)}${quote.issued_by_name ? ` door ${quote.issued_by_name}` : ''}`;
}

/** What the quote says about itself in one quiet line. */
function byline(quote: QuoteSummary): string {
  return [quote.valid_until ? `Geldig t/m ${formatDate(quote.valid_until)}` : null, madeText(quote)]
    .filter(Boolean)
    .join(' · ');
}

/** How the decision is backed: the proof to look at, or that there is none. */
function DecisionProof({
  decision,
  evidence,
  mayManage,
}: {
  decision: 'accept' | 'reject';
  evidence: readonly QuoteEvidenceRow[] | undefined;
  mayManage: boolean;
}) {
  // Not known (still loading, or not for this reader): say nothing.
  if (evidence === undefined) return null;
  const row = evidence.find((item) => item.decision === decision);
  if (!row) return <Quiet>Zonder bewijspakket vastgelegd.</Quiet>;
  return (
    <nldd-container layout="row" gap="16" vertical-alignment="center">
      <DocumentLink href={statementPageUrl('proof', row.id)} text="Bekijk bewijs" newTab />
      {mayManage ? (
        <DocumentLink href={bundleUrl('proof', row.id)} text="Download bewijs" download />
      ) : null}
    </nldd-container>
  );
}

function Decision({
  quote,
  evidence,
  mayManage,
}: {
  quote: QuoteSummary;
  evidence: readonly QuoteEvidenceRow[] | undefined;
  mayManage: boolean;
}) {
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
      <Stack gap="close">
        <nldd-text>
          Getekend op {formatDateTime(acceptance.signed_at)}
          {who ? ` door ${who}` : ''}.
        </nldd-text>
        <DecisionProof decision="accept" evidence={evidence} mayManage={mayManage} />
      </Stack>
    );
  }
  if (quote.rejection) {
    return (
      <Stack gap="close">
        <nldd-text>
          Afgewezen op {formatDateTime(quote.rejection.rejected_at)}
          {quote.rejection.reason ? `: ${quote.rejection.reason}` : '.'}
        </nldd-text>
        <DecisionProof decision="reject" evidence={evidence} mayManage={mayManage} />
      </Stack>
    );
  }
  return null;
}

/**
 * One offer: how it went out, where it stands, and for a signing link the
 * link itself with its actions. Stacked, so the link and its buttons have
 * the full width and never fall off the edge.
 */
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
  const manages = mayManage && invitation !== null && open;
  const state = [
    offerState(offer, quote),
    `aangeboden op ${formatDateTime(offer.offered_at)}`,
    manages && works && invitation.expires_at
      ? `link geldig t/m ${formatDate(invitation.expires_at)}`
      : null,
    manages ? mailLine(offer) : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <div role="listitem" data-offer={offer.channel}>
      <Stack gap="close">
        <Stack gap="tight">
          <nldd-text {...(offer.delivery === 'refused' ? { color: 'critical' } : {})}>
            {offerTitle(offer)}
          </nldd-text>
          <Quiet>{state}</Quiet>
        </Stack>
        {manages ? (
          <>
            {works ? (
              <Stack gap="tight">
                <nldd-text size="sm" data-signing-link>
                  {link}
                </nldd-text>
                {offer.recipient ? (
                  <Quiet>De link werkt alleen voor {offer.recipient}, na inloggen.</Quiet>
                ) : null}
              </Stack>
            ) : null}
            <nldd-container layout="wrap" gap="8" vertical-alignment="center">
              {works ? (
                <>
                  <CopyButton text="Kopieer tekenlink" value={link} size="sm" />
                  <CopyButton
                    text="Kopieer bericht"
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
              <MoreButton name={`de tekenlink${offer.recipient ? ` aan ${offer.recipient}` : ''}`}>
                <nldd-menu slot="popup" placement="bottom-start">
                  <MenuAction
                    text={works ? 'Verleng met 30 dagen' : 'Maak de tekenlink weer geldig'}
                    onSelect={() =>
                      onAction({
                        kind: 'renew-link',
                        invitationId: invitation.id,
                      })
                    }
                  />
                  {works && offer.mail ? (
                    <MenuAction
                      text="Stuur opnieuw"
                      onSelect={() =>
                        onAction({ kind: 'resend-mail', invitationId: invitation.id })
                      }
                    />
                  ) : null}
                  {works ? (
                    <MenuAction
                      text="Trek de tekenlink in"
                      onSelect={() =>
                        onAction({
                          kind: 'withdraw-link',
                          invitationId: invitation.id,
                        })
                      }
                    />
                  ) : null}
                </nldd-menu>
              </MoreButton>
            </nldd-container>
          </>
        ) : null}
      </Stack>
    </div>
  );
}

interface QuoteCardProps {
  quote: QuoteSummary;
  /** The quote with its offers, once loaded. */
  detail: QuoteDetail | undefined;
  /** Internal approval, where the organisation asks for it; undefined while loading. */
  approval?: ApprovalState | null;
  mayManage: boolean;
  /** The decisions on this quote that have a proof; undefined when not known. */
  evidence?: readonly QuoteEvidenceRow[];
  /** Who owns the assignment, to say who can see a signing link. */
  ownerName?: string | null;
  /** The reader is a beheerder, who can grant the right to approve. */
  isAdmin?: boolean;
  /**
   * The budget changed since this quote was made. Offering it would send
   * amounts that no longer hold: the next step is a new quote.
   */
  outdated?: boolean;
  busy: boolean;
  onAction: (action: CardAction) => void;
}

/**
 * One quote as one card: the amount, where it stands, and the one thing to
 * do next. Everything else is quiet.
 */
export function QuoteCard({
  quote,
  detail,
  approval,
  mayManage,
  isAdmin = false,
  outdated = false,
  evidence,
  ownerName,
  busy,
  onAction,
}: QuoteCardProps) {
  const offers = detail?.offers ?? [];
  const listed = listedOffers(offers);
  // Complete once the offers and the approval are in: until then no action,
  // so a button never changes under the pointer.
  const ready = detail !== undefined && approval !== undefined;
  const step = mayManage && ready ? primaryAction(quote, offers, approval) : null;
  const next = outdated && mayManage && ready && quote.status === 'issued' ? 'new-quote' : step;
  const open = quote.status === 'issued';
  const blocked = awaitsApproval(approval);
  // Approval is a matter between making and offering; once the quote is out
  // or decided it is history and stays in the details.
  const approvalText = open && offers.length === 0 ? approvalLine(approval) : null;
  // Nothing about approval shows for a quote that does not need it.
  const required = approval?.approval_required === true;
  const noApprover = blocked && approval?.approver_available === false;
  const mayReview = open && required && Boolean(approval?.may_decide_approval);
  const mayWithdrawApproval = open && required && Boolean(approval?.may_withdraw);
  const name = detail?.content?.name ?? '';

  // What else this quote can do. It sits next to the one button when there is
  // one, and otherwise with the quiet links at the top: never on a line alone.
  const acts = open && ready && (mayManage || mayWithdrawApproval);
  const withButton = open && ready && (next !== null || mayReview);
  const menu = acts ? (
    <MoreButton name="deze offerte" size={withButton ? 'md' : 'sm'}>
      <nldd-menu slot="popup" placement="bottom-start">
        {mayWithdrawApproval ? (
          <MenuAction
            text={
              approval?.status === 'approved' ? 'Trek de goedkeuring in' : 'Trek de aanvraag in'
            }
            onSelect={() => onAction({ kind: 'withdraw-approval' })}
          />
        ) : null}
        {mayManage && next !== 'offer' && !blocked ? (
          <MenuAction text="Bied opnieuw aan" onSelect={() => onAction({ kind: 'offer' })} />
        ) : null}
        {mayManage && next !== 'record-signed' && !blocked ? (
          <MenuAction text="Leg getekende pdf vast" onSelect={() => onAction({ kind: 'upload' })} />
        ) : null}
        {mayManage ? (
          <MenuAction text="Leg afwijzing vast" onSelect={() => onAction({ kind: 'reject' })} />
        ) : null}
      </nldd-menu>
    </MoreButton>
  ) : null;

  return (
    <nldd-card
      accessible-label={`Offerte ${quote.reference ?? ''}`.trim()}
      data-ready={ready ? 'true' : 'false'}
    >
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
                  : open && blocked
                    ? 'Wacht op goedkeuring'
                    : (QUOTE_STATUS_LABELS[quote.status] ?? quote.status)
              }
            />
          </nldd-title>
          <Quiet>{byline(quote)}</Quiet>
          {quote.snapshot_hash !== undefined ? (
            <nldd-container layout="row" gap="16" vertical-alignment="center">
              <DocumentLink href={quoteDocumentUrl(quote.id)} text="Bekijk pdf" newTab />
              {quote.acceptance?.has_document ? (
                <DocumentLink
                  href={signedDocumentUrl(quote.id)}
                  text="Getekend exemplaar"
                  download
                />
              ) : null}
              <QuoteDetails
                hash={quote.snapshot_hash}
                documentHref={quoteDocumentUrl(quote.id)}
                fileHash={quote.document_sha256 ?? detail?.document_sha256 ?? null}
                fileNote={quote.document_note ?? detail?.document_note ?? null}
                facts={[
                  { label: 'Kenmerk', value: quote.reference ?? '' },
                  {
                    label: 'Gemaakt',
                    value: `${formatDate(quote.issued_at)}${quote.issued_by_name ? ` door ${quote.issued_by_name}` : ''}`,
                  },
                  { label: 'Adres voor systemen', value: quote.uri },
                ]}
              />
              {withButton ? null : menu}
            </nldd-container>
          ) : null}
        </Stack>

        <Decision quote={quote} evidence={evidence} mayManage={mayManage} />

        {/* How it was offered matters while an answer is awaited; after the
            decision it is history, and the decision above says how it ended. */}
        {open && listed.length > 0 ? (
          <div role="list" aria-label="Hoe deze offerte is aangeboden">
            <Stack gap="related">
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
              {!mayManage && open && listed.some((offer) => offer.channel === 'signing_link') ? (
                <Quiet>
                  De tekenlink is zichtbaar voor de eigenaar{ownerName ? ` (${ownerName})` : ''} en
                  de managers van de opdracht.
                </Quiet>
              ) : null}
            </Stack>
          </div>
        ) : null}

        {approvalText && noApprover ? (
          <Stack gap="close">
            <nldd-banner
              variant="warning"
              size="sm"
              text={`Deze offerte heeft interne goedkeuring nodig${
                approval?.approval_reason ? ` (${approval.approval_reason})` : ''
              }, en er is nog niemand die dat kan geven`}
              supporting-text={
                isAdmin
                  ? `Geef een collega het recht "${APPROVER_RIGHT}": open de persoon onder Team, bij Rechten in grip.`
                  : 'Vraag de beheerder om iemand het recht te geven.'
              }
            />
            {isAdmin ? (
              <nldd-button-group>
                <Button
                  text="Ga naar Team"
                  size="sm"
                  onClick={() => onAction({ kind: 'grant-right' })}
                />
              </nldd-button-group>
            ) : null}
          </Stack>
        ) : null}
        {approvalText && !noApprover ? (
          <Stack gap="close">
            <nldd-text>{approvalText}</nldd-text>
            {approval?.status === 'requested' && approval.current?.request_note ? (
              <Quiet>Toelichting bij de aanvraag: {approval.current.request_note}</Quiet>
            ) : null}
          </Stack>
        ) : null}

        {withButton ? (
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            {next === 'offer' ? (
              <Button
                text="Bied aan"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: 'offer' })}
              />
            ) : null}
            {next === 'request-approval' ? (
              <Button
                text="Vraag goedkeuring"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: 'request-approval' })}
              />
            ) : null}
            {next === 'new-quote' ? (
              <Button
                text="Maak nieuwe offerte"
                appearance="primary"
                disabled={busy}
                onClick={() => onAction({ kind: 'new-quote' })}
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
            {mayReview ? (
              <Button
                text="Beoordeel"
                appearance={next === null ? 'primary' : 'secondary'}
                disabled={busy}
                onClick={() => onAction({ kind: 'review' })}
              />
            ) : null}
            {withButton ? menu : null}
          </nldd-container>
        ) : null}
        {mayManage &&
        open &&
        blocked &&
        approval?.blocked_message &&
        approval.approver_available &&
        next !== 'new-quote' ? (
          <Quiet>{approval.blocked_message}</Quiet>
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
        supporting-text={[
          QUOTE_STATUS_LABELS[quote.status] ?? quote.status,
          quote.total_cents !== undefined ? formatEuro(quote.total_cents) : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      />
      {quote.snapshot_hash !== undefined ? (
        <nldd-cell width="fit-content">
          <SharedDocumentLink
            href={quoteDocumentUrl(quote.id)}
            text="Bekijk pdf"
            kind="view"
            accessibleLabel={`Bekijk offerte ${quote.reference ?? formatDate(quote.issued_at)}`}
          />
        </nldd-cell>
      ) : null}
    </nldd-list-item>
  );
}
