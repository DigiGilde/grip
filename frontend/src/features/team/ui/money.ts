/**
 * Amounts travel as integer cents. These two functions turn what someone
 * types into cents and back by moving the decimal separator in the text, so
 * no amount ever passes through a floating-point number.
 */

/** "18.000", "18000,5" or "18000.50" as cents; null when it is not an amount. */
export function eurosToCents(input: string): number | null {
  let text = input.trim().replace(/^€\s*/, '').replace(/\s/g, '');
  if (text === '') return null;
  const negative = text.startsWith('-');
  if (negative) text = text.slice(1);

  let whole = text;
  let fraction = '';
  // The last comma or point is the decimal separator when at most two
  // digits follow it; anything else is a thousands separator.
  const match = text.match(/^(.*)[.,](\d{1,2})$/);
  if (match) {
    whole = match[1] ?? '';
    fraction = match[2] ?? '';
  }
  whole = whole.replace(/[.,]/g, '');
  if (!/^\d+$/.test(whole)) return null;

  const cents = Number.parseInt(`${whole}${fraction.padEnd(2, '0')}`, 10);
  if (!Number.isSafeInteger(cents)) return null;
  return negative ? -cents : cents;
}

/** Cents as the text for an input: "18000" or "18000,50". */
export function centsToEuroInput(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '';
  const digits = String(Math.abs(cents)).padStart(3, '0');
  const whole = digits.slice(0, -2);
  const fraction = digits.slice(-2);
  const sign = cents < 0 ? '-' : '';
  return fraction === '00' ? `${sign}${whole}` : `${sign}${whole},${fraction}`;
}

/** "62,5" or "62.5" as the decimal string the API takes; null when invalid. */
export function percentInput(input: string): string | null {
  const text = input.trim().replace('%', '').replace(',', '.');
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(text)) return null;
  return text;
}
