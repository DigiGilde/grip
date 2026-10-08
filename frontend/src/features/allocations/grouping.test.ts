import { describe, expect, it } from 'vitest';
import type { Allocation } from './api';
import { groupAllocations, mismatchText } from './grouping';

const rows: Allocation[] = [
  {
    id: '1',
    person_id: 'p1',
    person_name: 'Voorbeeld Een',
    assignment_name: 'Opdracht Beta',
    budget_line_id: 'l2',
    budget_line_description: 'Developer',
  },
  {
    id: '2',
    person_id: 'p2',
    person_name: 'Voorbeeld Twee',
    assignment_name: 'Opdracht Alfa',
    budget_line_id: 'l1',
    budget_line_description: 'Productmanager',
  },
  {
    id: '3',
    person_id: 'p1',
    person_name: 'Voorbeeld Een',
    assignment_name: 'Opdracht Alfa',
    budget_line_id: 'l1',
    budget_line_description: 'Productmanager',
  },
];

describe('groupAllocations', () => {
  it('groups per person, by name', () => {
    const groups = groupAllocations(rows, 'person');
    expect(groups.map((g) => [g.title, g.items.map((i) => i.id)])).toEqual([
      ['Voorbeeld Een', ['1', '3']],
      ['Voorbeeld Twee', ['2']],
    ]);
  });

  it('groups per budget line, by assignment and then line', () => {
    const groups = groupAllocations(rows, 'line');
    expect(groups.map((g) => [g.subtitle, g.title, g.items.length])).toEqual([
      ['Opdracht Alfa', 'Productmanager', 2],
      ['Opdracht Beta', 'Developer', 1],
    ]);
  });

  it('keeps a row without a visible line in a group of its own', () => {
    const groups = groupAllocations([{ id: '9', person_id: 'p', person_name: 'X' }], 'line');
    expect(groups).toHaveLength(1);
  });
});

describe('mismatchText', () => {
  it('says nothing without a signal', () => {
    expect(mismatchText(rows[0]!)).toBe('');
  });

  it('gives the bare signal to a reader without the categories', () => {
    const text = mismatchText({ ...rows[0]!, category_mismatch: true });
    expect(text).toContain('andere categorie');
    expect(text).not.toMatch(/categorie [A-E]\b/);
  });

  it('names the categories for a reader who got them', () => {
    const text = mismatchText({
      ...rows[0]!,
      category_mismatch: true,
      person_category: 'C',
      line_category: 'D',
    });
    expect(text).toContain('categorie C');
    expect(text).toContain('met D');
  });
});
