import { describe, expect, it } from 'vitest';
import {
  byDay,
  filterChoices,
  filterOf,
  isFiltered,
  unknownFilters,
  withFilter,
  type UpdateItem,
} from './updates';

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

const OPTIONS = {
  assignments: [
    { id: 'a1', name: 'Opdracht Alfa' },
    { id: 'a2', name: 'Opdracht Beta' },
  ],
  people: [{ id: 'p1', name: 'Pim Planner' }],
};

describe('the filter in the address', () => {
  it('reads an assignment and a person, and nothing else', () => {
    const params = new URLSearchParams('opdracht=a1&persoon=p1&pagina=2');
    expect(filterOf(params)).toEqual({ opdracht: 'a1', persoon: 'p1' });
    expect(filterOf(new URLSearchParams('opdracht='))).toEqual({});
    expect(isFiltered(filterOf(params))).toBe(true);
    expect(isFiltered({})).toBe(false);
  });

  it('sets one filter, or takes it away, and leaves the rest of the address', () => {
    const params = new URLSearchParams('opdracht=a1&zoek=x');
    expect(withFilter(params, 'persoon', 'p1').toString()).toBe('opdracht=a1&zoek=x&persoon=p1');
    expect(withFilter(params, 'opdracht', 'a2').toString()).toBe('opdracht=a2&zoek=x');
    expect(withFilter(params, 'opdracht', '').toString()).toBe('zoek=x');
    // The address it started from is not changed.
    expect(params.toString()).toBe('opdracht=a1&zoek=x');
  });

  it('names the filters whose id the options do not hold', () => {
    expect(unknownFilters({ opdracht: 'a1', persoon: 'p1' }, OPTIONS)).toEqual([]);
    expect(unknownFilters({ opdracht: 'a9', persoon: 'p1' }, OPTIONS)).toEqual(['opdracht']);
    // An assignment id is not a person.
    expect(unknownFilters({ persoon: 'a1' }, OPTIONS)).toEqual(['persoon']);
    expect(unknownFilters({}, { assignments: [], people: [] })).toEqual([]);
  });
});

describe('filterChoices', () => {
  it('offers a choice per filter with options, the whole feed first', () => {
    expect(filterChoices(OPTIONS, { persoon: 'p1' })).toEqual([
      {
        key: 'opdracht',
        label: 'Opdracht',
        value: '',
        options: [
          { value: '', label: 'Alle opdrachten' },
          { value: 'a1', label: 'Opdracht Alfa' },
          { value: 'a2', label: 'Opdracht Beta' },
        ],
      },
      {
        key: 'persoon',
        label: 'Persoon',
        value: 'p1',
        options: [
          { value: '', label: 'Iedereen' },
          { value: 'p1', label: 'Pim Planner' },
        ],
      },
    ]);
  });

  it('offers nothing to narrow a feed with nothing to narrow it to', () => {
    expect(filterChoices({ assignments: [], people: [] }, {})).toEqual([]);
    expect(filterChoices({ ...OPTIONS, people: [] }, {}).map((choice) => choice.key)).toEqual([
      'opdracht',
    ]);
  });
});
