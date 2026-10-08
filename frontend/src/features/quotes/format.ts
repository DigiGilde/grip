/** Presentation helpers of the quote, signing and monthly close screens. */

/** First characters of a hash, enough to compare two by eye. */
export function shortHash(hash: string | undefined): string {
  return hash ? `${hash.slice(0, 12)}…` : '';
}

/** A date and time from an ISO timestamp, in Dutch. */
const dateTime = new Intl.DateTimeFormat('nl-NL', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : dateTime.format(date);
}
