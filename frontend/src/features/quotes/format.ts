import { formatDate } from '@/lib/format';
import { ZONE } from '@/lib/today';
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
  // The time on the instance's clock, whatever the device is set to.
  timeZone: ZONE,
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : dateTime.format(date);
}

/** What a client reads on the rate leaflet: the scales, then the category. */
export function scaleText(line: { scales?: number[]; rate_category?: string | null }): string {
  const scales = line.scales ?? [];
  const category = line.rate_category ?? '';
  if (scales.length === 0) return category ? `Categorie ${category}` : '';
  const list =
    scales.length === 1
      ? String(scales[0])
      : `${scales.slice(0, -1).join(', ')} en ${scales[scales.length - 1]}`;
  return category ? `${list} (categorie ${category})` : list;
}

const MONTH_NAMES = [
  'januari',
  'februari',
  'maart',
  'april',
  'mei',
  'juni',
  'juli',
  'augustus',
  'september',
  'oktober',
  'november',
  'december',
];

interface PeriodLine {
  kind: string;
  start_date?: string | null;
  end_date?: string | null;
}

/**
 * One sentence on a part month, with the first one as the example, or null
 * when every line covers whole months. Says why an amount is not the rate
 * times a number of months. Counts days; no amount is computed here.
 */
export function partMonthNote(lines: readonly PeriodLine[]): string | null {
  for (const line of lines) {
    if (line.kind !== 'personnel' || !line.start_date || !line.end_date) continue;
    const [sy, sm, sd] = line.start_date.slice(0, 10).split('-').map(Number);
    const [ey, em, ed] = line.end_date.slice(0, 10).split('-').map(Number);
    if (!sy || !sm || !sd || !ey || !em || !ed) continue;
    const daysIn = (year: number, month: number) => new Date(year, month, 0).getDate();
    const sameMonth = sy === ey && sm === em;
    let counted: number;
    let of: number;
    let month: number;
    let year: number;
    if (sameMonth && (sd > 1 || ed < daysIn(ey, em))) {
      [counted, of, month, year] = [ed - sd + 1, daysIn(ey, em), em, ey];
    } else if (sd > 1) {
      [counted, of, month, year] = [daysIn(sy, sm) - sd + 1, daysIn(sy, sm), sm, sy];
    } else if (ed < daysIn(ey, em)) {
      [counted, of, month, year] = [ed, daysIn(ey, em), em, ey];
    } else continue;
    return `Een maand die maar deels in de periode valt, telt naar rato van het aantal dagen: ${MONTH_NAMES[month - 1]} ${year} telt voor ${counted} van de ${of} dagen.`;
  }
  return null;
}

/** One clause on a rate that changes inside the period of a line, with the first date. */
export function rateChangeNote(
  lines: readonly { rate_periods?: { start_date: string }[] }[],
): string | null {
  for (const line of lines) {
    const change = line.rate_periods?.[1]?.start_date;
    if (change) return `Het tarief wijzigt per ${formatDate(change)}.`;
  }
  return null;
}

/** A code in blocks of eight, four to a line, so it reads and never overflows. */
export function codeLines(code: string): string[] {
  const blocks = code.match(/.{1,8}/g) ?? [];
  const lines: string[] = [];
  for (let index = 0; index < blocks.length; index += 4) {
    lines.push(blocks.slice(index, index + 4).join(' '));
  }
  return lines;
}
