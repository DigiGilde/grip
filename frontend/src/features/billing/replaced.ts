import type {
  ReplacedMonth,
  ReplacesMonth,
  StatedCorrection,
} from '@/features/month-close/billingApi';
import { formatDate, formatEuro } from '@/lib/format';

const capital = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}`;

/** What a request replaces, in the words of its document. */
export function replacesText(item: ReplacesMonth): string {
  return `Dit verzoek vervangt ${item.month_label} uit factuurverzoek ${item.reference} (${formatEuro(item.amount_cents)}). Het verschil is ${formatEuro(item.difference_cents)}.`;
}

/** What of a request no longer counts, and what does. */
export function replacedText(replaced: ReplacedMonth[], inForceCents: number): string {
  const months = replaced.map((item) => item.month_label).join(' en ');
  const references = [...new Set(replaced.map((item) => item.reference))].join(' en ');
  const rest =
    inForceCents === 0
      ? 'Factureer dit verzoek niet meer.'
      : `Van dit verzoek telt nog ${formatEuro(inForceCents)}.`;
  return `${capital(months)} is opnieuw aangeleverd in factuurverzoek ${references}. ${rest}`;
}

/** A difference, in the words of its document: the amount, why, and on top of what. */
export function correctionText(item: StatedCorrection): string {
  const cause = item.cause.trim();
  const why = cause ? ` ${capital(cause)}.` : '';
  const verb = item.amount_cents < 0 ? 'gaat af van' : 'komt bovenop';
  const what = item.follows_reference
    ? `factuurverzoek ${item.follows_reference}${item.follows_delivered_on ? ` van ${formatDate(item.follows_delivered_on)}` : ''}`
    : 'wat eerder over deze maand is aangeleverd';
  return `Naverrekening ${item.month_label}: ${formatEuro(item.amount_cents)}.${why} Dit bedrag ${verb} ${what}.`;
}
