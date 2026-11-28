import { describe, expect, it } from 'vitest';
import { placeOf } from './track';

describe('placeOf', () => {
  it('joins the rows on one track, and leaves one alone without', () => {
    expect([0, 1, 2].map((index) => placeOf(index, 3))).toEqual(['first', 'between', 'last']);
    expect([0, 1].map((index) => placeOf(index, 2))).toEqual(['first', 'last']);
    expect(placeOf(0, 1)).toBe('only');
  });
});
