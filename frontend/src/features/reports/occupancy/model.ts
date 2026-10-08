import { formatPercent } from '@/lib/format';
import type { OccupancyCell, OccupancyPart, PersonOccupancy } from '../api';
import { monthName } from '../labels';
import { cellState } from './scale';

export type SortMode = 'problems' | 'name';

const number = (value: string | null | undefined) =>
  value === null || value === undefined ? 0 : Number(value);

const byName = (a: PersonOccupancy, b: PersonOccupancy) =>
  a.person_name.localeCompare(b.person_name, 'nl');

/**
 * Problems first: whoever is above 100 percent in most months on top, then
 * whoever has most room (the lowest average). Or simply by name.
 */
export function sortPersons(persons: readonly PersonOccupancy[], mode: SortMode) {
  const rows = [...persons];
  if (mode === 'name') return rows.sort(byName);
  return rows.sort((a, b) => {
    const over = (b.over_months?.length ?? 0) - (a.over_months?.length ?? 0);
    if (over !== 0) return over;
    const free = number(a.average_pct) - number(b.average_pct);
    return free !== 0 ? free : byName(a, b);
  });
}

/** What a part is, in words: firm or tentative, established or planned. */
export function partTags(part: OccupancyPart): string[] {
  const tags: string[] = [];
  if (part.verbally_agreed) tags.push('onder voorbehoud, mondeling akkoord');
  else if (part.tentative) tags.push('onder voorbehoud');
  tags.push(part.established ? 'vastgesteld' : 'gepland');
  return tags;
}

/** A cell in words, for a screen reader and for the detail below the table. */
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

export const cellTitle = (person: PersonOccupancy, cell: OccupancyCell) =>
  `${person.person_name}, ${monthName(cell.month)}`;

/** Whether a person has any inzet in the months shown. */
export const hasInzet = (person: PersonOccupancy) =>
  person.cells.some((cell) => Number(cell.pct) > 0);
