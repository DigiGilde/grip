/**
 * Addresses of the steps on the monthly close tab, so a task or a link can
 * land someone on exactly the step to take.
 */
export const MONTH_PARAM = 'maand';
export const INVOICE_PARAM = 'factuur';

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

/** The months named in an address, in the form YYYY-MM; anything else is dropped. */
export function monthsFromParam(value: string | null): string[] {
  return (value ?? '').split(',').filter((part) => /^\d{4}-\d{2}$/.test(part));
}
