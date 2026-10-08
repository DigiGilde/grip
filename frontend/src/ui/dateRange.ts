/**
 * The years a date field offers. Without bounds the design system's picker
 * lists the years from long ago; grip's dates are periods of work, rates and
 * contracts, so a window around today is all anyone picks from.
 */
const YEARS_BACK = 10;
const YEARS_AHEAD = 15;

export function dateFieldRange(now: Date = new Date()): { min: string; max: string } {
  const year = now.getFullYear();
  return { min: `${year - YEARS_BACK}-01-01`, max: `${year + YEARS_AHEAD}-12-31` };
}
