/**
 * The factuurinformatie: where the contractor sends the invoice. Asked when
 * a quote is accepted, changed later by the client, and asked again at
 * delivery only when something is missing.
 */
import type { BillingDetails, DetailKey } from './billingApi';
import { DETAIL_LABELS } from './periodText';

export const ADDRESS_KEYS: DetailKey[] = [
  'organisation',
  'attention_of',
  'address',
  'postcode_city',
  'reference',
];
export const CONTACT_KEYS: DetailKey[] = ['contact_name', 'contact_phone', 'contact_email'];
export const REQUIRED_DETAILS: DetailKey[] = ['organisation', 'address', 'postcode_city'];

export function missing(details: BillingDetails): DetailKey | null {
  return REQUIRED_DETAILS.find((key) => !(details[key] ?? '').trim()) ?? null;
}

/** What to say when the address is not complete, or null when it is. */
export function missingText(details: BillingDetails): string | null {
  const gap = missing(details);
  return gap ? `Vul in: ${DETAIL_LABELS[gap].toLowerCase()}.` : null;
}

/** The details to start from: the client's own reference goes on the invoice unless one is given. */
export function startDetails(
  details: BillingDetails | null | undefined,
  clientReference: string | null | undefined,
): BillingDetails {
  const start = { ...(details ?? {}) };
  if (!(start.reference ?? '').trim() && clientReference) start.reference = clientReference;
  return start;
}

/** The trimmed fields that were filled in, or null when nothing was. */
export function filledDetails(details: BillingDetails): BillingDetails | null {
  const filled: BillingDetails = {};
  for (const [key, value] of Object.entries(details) as [DetailKey, string | undefined][]) {
    const trimmed = (value ?? '').trim();
    if (trimmed) filled[key] = trimmed;
  }
  return Object.keys(filled).length > 0 ? filled : null;
}
