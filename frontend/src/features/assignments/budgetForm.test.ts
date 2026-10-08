import { describe, expect, it } from 'vitest';
import { intendedText, lineForm, lineInput, previewInput, proposedYear } from './budgetForm';

const personnel = {
  ...lineForm(),
  description: ' Productmanager ',
  role: 'Productmanager',
  fte: '0,8',
  category: 'D',
  ownPeriod: true,
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
      period_source: 'own',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
    });
    expect(lineInput(personnel, false)).not.toHaveProperty('kind');
  });

  it('builds a fixed line in cents', () => {
    const form = {
      ...lineForm(),
      kind: 'fixed',
      description: 'Hosting',
      amount: '15.000',
      year: '2026',
    };
    expect(lineInput(form, true)).toEqual({
      description: 'Hosting',
      kind: 'fixed',
      amount_cents: 1500000,
      year: 2026,
    });
  });

  it.each([
    [{ ...personnel, role: ' ' }, 'rol'],
    [{ ...lineForm(), kind: 'fixed', description: ' ', amount: '1', year: '2026' }, 'omschrijving'],
    [{ ...personnel, fte: 'veel' }, 'FTE'],
    [{ ...personnel, category: '' }, 'schaal'],
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

  it('leaves the category to the server when a person is intended', () => {
    const input = lineInput({ ...personnel, category: '', personId: 'p1' }, true);
    expect(input).toMatchObject({ intended_person_id: 'p1', fte: '0.8' });
    expect(input).not.toHaveProperty('rate_category');
  });

  it('sends no person for a line without one, and null to remove one', () => {
    expect(lineInput(personnel, true)).not.toHaveProperty('intended_person_id');
    const line = {
      id: '1',
      assignment_id: 'a',
      description: 'x',
      kind: 'personnel',
      position: 1,
      intended_person_id: 'p1',
    };
    expect(lineInput({ ...personnel, personId: 'p1' }, false, line)).not.toHaveProperty(
      'intended_person_id',
    );
    expect(lineInput({ ...personnel, personId: '' }, false, line)).toMatchObject({
      intended_person_id: null,
    });
  });

  it('says who a line is meant for, tentative and out of step in words', () => {
    const base = { id: '1', assignment_id: 'a', description: 'x', kind: 'personnel', position: 1 };
    expect(intendedText(base)).toBe('');
    expect(
      intendedText({
        ...base,
        intended_person_name: 'Voorbeeld Een',
        intended_tentative: true,
        intended_in_step: false,
      }),
    ).toBe(
      'Beoogd: Voorbeeld Een, onder voorbehoud, de reservering loopt niet meer gelijk met de regel',
    );
  });

  it('prices only what is filled in', () => {
    expect(previewInput({ ...lineForm(), fte: '0,8' })).toEqual({
      kind: 'personnel',
      fte: '0.8',
      period_source: 'assignment',
    });
    expect(previewInput(personnel)).toMatchObject({ rate_category: 'D', start_date: '2026-01-01' });
  });

  it('follows the period of the assignment unless the line has its own', () => {
    const parent = { start: '2026-03-01', end: '2026-09-30' };
    const following = { ...personnel, ownPeriod: false, startDate: '', endDate: '' };
    // A following line sends no dates: it moves with the assignment.
    const sent = lineInput(following, true);
    expect(sent).toMatchObject({ period_source: 'assignment' });
    expect(sent).not.toHaveProperty('start_date');
    expect(lineInput(personnel, true)).toMatchObject({
      period_source: 'own',
      start_date: '2026-01-01',
    });
    expect(previewInput(following)).not.toHaveProperty('start_date');
    const base = { id: '1', assignment_id: 'a', description: 'x', kind: 'personnel', position: 1 };
    expect(
      lineForm({ ...base, start_date: '2026-03-01', end_date: '2026-09-30' }, parent).ownPeriod,
    ).toBe(false);
    expect(
      lineForm({ ...base, start_date: '2026-04-01', end_date: '2026-09-30' }, parent).ownPeriod,
    ).toBe(true);
    expect(lineForm(undefined, parent).ownPeriod).toBe(false);
    expect(
      lineForm(
        { ...base, period_source: 'own', start_date: '2026-03-01', end_date: '2026-09-30' },
        parent,
      ).ownPeriod,
    ).toBe(true);
  });
});

describe('the year of a new fixed amount', () => {
  const today = new Date('2026-10-08T12:00:00');

  it('is the first year of an assignment that runs in another year', () => {
    expect(proposedYear({ start: '2027-01-01', end: '2027-12-31' }, today)).toBe('2027');
    expect(proposedYear({ start: '2024-03-01', end: '2025-02-28' }, today)).toBe('2024');
  });

  it('is this year when the assignment runs in it, or has no period yet', () => {
    expect(proposedYear({ start: '2026-07-01', end: '2027-06-30' }, today)).toBe('2026');
    expect(proposedYear({ start: '', end: '' }, today)).toBe('2026');
    expect(proposedYear(undefined, today)).toBe('2026');
  });
});
