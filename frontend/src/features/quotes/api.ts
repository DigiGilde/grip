/**
 * The quote endpoints. Fields of a data class the person may not see are
 * absent from a response, not null, so most fields are optional here.
 */
import { ApiError, apiGet, apiPost, getCsrfToken, type ProblemDetails } from '@/api/client';

export interface YearRate {
  year: number;
  monthly_rate_cents: number;
}

export interface RatePeriod {
  start_date: string;
  end_date: string;
  monthly_rate_cents: number;
}

export interface QuoteLine {
  position: number;
  description: string;
  kind: 'personnel' | 'fixed' | string;
  role?: string | null;
  fte?: string | null;
  rate_category?: string | null;
  /** The scales that bill in this category, as on the rate leaflet. */
  scales?: number[];
  start_date?: string | null;
  end_date?: string | null;
  year?: number | null;
  monthly_rates?: YearRate[];
  /** Instead of monthly_rates, when the rate changes on another date than 1 January. */
  rate_periods?: RatePeriod[];
  amount_cents: number;
}

export interface QuoteContent {
  name: string;
  context_refs?: string[];
  lines: QuoteLine[];
  subtotals_per_year: { year: number; amount_cents: number }[];
  total_cents: number;
  valid_until?: string | null;
  conditions?: string | null;
  /** The organisation that sends the quote. */
  sender?: string | null;
  /** The client's own reference ("uw kenmerk"). */
  client_reference?: string | null;
}

export interface QuotePreview {
  assignment_id: string;
  assignment_name: string;
  assignment_status: string;
  can_issue: boolean;
  may_issue: boolean;
  problem: string | null;
  content?: QuoteContent;
  quoted_amount_cents?: number | null;
  difference_cents?: number | null;
  /** Conditions the organisation proposes for a new quote. */
  default_conditions?: string | null;
}

export interface Acceptance {
  form: 'own_instance' | 'signing_link' | 'uploaded_pdf' | string;
  signed_at: string;
  signer_name?: string;
  signer_function?: string | null;
  organisation_name?: string | null;
  has_document?: boolean;
}

export interface Rejection {
  rejected_at: string;
  reason?: string | null;
}

export interface QuoteSummary {
  id: string;
  uri: string;
  /** The reference people quote, e.g. "DG-2026-0007". */
  reference?: string | null;
  assignment_id: string;
  status: 'issued' | 'accepted' | 'rejected' | 'superseded' | string;
  issued_at: string;
  issued_by_name: string | null;
  total_cents?: number;
  snapshot_hash?: string;
  valid_until?: string | null;
  acceptance?: Acceptance | null;
  rejection?: Rejection | null;
}

export type OfferChannel = 'client_instance' | 'signing_link' | 'document';

/** The signing link behind an offer; only for whoever manages the assignment. */
export interface OfferInvitation {
  id: string;
  /** Path of the page the invited person opens. */
  signing_path: string;
  expires_at: string | null;
  opened_at: string | null;
  used_at: string | null;
  withdrawn_at: string | null;
  state: 'invited' | 'opened' | 'signed' | 'expired' | 'withdrawn' | string;
}

/** One time the quote was put before the client, through one channel. */
export interface QuoteOffer {
  id: string;
  channel: OfferChannel | string;
  /** The client's instance, the invited email address, or nothing. */
  recipient?: string | null;
  offered_at: string;
  offered_by_name?: string | null;
  /** For the client's own instance: pending, sent or refused. */
  delivery?: 'pending' | 'sent' | 'refused' | string | null;
  invitation?: OfferInvitation | null;
}

/** A channel the quote can be offered through, or why it cannot. */
export interface QuoteChannel {
  channel: OfferChannel | string;
  available: boolean;
  reason?: string | null;
  suggested?: boolean;
}

export interface QuoteDetail extends QuoteSummary {
  /** The frozen content of the quote. */
  content?: QuoteContent;
  offers?: QuoteOffer[];
  channels?: QuoteChannel[];
}

export interface QuoteList {
  may_manage: boolean;
  quotes: QuoteSummary[];
}

export interface Invitation {
  id: string;
  email: string;
  created_at: string;
  expires_at: string | null;
  used_at: string | null;
}

export const quoteKeys = {
  preview: (assignmentId: string) => ['quotes', 'preview', assignmentId] as const,
  list: (assignmentId: string) => ['quotes', 'list', assignmentId] as const,
  invitations: (quoteId: string) => ['quotes', 'invitations', quoteId] as const,
  detail: (quoteId: string) => ['quotes', 'detail', quoteId] as const,
};

export function fetchQuotePreview(assignmentId: string): Promise<QuotePreview> {
  return apiGet(`/api/assignments/${assignmentId}/quote-preview`);
}

export function fetchQuotes(assignmentId: string): Promise<QuoteList> {
  return apiGet(`/api/assignments/${assignmentId}/quotes`);
}

export function issueQuote(
  assignmentId: string,
  input: {
    valid_until: string | null;
    conditions: string | null;
    client_reference?: string | null;
  },
): Promise<QuoteSummary> {
  return apiPost(`/api/assignments/${assignmentId}/quotes`, input);
}

