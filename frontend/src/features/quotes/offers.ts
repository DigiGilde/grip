/**
 * Where a quote stands, in words and in steps. Pure functions, so the card
 * shows a structure instead of sentences that explain it.
 */
import { formatDate } from '@/lib/format';
import type { QuoteDetail, QuoteOffer, QuoteSummary } from './api';
import { OFFER_CHANNEL_LABELS } from './api';
import { quotePosition } from '@/features/assignments/standing';
import { awaitsApproval, type ApprovalState } from './approval';
import { formatDateTime } from './format';

export interface QuoteStep {
  text: string;
  status: 'past' | 'current' | 'future';
}

/** The quote as the shared standing function reads it. */
function quoteFact(quote: QuoteSummary, approval?: ApprovalState | null) {
  return {
    status: quote.status,
    // Only a quote that needs approval has an approval to wait for.
    approval: approval?.approval_required ? approval.status : null,
  };
}

/**
 * The steps of one quote: gemaakt, aangeboden, getekend of afgewezen. Where
 * the organisation approves a quote internally first, that is a step between
 * making and offering; elsewhere it does not show.
 *
 * Which step is the current one comes from `quotePosition`, the same
 * function the steps of the assignment read.
 */
export function quoteSteps(
  quote: QuoteSummary,
  offers: readonly QuoteOffer[],
  approval?: ApprovalState | null,
): QuoteStep[] {
  const position = quotePosition(quoteFact(quote, approval), offers);
  const needsApproval = Boolean(approval?.approval_required);
  const texts = [
    'Gemaakt',
    ...(needsApproval ? ['Interne goedkeuring'] : []),
    'Aangeboden',
    quote.status === 'accepted'
      ? 'Getekend'
      : quote.status === 'rejected'
        ? 'Afgewezen'
        : 'Getekend of afgewezen',
  ];
  const last = texts.length - 1;
  // A quote that was sent back stays at the approval it did not get; one
  // that was rejected or replaced has run its course.
  const current =
    position === 'approval' || (position === 'quote' && quote.status === 'issued')
      ? 1
      : position === 'offer'
        ? last - 1
        : position === 'agreement'
          ? last
          : position === 'quote' && quote.status === 'superseded' && offers.length === 0
            ? last - 1
            : last + 1;
  return texts.map((text, index) => ({
    text,
    status: index < current ? 'past' : index === current ? 'current' : 'future',
  }));
}

/** Whether the client can still answer through this offer. */
export function awaitsResponse(offer: QuoteOffer): boolean {
  if (offer.channel === 'signing_link') {
    const state = offer.invitation?.state;
    return state === undefined || state === 'invited' || state === 'opened';
  }
  if (offer.channel === 'client_instance') return offer.delivery !== 'refused';
  return true;
}

/**
 * One entry per signing link (the latest offer on it), the offers that still
 * wait for an answer first, and within that the newest first.
 */
