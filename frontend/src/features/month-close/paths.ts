/**
 * Addresses of the steps on the monthly close tab, so a task or a link can
 * land someone on exactly the step to take.
 */
export const MONTH_PARAM = 'maand';
export const INVOICE_PARAM = 'factuur';
export const PERIOD_PARAM = 'periode';

function tab(assignmentId: string): string {
  return `/opdrachten/${assignmentId}/maandafsluiting`;
}

/** The tab with one month open: the place to close it, or to see how it was closed. */
export function monthClosePath(assignmentId: string, month: string): string {
  return `${tab(assignmentId)}?${MONTH_PARAM}=${month}`;
}

/** The tab with the sheet open to record an invoice for these delivered months. */
export function recordInvoicePath(assignmentId: string, months: readonly string[]): string {
  return `${tab(assignmentId)}?${INVOICE_PARAM}=${months.join(',')}`;
}

/** The tab with the sheet open to deliver a billing period ("2026-Q3" or "2026-07"). */
export function deliverPeriodPath(assignmentId: string, periodKey: string): string {
  return `${tab(assignmentId)}?${PERIOD_PARAM}=${periodKey}`;
}

/** The months named in an address, in the form YYYY-MM; anything else is dropped. */
export function monthsFromParam(value: string | null): string[] {
  return (value ?? '').split(',').filter((part) => /^\d{4}-\d{2}$/.test(part));
}
