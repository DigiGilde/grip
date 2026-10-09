import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { BudgetEditor } from './BudgetEditor';
import { allText, assignment, mockApi, plain } from './testing';

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

const BANDS = {
  rate_bands: [{ category: 'B', monthly_rate_cents: 1312500 }],
  scale_bands: [
    { scale: 10, category: 'B' },
    { scale: 11, category: 'B' },
  ],
};
const CARDS = {
  may_manage: false,
  default_increase_pct: '0',
  items: [
    { status: 'active', valid_from: '2020-01-01', valid_to: null, name: 'Tarieven 2026', ...BANDS },
  ],
};
const VALID = {
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  stretches: [
    {
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      card_id: 'c1',
      card_name: 'Tarieven 2026',
      card_valid_to: '2026-12-31',
      ...BANDS,
    },
  ],
  crosses_cards: false,
  rates_differ: false,
  has_gap: false,
  summary: 'Volgens Tarieven 2026, geldig t/m 31 december 2026.',
};

const DERIVED = {
  intended_person_id: 'p2',
  summary: [
    'Rol van Voorbeeld Twee: Productmanager (uit Wies).',
    'Heeft 60% vrij in deze periode.',
  ],
  notes: [],
  role: 'Productmanager',
  role_source_text: 'uit Wies',
  start_date: '2026-12-01',
  end_date: '2027-06-30',
  period_proposed: true,
  period_source_text: 'de looptijd van de opdracht',
  fte: '0.600',
  fte_source_text: '60% vrij in deze periode',
  rate_summary: 'Schaal 10 valt in categorie B: € 13.125 per maand per FTE in 2026.',
  rate_category: 'B',
  monthly_rates: [],
  budgeted_cents: null,
};

