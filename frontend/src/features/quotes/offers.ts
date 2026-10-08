/**
 * Where a quote stands, in words and in steps. Pure functions, so the card
 * shows a structure instead of sentences that explain it.
 */
import { formatDate } from '@/lib/format';
import type { QuoteDetail, QuoteOffer, QuoteSummary } from './api';
import { OFFER_CHANNEL_LABELS } from './api';
import { awaitsApproval, type ApprovalState } from './approval';
import { formatDateTime } from './format';

export interface QuoteStep {
  text: string;
  status: 'past' | 'current' | 'future';
}

/**
 * The steps of one quote: gemaakt, aangeboden, getekend of afgewezen. Where
 * the organisation approves a quote internally first, that is a step between
 * making and offering; elsewhere it does not show.
 */
export function quoteSteps(
  quote: QuoteSummary,
  offers: readonly QuoteOffer[],
  approval?: ApprovalState | null,
): QuoteStep[] {
  const decided = quote.status === 'accepted' || quote.status === 'rejected';
  const offered = offers.length > 0 || decided;
  const needsApproval = Boolean(approval?.approval_required);
  const approved = offered || !awaitsApproval(approval);
  const steps: QuoteStep[] = [{ text: 'Gemaakt', status: 'past' }];
  if (needsApproval) {
    steps.push({ text: 'Interne goedkeuring', status: approved ? 'past' : 'current' });
  }
  steps.push({
    text: 'Aangeboden',
    status: offered ? 'past' : approved ? 'current' : 'future',
  });
  steps.push({
    text:
      quote.status === 'accepted'
        ? 'Getekend'
        : quote.status === 'rejected'
          ? 'Afgewezen'
          : 'Getekend of afgewezen',
    status: decided ? 'past' : offered ? 'current' : 'future',
  });
  return steps;
}

/** Offers newest first, with one entry per signing link: the latest offer on it. */
export function listedOffers(offers: readonly QuoteOffer[]): QuoteOffer[] {
  const newestFirst = [...offers].sort((a, b) => b.offered_at.localeCompare(a.offered_at));
  const seen = new Set<string>();
  return newestFirst.filter((offer) => {
    const key = offer.invitation?.id;
    if (!key) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
  const latest = listedOffers(offers)[0];
  return latest?.channel === 'document' ? 'record-signed' : null;
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
