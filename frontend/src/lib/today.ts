/**
 * The one "today" of the screens: the day on the calendar of the instance.
 *
 * A date of the domain (a card holds from a day, a hire ends on a day) is a
 * day in the Netherlands, whatever the clock of the device says and whatever
 * day it is in UTC. The server decides with the same rule
 * (`grip.core.clock`); a screen that proposed the UTC day would offer
 * yesterday until one or two in the night.
 */
export const ZONE = 'Europe/Amsterdam';

const PARTS = new Intl.DateTimeFormat('en-CA', {
  timeZone: ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** Today as yyyy-mm-dd on the instance's calendar. */
export function todayIso(now: Date = new Date()): string {
  const parts = Object.fromEntries(PARTS.formatToParts(now).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/** The day a number of days after an ISO date, as yyyy-mm-dd. */
export function addDays(iso: string, days: number): string {
  const [year = 0, month = 1, day = 1] = iso.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

/** The year it is on the instance's calendar. */
export function thisYear(now: Date = new Date()): number {
  return Number(todayIso(now).slice(0, 4));
}
