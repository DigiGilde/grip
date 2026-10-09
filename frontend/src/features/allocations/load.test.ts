import { describe, expect, it } from 'vitest';
import { overLoadText } from './load';

const month = (m: string, pct: string) => ({ month: m, current_pct: '50.0', new_pct: pct });

describe('overLoadText', () => {
  it('says nothing when the inzet fits', () => {
    expect(overLoadText({ person_name: 'Lot Lid', over_months: [] })).toBeNull();
    expect(overLoadText(undefined)).toBeNull();
  });

  it('names the months and what the person ends up at', () => {
    expect(
      overLoadText({
        person_name: 'Lot Lid',
        over_months: [month('2026-03-01', '150.0'), month('2026-04-01', '112.5')],
      }),
    ).toBe('Lot Lid komt boven 100% in maart 2026 (150%) en april 2026 (112,5%)');
  });

  it('shortens a long period to its first months and a count', () => {
    const months = ['01', '02', '03', '04', '05', '06'].map((m) => month(`2026-${m}-01`, '180.0'));
    expect(overLoadText({ person_name: 'Lot Lid', over_months: months })).toBe(
      'Lot Lid komt boven 100% in januari 2026 (180%), februari 2026 (180%), maart 2026 (180%), april 2026 (180%) en nog 2 maanden',
    );
  });
});
