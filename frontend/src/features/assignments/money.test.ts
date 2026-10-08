import { describe, expect, it } from 'vitest';
import { centsToInput, decimalToInput, parseDecimal, parseEuroToCents } from './money';

describe('parseEuroToCents', () => {
  it.each([
    ['1250', 125000],
    ['1250,5', 125050],
    ['1250,50', 125050],
    ['1.250,50', 125050],
    ['1,250.50', 125050],
    ['€ 1.250', 125000],
    ['0,05', 5],
    ['172800', 17280000],
  ])('reads %s as %d cents', (input, cents) => {
    expect(parseEuroToCents(input)).toBe(cents);
  });

  it.each(['', 'abc', '12,345,6', '-5', '1,2,3'])('refuses %j', (input) => {
    expect(parseEuroToCents(input)).toBeNull();
  });

  it('keeps large amounts exact', () => {
    expect(parseEuroToCents('90.071.992.547,99')).toBe(9007199254799);
  });
});

describe('centsToInput', () => {
  it('shows whole euros without a fraction and cents with a comma', () => {
    expect(centsToInput(125000)).toBe('1250');
    expect(centsToInput(125050)).toBe('1250,50');
    expect(centsToInput(5)).toBe('0,05');
    expect(centsToInput(null)).toBe('');
  });

  it('round trips with the parser', () => {
    for (const cents of [0, 5, 99, 100, 125050, 17280000]) {
      expect(parseEuroToCents(centsToInput(cents))).toBe(cents);
    }
  });
});

describe('decimals', () => {
  it('reads a comma or a point', () => {
    expect(parseDecimal('0,8')).toBe('0.8');
    expect(parseDecimal(' 50 ')).toBe('50');
    expect(parseDecimal('1.5')).toBe('1.5');
    expect(parseDecimal('half')).toBeNull();
    expect(parseDecimal('')).toBeNull();
  });

  it('shows what the API sent without trailing zeros', () => {
    expect(decimalToInput('0.800')).toBe('0,8');
    expect(decimalToInput('50.00')).toBe('50');
    expect(decimalToInput('100')).toBe('100');
    expect(decimalToInput(null)).toBe('');
  });
});
