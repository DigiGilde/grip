/**
 * The state of a month in words. Three facts, each with its own word:
 * aangeleverd (billing data went to the financial administration),
 * gefactureerd (someone recorded that an invoice was sent), and neither.
 */
import { formatDateTime } from '@/features/quotes/format';
import { formatDate, formatEuro } from '@/lib/format';
import type { MonthBilling, OutgoingInvoice } from './api';

export function billingStateText(month: MonthBilling): string {
  if (month.state === 'invoiced') {
    return `Gefactureerd met nummer ${month.invoice_number ?? ''} op ${formatDate(month.invoice_date)}`;
  }
  if (month.state === 'delivered') {
    return `Aangeleverd op ${formatDateTime(month.delivered_at)}`;
  }
  return 'Niet aangeleverd';
}

/** What needs attention about a month, or nothing. */
export function billingStateRemark(month: MonthBilling): string | null {
  if (month.state === 'invoiced' && !month.closed) {
    return 'De maand is na de factuur heropend en nog niet opnieuw afgesloten';
  }
  if (month.invoice_on_earlier_delivery) {
    return 'De factuur hoort bij een eerdere aanlevering; de maand is daarna opnieuw aangeleverd';
  }
  if (month.state === 'delivered' && month.to_deliver_cents) {
    return 'De vastgestelde inzet is sinds de aanlevering gewijzigd';
  }
  return null;
}

/** The difference between an invoice and what was delivered for it, in words. */
export function differenceText(invoice: OutgoingInvoice): string {
  if (invoice.difference_cents === 0) return 'Gelijk aan het aangeleverde bedrag';
  const amount = formatEuro(Math.abs(invoice.difference_cents));
  return invoice.difference_cents > 0
    ? `${amount} meer dan aangeleverd`
    : `${amount} minder dan aangeleverd`;
}
