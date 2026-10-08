import { describe, expect, it } from 'vitest';
import { centsToEuroInput, eurosToCents, percentInput } from './money';

describe('eurosToCents', () => {
  it.each([
    ['18000', 1800000],
    ['18.000', 1800000],
    ['18.000,50', 1800050],
    ['18000,5', 1800050],
    ['18000.50', 1800050],
    ['€ 1.250.000', 125000000],
    ['0', 0],
    ['-250', -25000],
    ['0,07', 7],
    ['12,', 1200],
  ])('reads %s as %i cents', (input, cents) => {
    expect(eurosToCents(input)).toBe(cents);
  });

  it.each(['', '  ', 'abc', '12,345,6x', '1e5', ','])('refuses %j', (input) => {
    expect(eurosToCents(input)).toBeNull();
  });

  it('does not lose a cent to floating point', () => {
    // 1.15 * 100 is 114.99999999999999 in floating point.
    expect(eurosToCents('1,15')).toBe(115);
    expect(eurosToCents('19,99')).toBe(1999);
  });
});

describe('centsToEuroInput', () => {
  it.each([
    [1800000, '18000'],
    [1800050, '18000,50'],
    [7, '0,07'],
    [0, '0'],
    [-25000, '-250'],
  ])('writes %i cents as %s', (cents, text) => {
    expect(centsToEuroInput(cents)).toBe(text);
  });

  it('round-trips', () => {
    for (const cents of [0, 1, 99, 100, 123456, 1800050]) {
      expect(eurosToCents(centsToEuroInput(cents))).toBe(cents);
    }
  });

  it('is empty for no value', () => {
    expect(centsToEuroInput(null)).toBe('');
  });
});

describe('percentInput', () => {
  it.each([
    ['90', '90'],
    ['62,5', '62.5'],
    ['100%', '100'],
    ['0.25', '0.25'],
  ])('reads %s as %s', (input, value) => {
    expect(percentInput(input)).toBe(value);
  });

  it.each(['', 'veel', '1.234', '12,345'])('refuses %j', (input) => {
    expect(percentInput(input)).toBeNull();
  });
});
