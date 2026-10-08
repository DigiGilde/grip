import { describe, expect, it } from 'vitest';
import { dayOf, formatDate } from './format';
import { addDays, thisYear, todayIso } from './today';

/** A moment given as wall time in the Netherlands with its offset. */
const at = (local: string, offset: '+01:00' | '+02:00') => new Date(`${local}:00${offset}`);

describe('today on the calendar of the instance', () => {
  it('is the local day at 23:30 and at 00:30 on a month boundary', () => {
    expect(todayIso(at('2026-10-31T23:30', '+01:00'))).toBe('2026-10-31');
    // Still 31 October in UTC: the case that offered yesterday.
    expect(todayIso(at('2026-11-01T00:30', '+01:00'))).toBe('2026-11-01');
  });

  it('holds around both changes of daylight saving', () => {
    expect(todayIso(at('2026-03-28T23:30', '+01:00'))).toBe('2026-03-28');
    expect(todayIso(at('2026-03-29T00:30', '+01:00'))).toBe('2026-03-29');
    expect(todayIso(at('2026-10-24T23:30', '+02:00'))).toBe('2026-10-24');
    expect(todayIso(at('2026-10-25T00:30', '+02:00'))).toBe('2026-10-25');
  });

  it('turns the year at local midnight', () => {
    expect(thisYear(at('2026-12-31T23:30', '+01:00'))).toBe(2026);
    expect(thisYear(at('2027-01-01T00:30', '+01:00'))).toBe(2027);
  });

  it('adds days over a month and over a change of the clock', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-03-28', 2)).toBe('2026-03-30');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('dates a stored moment on the local calendar, not on its first ten characters', () => {
    // Made at 00:56 on 9 October in the Netherlands; 8 October in UTC.
    expect(dayOf('2026-10-08T22:56:31+00:00')).toBe('2026-10-09');
    expect(dayOf('2026-10-08T22:56:31Z')).toBe('2026-10-09');
    // A moment that lost its zone on the way is UTC, as it was stored.
    expect(dayOf('2026-10-08T22:56:31.123456')).toBe('2026-10-09');
    expect(formatDate('2026-10-08T22:56:31+00:00')).toBe('9 okt 2026');
    expect(formatDate('2026-10-31T23:30:00+00:00')).toBe('1 nov 2026');
  });

  it('leaves a date of the domain alone', () => {
    expect(dayOf('2026-10-08')).toBe('2026-10-08');
    expect(formatDate('2026-10-08')).toBe('8 okt 2026');
  });
});