function renderEditor(derive: unknown = DERIVED, detail = assignment(), valid: unknown = VALID) {
  const fetchMock = mockApi({
    '/api/assignments/a1/budget-lines/derive': derive,
    '/api/assignments/a1/budget-lines/preview': {
      budgeted_cents: 7875000,
      budgeted_by_year: {},
      reason: null,
    },
    '/api/assignments/a1/budget': BUDGET,
    '/api/assignments/a1': detail,
    '/api/person-options': {
      items: [
        { id: 'p1', name: 'Voorbeeld Een' },
        { id: 'p2', name: 'Voorbeeld Twee', starts_on: '2026-12-01' },
      ],
    },
    '/api/rates/cards': CARDS,
    '/api/rates/valid': valid,
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
    expect(container.querySelector('nldd-tag')?.getAttribute('text')).toBe(
      'Beoogd: Voorbeeld Een, onder voorbehoud',
    );
  });

  it('edits through the row and keeps the rest behind one quiet menu', async () => {
    const { container } = renderEditor();
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Bewerk"]')).toBeNull();
    // No "Acties" header is shown; the one a screen reader gets is hidden from sight.
    const actionHeaders = [...container.querySelectorAll('nldd-table-row[slot="header"] *')].filter(
      (el) => el.childElementCount === 0 && el.textContent === 'Acties',
    );
    expect(actionHeaders.map((el) => el.className)).toEqual(['grip-visually-hidden']);
    expect(container.querySelector('[text="Acties"]')).toBeNull();
    // The role is said once: the name, then the facts.
    const name = container.querySelector('nldd-table nldd-link');
    expect(name?.getAttribute('text')).toBe('Productmanager');
    expect(allText(container)).toContain('0,8 FTE');
    const more = container.querySelector('nldd-icon-button');
    expect(more?.getAttribute('accessible-label')).toBe('Meer acties voor Productmanager');
    expect(
      [...(more?.querySelectorAll('nldd-menu-item') ?? [])].map((i) => i.getAttribute('text')),
    ).toEqual(['Bekijk inzet', 'Verwijder']);
    expect(more?.querySelector('nldd-menu-item[text="Verwijder"]')).toHaveAttribute('destructive');
    // Removing asks first, and says what goes with it.
    more?.querySelector('nldd-menu-item[text="Verwijder"]')?.dispatchEvent(new Event('select'));
    await waitFor(() => expect(document.querySelector('nldd-modal-dialog[open]')).not.toBeNull());
    expect(document.querySelector('nldd-modal-dialog')?.getAttribute('supporting-text')).toContain(
      'De reservering van Voorbeeld Een vervalt ook.',
    );
    // The name opens the edit sheet.
    name?.dispatchEvent(new Event('click', { cancelable: true }));
    await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).not.toBeNull());
  });

  it('says what is wrong at the field, not in a banner at the top', async () => {
    const { container } = renderEditor();
    const sheet = await openNewLine(container);
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(
        sheet.querySelector('nldd-form-field[label="Rol"]')?.getAttribute('supporting-label'),
      ).toBe('Kies een rol.'),
    );
    expect(sheet.querySelector('nldd-banner[variant="critical"]')).toBeNull();
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
      'Schaal 10 valt in categorie B: € 13.125 per maand per FTE in 2026.',
    );
    expect(
      sheet.querySelector('nldd-banner[variant="accent"]')?.getAttribute('supporting-text'),
    ).toBe('Heeft 60% vrij in deze periode.');
    // The role was empty, so it is proposed, with its source at the field itself.
    expect(
      sheet.querySelector('nldd-form-field[label="Rol"]')?.getAttribute('supporting-label'),
    ).toBe('Voorstel: uit Wies');
    // The size is filled in as a proposal, with where it comes from.
    const size = field(sheet, 'Omvang in FTE');
    expect(size.querySelector('nldd-text-field')?.getAttribute('value')).toBe('0,6');
    expect(size.getAttribute('supporting-label')).toBe('Voorstel: 60% vrij in deze periode');
    // The assignment has a period, so the line keeps following it.
    expect(sheet.querySelector('nldd-form-field[label="Begindatum"]')).toBeNull();
    const calls = (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain('/api/assignments/a1/budget-lines/derive');

    // Changing away from it says so at the field.
    moved
      .querySelector('nldd-dropdown')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: 'C' } }));
    await waitFor(() =>
      expect(
        sheet.querySelector('nldd-banner[text^="De beoogde persoon declareert in"]'),
      ).not.toBeNull(),
    );
  });

  it('shows nothing derived to a reader who gets no category', async () => {
    const { container } = renderEditor({
      intended_person_id: 'p2',
      start_date: null,
      end_date: null,
      period_proposed: false,
      notes: ['Start op 1 december 2026.'],
    });
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
    expect(field(sheet, 'Schaal en tarief').querySelector('nldd-dropdown')).toHaveAttribute(
      'required',
    );
  });

  it('asks no dates: the period follows the assignment until it deviates', async () => {
    const { container } = renderEditor();
    const sheet = await openNewLine(container);
    await waitFor(() =>
      expect(plain(allText(sheet))).toContain(
        'Loopt mee met de opdracht: 1 jan 2026 t/m 31 dec 2026',
      ),
    );
    expect(sheet.querySelector('nldd-form-field[label="Begindatum"]')).toBeNull();
    sheet
      .querySelector('nldd-button[text="Afwijkende periode"]')
      ?.dispatchEvent(new Event('click'));
    await waitFor(() => expect(field(sheet, 'Begindatum')).not.toBeNull());
    sheet
      .querySelector('nldd-button[text="Laat meelopen met de opdracht"]')
      ?.dispatchEvent(new Event('click'));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-form-field[label="Begindatum"]')).toBeNull(),
    );
  });

  it('asks the period of an assignment without one in the same form, with one button', async () => {
    const { container } = renderEditor(DERIVED, assignment({ start_date: null, end_date: null }));
    const sheet = await openNewLine(container);
    await waitFor(() => expect(field(sheet, 'Begin van de opdracht')).not.toBeNull());
    expect(field(sheet, 'Einde van de opdracht')).not.toBeNull();
    // No form inside the form: nothing saves the period on its own.
    expect(
      sheet.querySelector('nldd-button[text="Bewaar de looptijd van de opdracht"]'),
    ).toBeNull();
    expect(allText(sheet)).toContain('vul haar hier in');
    // No rate card is named while the period is unknown.
    expect(field(sheet, 'Schaal en tarief').getAttribute('supporting-label')).toBe(
      'Het tarief volgt zodra de periode bekend is.',
    );
  });

  it('names the rate card that is valid over the period, and says when the period crosses cards', async () => {
    const { container } = renderEditor(DERIVED, assignment(), {
      ...VALID,
      crosses_cards: true,
      rates_differ: true,
      summary:
        'Tot en met 30 juni volgens Tarieven 2026, daarna volgens Tarieven vanaf 1 juli 2026.',
    });
    const sheet = await openNewLine(container);
    await waitFor(() =>
      expect(field(sheet, 'Schaal en tarief').getAttribute('supporting-label')).toContain(
        'volgens Tarieven 2026',
      ),
    );
    expect(
      sheet.querySelector('nldd-banner[text="De periode loopt over meer dan één tarievenkaart"]'),
    ).not.toBeNull();
    const calls = (vi.mocked(fetch).mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain('/api/rates/valid?start_date=2026-01-01&end_date=2026-12-31');
  });

  it('says plainly when part of the period has no rate card', async () => {
    const { container } = renderEditor(DERIVED, assignment(), {
      ...VALID,
      has_gap: true,
      summary: 'Vanaf 1 juli 2026 is er geen tarievenkaart.',
    });
    const sheet = await openNewLine(container);
    await waitFor(() =>
      expect(
        sheet.querySelector(
          'nldd-banner[text="Voor een deel van deze periode is er geen tarievenkaart"]',
        ),
      ).not.toBeNull(),
    );
  });
});
