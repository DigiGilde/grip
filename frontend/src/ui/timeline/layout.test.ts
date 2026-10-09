import { describe, expect, it } from 'vitest';
import { openingScroll } from './layout';

describe('openingScroll', () => {
  it('puts the current month first beside the names', () => {
    // Names 140 wide, months 80 wide, the fourth month is the current one.
    expect(openingScroll(140 + 3 * 80, 140, 600)).toBe(240);
  });

  it('stays within what can scroll', () => {
    expect(openingScroll(140 + 11 * 80, 140, 500)).toBe(500);
    expect(openingScroll(140, 140, 0)).toBe(0);
  });
});
