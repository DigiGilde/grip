import { describe, expect, it } from 'vitest';
import { byDay, type UpdateItem } from './updates';

function item(id: string, day: string): UpdateItem {
  return {
    id,
    seq: Number(id),
    kind: 'quote_signed',
    when: '2026-10-09T08:00:00+00:00',
    when_text: 'vanochtend',
    day,
    parts: [{ text: 'Offerte voor ' }, { text: 'Opdracht Alfa', href: '/opdrachten/a1/offerte' }],
    text: 'Offerte voor Opdracht Alfa',
    count: 1,
    new: false,
  };
}

describe('byDay', () => {
  it('puts the items under the day they happened, in the order they came', () => {
    const days = byDay([item('5', 'Vandaag'), item('4', 'Vandaag'), item('3', 'Gisteren')]);
    expect(days.map((day) => [day.day, day.items.map((entry) => entry.id)])).toEqual([
      ['Vandaag', ['5', '4']],
      ['Gisteren', ['3']],
    ]);
  });

  it('has no days when there is no news', () => {
    expect(byDay([])).toEqual([]);
  });
});
