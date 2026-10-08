/**
 * The words of closing and billing. One word per state, the same on the tab
 * of an assignment and on the page over all assignments.
 */
import { formatDateTime } from '@/features/quotes/format';
import { formatDate, formatEuro } from '@/lib/format';
import type {
  BillingDelivery,
  BillingOverview,
  BillingPeriod,
  DetailKey,
  NextStep,
  Rhythm,
} from './billingApi';

export const RHYTHM_TEXT: Record<Rhythm, string> = {
  month: 'per maand',
  quarter: 'per kwartaal',
};

export const DETAIL_LABELS: Record<DetailKey, string> = {
  organisation: 'Organisatie',
  attention_of: 'Ten name van',
  address: 'Adres of postbus',
  postcode_city: 'Postcode en plaats',
  reference: 'Kenmerk op de factuur',
  contact_name: 'Naam',
  contact_phone: 'Telefoon',
  contact_email: 'E-mail',
};

export const PERIOD_STATE_TEXT: Record<BillingPeriod['state'], string> = {
  running: 'Loopt',
  to_close: 'Af te sluiten',
  ready: 'Klaar om aan te leveren',
  delivered: 'Aangeleverd',
  invoiced: 'Gefactureerd',
};

/** The colour of a state, for the one row that asks for an act; every other row is neutral. */
export const PERIOD_STATE_COLOR: Record<
  BillingPeriod['state'],
  'neutral' | 'warning' | 'accent' | 'success'
> = {
  running: 'neutral',
  to_close: 'warning',
  ready: 'accent',
  delivered: 'neutral',
  invoiced: 'neutral',
};

/** "Het derde kwartaal 2026" or "Juli 2026", to start a sentence with. */
export function periodName(label: string, sentenceStart = false): string {
  const withArticle = label.includes('kwartaal') ? `het ${label}` : label;
  return sentenceStart ? withArticle.charAt(0).toUpperCase() + withArticle.slice(1) : withArticle;
}

/** What the one primary button does. */
export function stepAction(step: NextStep): string {
  if (step.kind === 'close_month') return `Sluit ${step.month_label ?? ''} af`;
  if (step.kind === 'deliver') return 'Lever aan';
  if (step.kind === 'record_invoice') return 'Leg de factuur vast';
  return '';
}

function amountOf(step: NextStep): string | null {
  return step.amount_cents === null || step.amount_cents === undefined
    ? null
    : formatEuro(step.amount_cents);
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** What the page asks now: the thing it concerns and its amount, in words. */
export function stepTitle(step: NextStep): string {
  const amount = amountOf(step);
  if (step.kind === 'close_month') return `${capital(step.month_label ?? '')} is voorbij`;
  if (step.kind === 'deliver') {
    const name = periodName(step.period_label ?? '', true);
    return amount ? `${name} is klaar: ${amount}` : `${name} is klaar`;
  }
  if (step.kind === 'record_invoice') {
    const name = periodName(step.period_label ?? '');
    return amount ? `${amount} aangeleverd over ${name}` : `Aangeleverd over ${name}`;
  }
  return 'Er staat niets open';
}

/** The line under it: what to do about it, or when the next thing comes. */
export function stepLine(step: NextStep, overview: BillingOverview): string {
  const amount = amountOf(step);
  if (step.kind === 'close_month') {
    return amount
      ? `Gepland was ${amount}. Stel vast wat er is gewerkt en sluit de maand af.`
      : 'Stel vast wat er is gewerkt en sluit de maand af.';
  }
  if (step.kind === 'deliver') {
    return overview.can_mail
      ? 'Alle maanden zijn afgesloten. Lever aan bij de financiële administratie.'
      : 'Alle maanden zijn afgesloten. Maak het factuurverzoek voor de financiële administratie.';
  }
  if (step.kind === 'record_invoice') {
    return 'Is de factuur de deur uit? Leg dan het nummer en de datum vast.';
  }
  if (step.from_date && step.month_label) {
    return `Vanaf ${formatDate(step.from_date)} sluit je ${step.month_label} af.`;
  }
  return 'Alle maanden zijn afgesloten en gefactureerd.';
}

/** The last thing that happened to a period, as one quiet line. */
export function periodLine(period: BillingPeriod): string {
  const delivery = (period.deliveries ?? []).at(-1);
  if (period.state === 'invoiced') {
    const numbers = (period.invoice_numbers ?? []).join(', ');
    return numbers ? `Factuur ${numbers}` : 'Gefactureerd';
  }
  if (period.state === 'delivered') {
    return delivery
      ? deliveryLine(delivery)
      : `Aangeleverd op ${formatDateTime(period.last_step_at)}`;
  }
  const closed = period.months.filter((month) => month.state === 'closed').length;
  const total = period.months.length;
  if (period.state === 'ready') {
    const correction = period.months.some((month) => (month.correction_cents ?? 0) !== 0);
    if (delivery && correction) return 'Gewijzigd na de aanlevering: naverrekening';
    return total > 1 ? `Alle ${total} maanden afgesloten` : 'Afgesloten';
  }
  if (total === 1) return '';
  return `${closed} van ${total} maanden afgesloten`;
}

export function deliveryLine(delivery: BillingDelivery): string {
  const when = formatDate(delivery.delivered_at);
  if (delivery.via === 'mail' && delivery.recipient) {
    if (delivery.mail_state === 'failed') {
      return `Aangeleverd op ${when}; de mail aan ${delivery.recipient} is niet afgeleverd`;
    }
    return `Aangeleverd op ${when} aan ${delivery.recipient}`;
  }
  return `Aangeleverd op ${when}${delivery.delivered_by_name ? ` door ${delivery.delivered_by_name}` : ''}`;
}

/** The amount a period row shows: what counts in its state. */
export function periodAmount(period: BillingPeriod): number | null | undefined {
  if (period.state === 'invoiced') return period.invoiced_cents;
  if (period.state === 'delivered') return period.delivered_cents;
  if (period.state === 'ready') return period.to_deliver_cents;
  return period.closed_cents || undefined;
}
