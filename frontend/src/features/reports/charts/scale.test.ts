import { describe, expect, it } from 'vitest';
import { niceAxis } from './scale';

describe('niceAxis', () => {
  it('ends on a clean tick at or above the largest value', () => {
    expect(niceAxis(94)).toEqual({ max: 100, ticks: [0, 25, 50, 75, 100] });
    expect(niceAxis(100)).toEqual({ max: 100, ticks: [0, 25, 50, 75, 100] });
    expect(niceAxis(130).max).toBeGreaterThanOrEqual(130);
    expect(niceAxis(10190000).ticks.at(-1)).toBeGreaterThanOrEqual(10190000);
  });

  it('never has more ticks than asked for', () => {
    for (const largest of [1, 7, 94, 130, 999, 10190000, 123456789]) {
      const axis = niceAxis(largest);
      expect(axis.ticks.length).toBeLessThanOrEqual(5);
      expect(axis.ticks[0]).toBe(0);
      expect(axis.max).toBe(axis.ticks.at(-1));
    }
  });

  it('has an axis when there is nothing to show', () => {
    expect(niceAxis(0)).toEqual({ max: 1, ticks: [0, 1] });
    expect(niceAxis(Number.NaN)).toEqual({ max: 1, ticks: [0, 1] });
  });
});
