import { describe, expect, it } from 'vitest';
import { cellDescription, openingScroll, type TimelineRow } from './layout';

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

describe('cellDescription', () => {
  const row = {
    cells: [0, 1, 2].map(() => ({ text: '', state: 'quiet', established: false, description: '' })),
    bars: [
      {
        key: 'b1',
        column: 0,
        span: 3,
        lane: 0,
        label: '50% Opdracht Alfa',
        description: '50% Opdracht Alfa, Developer, 1 jan 2026 t/m 31 mrt 2026',
        variant: 'filled',
        closedSpan: 0,
        clippedStart: false,
        clippedEnd: false,
        data: null,
      },
    ],
  } as unknown as TimelineRow;

  it('says all of a bar where it starts and only that it goes on in the months after', () => {
    expect(cellDescription(row, 0)).toBe(
      '50% Opdracht Alfa, Developer, 1 jan 2026 t/m 31 mrt 2026',
    );
    expect(cellDescription(row, 1)).toBe('50% Opdracht Alfa, loopt door');
    expect(cellDescription(row, 2)).toBe('50% Opdracht Alfa, loopt door');
  });
});
