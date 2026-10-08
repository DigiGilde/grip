import type { YearChoice } from './api';

export const WHOLE_PERIOD: YearChoice = 'all';

export function currentYearChoice(now: Date = new Date()): YearChoice {
  return String(now.getFullYear());
}

/** The years on offer: two back and two ahead of the current one. */
export function yearOptions(now: Date = new Date()) {
  const year = now.getFullYear();
  return [
    ...[-2, -1, 0, 1, 2].map((offset) => ({
      value: String(year + offset),
      label: String(year + offset),
    })),
    { value: WHOLE_PERIOD, label: 'Hele looptijd' },
  ];
}

export function periodLabel(value: YearChoice): string {
  return value === WHOLE_PERIOD ? 'de hele looptijd' : value;
}

export const YEAR_FILTER_LABEL = 'Jaar';

/**
 * The year a view of one assignment opens on: this year when the assignment
 * runs in it, otherwise its first year, and the whole period when that year
 * is not on offer. An assignment for next year has nothing to show in this one.
 */
export function startingYear(
  start: string | null | undefined,
  end: string | null | undefined,
  now: Date = new Date(),
): YearChoice {
  const current = currentYearChoice(now);
  if (!start) return current;
  const first = start.slice(0, 4);
  const last = (end ?? start).slice(0, 4);
  if (current >= first && current <= last) return current;
  const offered = yearOptions(now).some((option) => option.value === first);
  return offered ? first : WHOLE_PERIOD;
}
