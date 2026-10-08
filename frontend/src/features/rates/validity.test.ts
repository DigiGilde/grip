import { describe, expect, it } from 'vitest';
import { proposedStart } from './validity';

describe('proposedStart', () => {
  it('follows the last day any card covers', () => {
    expect(
      proposedStart('2026-10-08', [
        { valid_from: '2026-01-01', valid_to: '2026-12-31' },
        { valid_from: '2027-01-01', valid_to: '2027-12-31' },
        { valid_from: '2028-01-01', valid_to: '2028-12-31' },
      ]),
    ).toBe('2029-01-01');
  });

  it('starts the year after a last card without an end, or after today', () => {
    expect(proposedStart('2026-10-08', [{ valid_from: '2026-01-01', valid_to: null }])).toBe(
      '2027-01-01',
    );
    expect(proposedStart('2026-10-08', [])).toBe('2027-01-01');
  });
});
