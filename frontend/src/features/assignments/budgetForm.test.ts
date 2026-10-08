import { describe, expect, it } from 'vitest';
import { lineForm, lineInput } from './budgetForm';

const personnel = {
  ...lineForm(),
  description: ' Productmanager ',
  role: 'Productmanager',
  fte: '0,8',
  category: 'D',
  startDate: '2026-01-01',
  endDate: '2026-12-31',
};

describe('lineInput', () => {
  it('builds a personnel line with the kind only when it is new', () => {
    expect(lineInput(personnel, true)).toEqual({
      description: 'Productmanager',
      kind: 'personnel',
      role: 'Productmanager',
      fte: '0.8',
      rate_category: 'D',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
    });
    expect(lineInput(personnel, false)).not.toHaveProperty('kind');
  });

  it('builds a fixed line in cents', () => {
    const form = { ...lineForm(), kind: 'fixed', description: 'Hosting', amount: '15.000', year: '2026' };
    expect(lineInput(form, true)).toEqual({
      description: 'Hosting',
      kind: 'fixed',
      amount_cents: 1500000,
      year: 2026,
    });
  });

  it.each([
    [{ ...personnel, description: ' ' }, 'omschrijving'],
    [{ ...personnel, fte: 'veel' }, 'FTE'],
    [{ ...personnel, category: '' }, 'tariefcategorie'],
    [{ ...personnel, endDate: '' }, 'einddatum'],
    [{ ...lineForm(), kind: 'fixed', description: 'x', amount: 'x', year: '2026' }, 'bedrag'],
    [{ ...lineForm(), kind: 'fixed', description: 'x', amount: '1', year: '26' }, 'jaar'],
  ])('says what is wrong instead of sending it', (form, word) => {
    const result = lineInput(form, true);
    expect(typeof result).toBe('string');
    expect(String(result).toLowerCase()).toContain(word.toLowerCase());
  });

  it('starts from an existing line', () => {
    const form = lineForm({
      id: '1',
      assignment_id: 'a',
      description: 'Developer',
      kind: 'personnel',
      position: 1,
      fte: '1.000',
      rate_category: 'C',
      start_date: '2026-07-01',
      end_date: '2026-12-31',
    });
    expect(form.fte).toBe('1');
    expect(form.category).toBe('C');
  });
});
