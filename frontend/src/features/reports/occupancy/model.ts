import { formatDate, formatPercent } from '@/lib/format';
import type { OccupancyCell, OccupancyPart, PersonOccupancy } from '../api';
import { monthName } from '../labels';
import { cellState } from './scale';

/** problems: overbooked first, then most room. free: most room this month first. */
export type SortMode = 'problems' | 'name' | 'free';

const number = (value: string | null | undefined) =>
  value === null || value === undefined ? 0 : Number(value);

const byName = (a: PersonOccupancy, b: PersonOccupancy) =>
  a.person_name.localeCompare(b.person_name, 'nl');

/** Free capacity this month in percent; -1 for someone who is not deployable now. */
const freeNow = (person: PersonOccupancy) =>
  person.now_pct === null || person.now_pct === undefined
    ? -1
    : Math.max(0, 100 - Number(person.now_pct));

export function sortPersons(persons: readonly PersonOccupancy[], mode: SortMode) {
  const rows = [...persons];
  if (mode === 'name') return rows.sort(byName);
  if (mode === 'free') return rows.sort((a, b) => freeNow(b) - freeNow(a) || byName(a, b));
  return rows.sort((a, b) => {
    const over = (b.over_months?.length ?? 0) - (a.over_months?.length ?? 0);
    if (over !== 0) return over;
    const free = number(a.average_pct) - number(b.average_pct);
    return free !== 0 ? free : byName(a, b);
  });
}

/** Whether a person has any inzet in the months shown. */
export const hasInzet = (person: PersonOccupancy) =>
  person.cells.some((cell) => Number(cell.pct) > 0);

/** A cell in a few words, for a screen reader walking the table. */
export function describeCell(cell: OccupancyCell): string {
  const pct = number(cell.pct);
  const state = cellState(cell.available, pct);
  if (state === 'unavailable') return 'niet inzetbaar';
  if (state === 'empty') return 'geen inzet';
  const words = [formatPercent(cell.pct)];
  if (state === 'over') words.push('boven 100%');
  const tentative = number(cell.tentative_pct);
  if (tentative > 0) {
    words.push(
      tentative >= pct
        ? 'onder voorbehoud'
        : `waarvan ${formatPercent(cell.tentative_pct)} onder voorbehoud`,
    );
  }
  words.push(cell.established ? 'vastgesteld' : 'gepland');
  return words.join(', ');
}

/** How firm a part is, as it reads in a sentence: "100% vast op ...". */
export function partStanding(part: OccupancyPart): string {
  if (part.verbally_agreed) return 'onder voorbehoud (mondeling akkoord)';
  if (part.tentative) return 'onder voorbehoud';
  return part.established ? 'vastgesteld' : 'vast';
}

export const cellTitle = (person: PersonOccupancy, cell: OccupancyCell) =>
  `${person.person_name}, ${monthName(cell.month)}`;

/**
 * The one line under the name of someone who is free, in the words of the
 * Inzet board. Empty for someone who is not.
 */
export function freeSummary(person: PersonOccupancy, withRoomNow = false): string {
  if (person.idle_ahead) {
    return person.last_inzet_end
      ? `Vrij, laatste inzet tot ${formatDate(person.last_inzet_end)}`
      : 'Vrij, nog geen inzet gehad';
  }
  if (withRoomNow && person.now_pct !== null && Number(person.now_pct) < 100) {
    const now = Number(person.now_pct);
    return now === 0
      ? 'Nu vrij'
      : `Nu ${formatPercent(person.now_pct)}, ${formatPercent(100 - now)} vrij`;
  }
  return '';
}

/** The Inzet board, opened on one person. */
export const personBoardPath = (personId: string) => `/inzet?persoon=${personId}`;