export function listedOffers(offers: readonly QuoteOffer[]): QuoteOffer[] {
  const newestFirst = [...offers].sort((a, b) => b.offered_at.localeCompare(a.offered_at));
  const seen = new Set<string>();
  const unique = newestFirst.filter((offer) => {
    const key = offer.invitation?.id;
    if (!key) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return [...unique.filter(awaitsResponse), ...unique.filter((offer) => !awaitsResponse(offer))];
}

/** "Met een tekenlink aan naam@organisatie.example": the channel, and to whom. */
export function offerTitle(offer: QuoteOffer): string {
  const channel = OFFER_CHANNEL_LABELS[offer.channel] ?? offer.channel;
  if (offer.channel === 'signing_link' && offer.recipient) {
    return `${channel} aan ${offer.recipient}`;
  }
  return channel;
}

/** Where the offer stands, in words. */
export function offerState(offer: QuoteOffer, quote: QuoteSummary): string {
  if (offer.channel === 'client_instance') {
    if (offer.delivery === 'refused') return 'Niet afgeleverd bij de opdrachtgever';
    if (offer.delivery === 'pending') return 'Onderweg naar de opdrachtgever';
    return 'Afgeleverd bij de opdrachtgever';
  }
  if (offer.channel === 'document') {
    return quote.acceptance?.form === 'uploaded_pdf'
      ? 'Getekend exemplaar vastgelegd'
      : 'Meegegeven, wacht op het getekende exemplaar';
  }
  const invitation = offer.invitation;
  if (!invitation) return 'Uitgenodigd om te tekenen';
  switch (invitation.state) {
    case 'signed': {
      const who = quote.acceptance?.signer_name;
      return `Getekend op ${formatDateTime(invitation.used_at)}${who ? ` door ${who}` : ''}`;
    }
    case 'withdrawn':
      return `Tekenlink ingetrokken op ${formatDateTime(invitation.withdrawn_at)}`;
    case 'expired':
      return `Tekenlink verlopen op ${formatDate(invitation.expires_at)}`;
    case 'opened':
      return `Geopend op ${formatDateTime(invitation.opened_at)}`;
    default:
      return 'Uitgenodigd, nog niet geopend';
  }
}

/** Whether the signing link of this offer still opens the quote. */
export function linkWorks(offer: QuoteOffer): boolean {
  const state = offer.invitation?.state;
  return state === 'invited' || state === 'opened';
}

export type PrimaryAction = 'offer' | 'record-signed' | 'request-approval' | 'new-quote' | null;

/**
 * The one thing to do now on an open quote, for whoever manages it. After
 * making: offer it, or first ask for the internal approval the organisation
 * wants. Sent back: make a new quote. When it went out as a document: record
 * the signed copy. While an approver or the client has it: nothing; the
 * decision comes in by itself.
 */
export function primaryAction(
  quote: QuoteDetail | QuoteSummary,
  offers: readonly QuoteOffer[],
  approval?: ApprovalState | null,
): PrimaryAction {
  if (quote.status !== 'issued') return null;
  if (offers.length === 0) {
    if (!awaitsApproval(approval)) return 'offer';
    if (approval?.status === 'sent_back') return 'new-quote';
    if (approval?.status === 'requested') return null;
    return approval?.may_request_approval && approval.approver_available
      ? 'request-approval'
      : null;
  }
  // Recording the signed copy is the step only when a document is all the
  // client has: with a signing link or the client's own grip also open, the
  // answer may come in by itself, and recording stays in the menu.
  const awaited = listedOffers(offers).filter(awaitsResponse);
  return awaited.length > 0 && awaited.every((offer) => offer.channel === 'document')
    ? 'record-signed'
    : null;
}

/** The text someone pastes into a mail to the person invited to sign. */
export function invitationMessage(input: {
  reference: string | null | undefined;
  name: string;
  link: string;
  email: string | null | undefined;
  expiresAt: string | null | undefined;
}): string {
  const subject = input.reference ? `offerte ${input.reference}` : 'de offerte';
  const lines = [
    `Hierbij ${subject} voor ${input.name}.`,
    `Je kunt de offerte bekijken en tekenen via ${input.link}`,
    input.email
      ? `Log in met SSO Rijk, met het e-mailadres ${input.email}.`
      : 'Log in met SSO Rijk, met het e-mailadres waarop je bent uitgenodigd.',
  ];
  if (input.expiresAt) lines.push(`De link werkt tot en met ${formatDate(input.expiresAt)}.`);
  return lines.join('\n');
}

/** A reason from the server in words for someone who offers a quote. */
export function channelReason(reason: string | null | undefined): string {
  return reason?.trim() || 'Dit kan nu niet.';
}

/** What happened to the mail with the signing link, in words; null without one. */
export function mailLine(offer: QuoteOffer): string | null {
  const mail = offer.mail;
  if (!mail) return null;
  if (mail.state === 'sent') return `Gemaild op ${formatDate(mail.sent_at ?? mail.queued_at)}`;
  if (mail.state === 'failed') {
    return `Mail niet afgeleverd${mail.failed_reason ? `: ${mail.failed_reason}` : ''}`;
  }
  return 'Wordt gemaild';
}
