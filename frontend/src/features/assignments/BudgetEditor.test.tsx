import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { BudgetEditor } from './BudgetEditor';
import { allText, mockApi, plain } from './testing';

afterEach(() => vi.unstubAllGlobals());

const BUDGET = {
  assignment_id: 'a1',
  assignment_name: 'Opdracht Alfa 2026',
  can_edit: true,
  total_budgeted_cents: 17280000,
  subtotals_by_year: { '2026': 17280000 },
  quoted_amount_cents: null,
  pricing_error: null,
  lines: [
    {
      id: 'l1',
      assignment_id: 'a1',
      description: 'Productmanager',
      kind: 'personnel',
      position: 1,
      role: 'Productmanager',
      fte: '0.800',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      rate_category: 'D',
      budgeted_cents: 17280000,
      budgeted_by_year: { '2026': 17280000 },
      pricing_error: null,
      intended_person_id: 'p1',
      intended_person_name: 'Voorbeeld Een',
      intended_tentative: true,
      intended_in_step: true,
      intended_notes: [],
    },
  ],
};

const CARDS = {
  may_manage: false,
  default_increase_pct: '0',
  items: [
    {
      year: new Date().getFullYear(),
      status: 'active',
      rate_bands: [{ category: 'B', monthly_rate_cents: 1312500 }],
      scale_bands: [
        { scale: 10, category: 'B' },
        { scale: 11, category: 'B' },
      ],
    },
  ],
};

function renderEditor(derive: unknown = { intended_person_id: 'p2', start_date: null, end_date: null, period_proposed: false, notes: [], rate_category: 'B', category_notes: [], monthly_rates: [], budgeted_cents: null }) {
  const fetchMock = mockApi({
    '/api/assignments/a1/budget-lines/derive': derive,
    '/api/assignments/a1/budget-lines/preview': {
      budgeted_cents: 7875000,
      budgeted_by_year: {},
      reason: null,
    },
    '/api/assignments/a1/budget': BUDGET,
    '/api/person-options': {
      items: [
        { id: 'p1', name: 'Voorbeeld Een' },
        { id: 'p2', name: 'Voorbeeld Twee', starts_on: '2026-12-01' },
      ],
    },
    '/api/rates/cards': CARDS,
  });
  return { ...renderApp(<BudgetEditor assignmentId="a1" />), fetchMock };
}

async function openNewLine(container: HTMLElement) {
  await waitFor(() =>
    expect(container.querySelector('nldd-button[text="Nieuwe begrotingsregel"]')).not.toBeNull(),
  );
  container
    .querySelector('nldd-button[text="Nieuwe begrotingsregel"]')
    ?.dispatchEvent(new Event('click'));
  await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).not.toBeNull());
  return document.querySelector('nldd-sheet') as HTMLElement;
}

const field = (sheet: HTMLElement, label: string) =>
  sheet.querySelector(`nldd-form-field[label="${label}"]`) as HTMLElement;

describe('budget line sheet', () => {
  it('shows who a line is meant for in the table, in the staffing sense', async () => {
    const { container } = renderEditor();
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(allText(container)).toContain('Beoogd: Voorbeeld Een, onder voorbehoud');
  });

  it('offers an optional intended person, with the start date of a new colleague', async () => {
    const { container } = renderEditor();
    const sheet = await openNewLine(container);
    const person = field(sheet, 'Beoogde persoon');
    expect(person).toHaveAttribute('optional');
    expect(person.getAttribute('supporting-label')).toBe(
      'De naam komt niet in de offerte; daar staat alleen de rol.',
    );
    await waitFor(() => expect(person.querySelectorAll('option').length).toBe(3));
    expect([...person.querySelectorAll('option')].map((o) => o.textContent)).toEqual([
      'Geen beoogde persoon',
      'Voorbeeld Een',
      'Voorbeeld Twee, start op 1 dec 2026',
    ]);
  });

  it('names scales with their rate, and fills in what follows from the person', async () => {
    const { container, fetchMock } = renderEditor();
    const sheet = await openNewLine(container);
    const scale = field(sheet, 'Schaal en tarief');
    await waitFor(() =>
      expect(allText(scale)).toContain('Schaal 10 en 11 (categorie B), € 13.125 per maand'),
    );
    expect(scale.querySelector('select')).toHaveValue('');

    field(sheet, 'Beoogde persoon')
      .querySelector('nldd-dropdown')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: 'p2' } }));
    await waitFor(() =>
      expect(field(sheet, 'Schaal en tarief').querySelector('select')).toHaveValue('B'),
    );
    const moved = field(sheet, 'Schaal en tarief');
    expect(moved.getAttribute('supporting-label')).toContain('Volgt uit de beoogde persoon');
    // The result sits directly under the person, and the field it changed right after it.
    const order = [...sheet.querySelectorAll('nldd-form-field, nldd-banner')].map(
      (el) => el.getAttribute('label') ?? el.getAttribute('text'),
    );
    const at = order.indexOf('Beoogde persoon');
    expect(plain(order[at + 1])).toBe(
      'Volgt uit de beoogde persoon: Schaal 10 en 11 (categorie B), € 13.125 per maand',
    );
    expect(order[at + 2]).toBe('Schaal en tarief');
    const calls = (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain('/api/assignments/a1/budget-lines/derive');

    // Changing away from it says so at the field.
    moved.querySelector('nldd-dropdown')?.dispatchEvent(new CustomEvent('change', { detail: { value: 'C' } }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner[text^="De beoogde persoon declareert in"]')).not.toBeNull(),
    );
  });

  it('shows nothing derived to a reader who gets no category', async () => {
    const { container } = renderEditor({ intended_person_id: 'p2', start_date: null, end_date: null, period_proposed: false, notes: ['Start op 1 december 2026.'] });
    const sheet = await openNewLine(container);
    field(sheet, 'Beoogde persoon')
      .querySelector('nldd-dropdown')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: 'p2' } }));
    await waitFor(() =>
      expect(field(sheet, 'Beoogde persoon').querySelector('select')).toHaveValue('p2'),
    );
    const scale = field(sheet, 'Schaal en tarief');
    expect(scale.querySelector('select')).toHaveValue('');
    expect(scale.getAttribute('supporting-label')).not.toContain('Volgt uit');
    // A raw condition from the server is never shown; without a summary, nothing.
    expect(allText(sheet)).not.toContain('Start op 1 december 2026.');
    expect(sheet.querySelector('nldd-banner')).toBeNull();
  });

  it('shows the amount the server computed as the outcome', async () => {
    const { container } = renderEditor();
    const sheet = await openNewLine(container);
    await waitFor(() => expect(allText(sheet)).toContain('Begroot voor deze regel: € 78.750'));
  });

  it('works without a person exactly as before', async () => {
    const { container } = renderEditor();
    const sheet = await openNewLine(container);
    expect(field(sheet, 'Beoogde persoon').querySelector('select')).toHaveValue('');
    expect(sheet.querySelector('nldd-banner')).toBeNull();
    expect(field(sheet, 'Schaal en tarief').querySelector('nldd-dropdown')).toHaveAttribute('required');
  });
});
