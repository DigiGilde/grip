/**
 * Reading an amount a person typed. The API takes integer cents; this turns
 * "1.250,50" or "1250.5" into 125050 by handling the digits as text, so no
 * floating point comes near an amount.
 */
export function parseEuroToCents(input: string): number | null {
  const text = input.replace(/[€\s]/g, '');
  // Dutch notation (1.250,50), English notation (1,250.50) or bare digits
  // with an optional fraction after either mark. The mark that groups
  // thousands is never the one before the fraction.
  const match =
    /^(\d{1,3}(?:\.\d{3})+)(?:,(\d{1,2}))?$/.exec(text) ??
    /^(\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?$/.exec(text) ??
    /^(\d+)(?:[.,](\d{1,2}))?$/.exec(text);
  if (!match) return null;
  const whole = (match[1] ?? '').replace(/[.,]/g, '');
  const fraction = (match[2] ?? '').padEnd(2, '0');
  const cents = Number(`${whole}${fraction}`);
  return Number.isSafeInteger(cents) ? cents : null;
}

/** Cents as the text of an input, e.g. 125050 becomes "1250,50". */
export function centsToInput(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '';
  const digits = String(Math.abs(cents)).padStart(3, '0');
  const whole = digits.slice(0, -2);
  const fraction = digits.slice(-2);
  return fraction === '00' ? whole : `${whole},${fraction}`;
}

/** A decimal a person typed with a comma, as the API wants it. */
export function parseDecimal(input: string): string | null {
  const text = input.trim().replace(',', '.');
  return /^\d+(\.\d+)?$/.test(text) ? text : null;
}

/** A decimal string from the API as the text of an input. */
export function decimalToInput(value: string | null | undefined): string {
  if (!value) return '';
  const trimmed = value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
  return trimmed.replace('.', ',');
}
