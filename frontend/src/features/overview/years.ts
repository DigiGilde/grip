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
