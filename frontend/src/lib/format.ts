/**
 * Shared formatters. Amounts travel as integer cents and percentages and
 * FTE as decimal strings; nothing here does arithmetic beyond presentation.
 */

const euro = new Intl.NumberFormat('nl-NL', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const euroWithCents = new Intl.NumberFormat('nl-NL', {
  style: 'currency',
  currency: 'EUR',
});

const dateFormat = new Intl.DateTimeFormat('nl-NL', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});

const monthFormat = new Intl.DateTimeFormat('nl-NL', {
  month: 'long',
  year: 'numeric',
});

/** Whole euros, the default in overviews. */
export function formatEuro(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '';
  return euro.format(cents / 100);
}

/** Euros with cents, for a single amount where the cents matter. */
export function formatEuroExact(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '';
  return euroWithCents.format(cents / 100);
}

/** A percentage given as a number or decimal string, e.g. "80" or "62.5". */
export function formatPercent(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  const number = typeof value === 'string' ? Number(value) : value;
  if (Number.isNaN(number)) return '';
  return `${number.toLocaleString('nl-NL', { maximumFractionDigits: 2 })}%`;
}

/** An FTE fraction given as a number or decimal string, e.g. "0.8". */
export function formatFte(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  const number = typeof value === 'string' ? Number(value) : value;
  if (Number.isNaN(number)) return '';
  return number.toLocaleString('nl-NL', { maximumFractionDigits: 2 });
}

/** An ISO date (yyyy-mm-dd). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? '' : dateFormat.format(date);
}

/** An ISO month (yyyy-mm) or date. */
export function formatMonth(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(`${iso.slice(0, 7)}-01T00:00:00`);
  return Number.isNaN(date.getTime()) ? '' : monthFormat.format(date);
}

/** A period with an open end. */
export function formatPeriod(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  const from = formatDate(start);
  const to = formatDate(end);
  if (from && to) return `${from} t/m ${to}`;
  if (from) return `vanaf ${from}`;
  if (to) return `t/m ${to}`;
  return '';
}