export function fetchQuoteDetail(quoteId: string): Promise<QuoteDetail> {
  return apiGet(`/api/quotes/${quoteId}`);
}

/**
 * Offers an issued quote to the client through one channel. Issuing a quote
 * sends nothing; this does.
 */
export function offerQuote(
  quoteId: string,
  input: { channel: OfferChannel; email?: string },
): Promise<QuoteDetail> {
  return apiPost(`/api/quotes/${quoteId}/offers`, input);
}

/** Takes a signing link back: from then on it opens nothing. */
export function withdrawInvitation(quoteId: string, invitationId: string): Promise<QuoteDetail> {
  return apiPost(`/api/quotes/${quoteId}/invitations/${invitationId}/withdraw`);
}

/** Makes a signing link work again for the standard period. */
export function renewInvitation(quoteId: string, invitationId: string): Promise<QuoteDetail> {
  return apiPost(`/api/quotes/${quoteId}/invitations/${invitationId}/renew`);
}

export function fetchInvitations(quoteId: string): Promise<{ invitations: Invitation[] }> {
  return apiGet(`/api/quotes/${quoteId}/invitations`);
}

export function inviteSigner(quoteId: string, email: string): Promise<Invitation> {
  return apiPost(`/api/quotes/${quoteId}/invitations`, { email });
}

export function recordRejection(quoteId: string, reason: string | null): Promise<QuoteSummary> {
  return apiPost(`/api/quotes/${quoteId}/rejection`, { reason });
}

export interface UploadedAcceptanceInput {
  file: File;
  signer_name: string;
  signer_email: string;
  signer_function: string;
  organisation_name: string;
  signed_at: string;
}

/** Sends the signed pdf with the details of who signed, as a multipart form. */
export async function recordUploadedAcceptance(
  quoteId: string,
  input: UploadedAcceptanceInput,
): Promise<QuoteSummary> {
  const form = new FormData();
  form.append('file', input.file);
  form.append('signer_name', input.signer_name);
  form.append('signer_email', input.signer_email);
  if (input.signer_function) form.append('signer_function', input.signer_function);
  if (input.organisation_name) form.append('organisation_name', input.organisation_name);
  // The date field gives a day; the moment of signing is recorded at noon UTC
  // so the day does not shift with the time zone.
  if (input.signed_at) form.append('signed_at', `${input.signed_at}T12:00:00Z`);

  const response = await fetch(`/api/quotes/${quoteId}/acceptance/uploaded-pdf`, {
    method: 'POST',
    headers: {
      Accept: 'application/json, application/problem+json',
      'X-CSRF-Token': getCsrfToken(),
    },
    credentials: 'same-origin',
    body: form,
  });
  if (response.ok) return (await response.json()) as QuoteSummary;
  const body: unknown = await response.json().catch(() => null);
  const problem = typeof body === 'object' && body !== null ? (body as ProblemDetails) : null;
  throw new ApiError(response.status, response.statusText, body, problem);
}

export function quoteDocumentUrl(quoteId: string, download = false): string {
  return `/api/quotes/${quoteId}/document${download ? '?download=true' : ''}`;
}

export function signedDocumentUrl(quoteId: string): string {
  return `/api/quotes/${quoteId}/acceptance/document`;
}

/** The full address an invited signer opens, from the path the API gives. */
export function signingLink(path: string): string {
  return `${window.location.origin}${path}`;
}

export const QUOTE_STATUS_LABELS: Record<string, string> = {
  issued: 'Offerte gemaakt',
  accepted: 'Akkoord',
  rejected: 'Afgewezen',
  superseded: 'Vervangen',
};

export const QUOTE_STATUS_COLORS: Record<
  string,
  'neutral' | 'success' | 'warning' | 'critical' | 'accent'
> = {
  issued: 'accent',
  accepted: 'success',
  rejected: 'critical',
  superseded: 'neutral',
};

export const ACCEPTANCE_FORM_LABELS: Record<string, string> = {
  own_instance: 'Getekend in het grip van de opdrachtgever',
  signing_link: 'Getekend via de tekenlink',
  uploaded_pdf: 'Getekende pdf vastgelegd',
};

export const OFFER_CHANNEL_LABELS: Record<string, string> = {
  client_instance: 'Via het grip van de opdrachtgever',
  signing_link: 'Met een tekenlink',
  document: 'Als document',
};

/** One line per channel on what happens when the quote is offered through it. */
export const OFFER_CHANNEL_EFFECTS: Record<string, string> = {
  client_instance:
    'De offerte komt binnen in het grip van de opdrachtgever en wordt daar getekend.',
  signing_link:
    'Je krijgt een link voor één persoon. Die logt in met SSO Rijk en tekent hier. Je stuurt de link zelf door.',
  document: 'Je downloadt de pdf en verstuurt die zelf. Het getekende exemplaar leg je hier vast.',
};

export const OFFER_DELIVERY_LABELS: Record<string, string> = {
  pending: 'Staat klaar om te versturen',
  sent: 'Afgeleverd bij de opdrachtgever',
  refused: 'Niet afgeleverd',
};
