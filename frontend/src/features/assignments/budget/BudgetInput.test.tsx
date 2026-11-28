import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PERMISSIONS, allText, assignment, finance, mockApi } from '../testing';
import { BUDGET, CARDS, renderBudgetPart } from './testing';

afterEach(() => vi.unstubAllGlobals());

const INPUT = 'nldd-table[accessible-label="Begrotingsregels"]';
const STAND = 'nldd-table[accessible-label^="Stand per"]';

const POTENTIAL = { phase: 'potential', status: 'quoted' } as const;

function renderForm(shell = assignment(POTENTIAL), quotes: unknown = { quotes: [] }) {
  const fetchMock = mockApi({
    '/api/assignments/a1/financial': finance({
      signals: [
        {
          kind: 'free_room',
          budget_line_id: 'l1',
          description: 'Productmanager',
          amount_cents: 17280000,
          pct: '100',
          count: null,
          months: [],
        },
      ],
    }),
    '/api/assignments/a1/budget': BUDGET,
    '/api/assignments/a1/quotes': quotes,
    '/api/rates/cards': CARDS,
  });
  return { ...renderBudgetPart(shell), fetchMock };
}

const asked = (fetchMock: ReturnType<typeof vi.fn>) =>
  (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));

describe('the form of the part per phase', () => {
  it('is the list of lines to enter until the agreement', async () => {
    const { container, fetchMock } = renderForm();
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    expect(container.querySelector(STAND)).toBeNull();
    expect(asked(fetchMock).some((url) => url.includes('/financial'))).toBe(false);
  });

  it('is still that list after a verbal agreement', async () => {
    const { container } = renderForm(assignment({ phase: 'potential', status: 'verbally_agreed' }));
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    expect(container.querySelector(STAND)).toBeNull();
  });

  it('is the state of the budget from the agreement on, also afterwards', async () => {
    for (const shell of [
      assignment({ phase: 'active', status: 'accepted' }),
      assignment({ phase: 'active', status: 'in_progress' }),
      assignment({ phase: 'closed', status: 'completed' }),
    ]) {
      vi.unstubAllGlobals();
      const { container, unmount } = renderForm(shell);
      await waitFor(() => expect(container.querySelector(STAND)).not.toBeNull());
      expect(container.querySelector(INPUT)).toBeNull();
      unmount();
    }
  });

  it('asks the server for nothing when the reader has no such row', async () => {
    const fetchMock = mockApi({});
    const { container } = renderBudgetPart(assignment(POTENTIAL), []);
    await waitFor(() => expect(container.querySelector('[data-state="no-access"]')).not.toBeNull());
    expect(asked(fetchMock)).toEqual([]);
    expect(container.querySelector('nldd-button[appearance="primary"]')).toBeNull();
    expect(document.querySelector('nldd-sheet[open]')).toBeNull();
  });
});

describe('the list of lines before the agreement', () => {
  it('has FTE, scale and amount, and no columns full of zeros', async () => {
    const { container } = renderForm();
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    const table = container.querySelector(INPUT) as HTMLElement;
    const header = table.querySelector('nldd-table-row[slot="header"]') as Element;
    expect(
      [...header.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text')),
    ).toEqual(['Regel', 'Begroot']);
    await waitFor(() => expect(allText(table)).toContain('0,8 FTE, schaal 14 en 15 (categorie D)'));
    expect(allText(table)).toContain('€ 172.800');
  });

  it('has no signals about free room, and no warning that it is not agreed yet', async () => {
    const { container } = renderForm();
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    expect(container.querySelector('.signal')).toBeNull();
    expect(allText(container)).not.toContain('Vrije ruimte');
    expect(container.querySelector('nldd-banner')).toBeNull();
    expect(allText(container)).not.toContain('nog niet akkoord');
  });

  it('stands at the left edge of the part, in no section of its own', async () => {
    const { container } = renderForm();
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    expect(container.querySelectorAll('nldd-simple-section')).toHaveLength(1);
  });

  it('has its one button in the head and the period in the bar', async () => {
    const { container } = renderForm();
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    const primary = [...container.querySelectorAll('nldd-button[appearance="primary"]')];
    expect(primary.map((button) => button.getAttribute('text'))).toEqual([
      'Nieuwe begrotingsregel',
    ]);
    expect(primary[0]?.closest('.thing-action')).not.toBeNull();
    expect(container.querySelector('nldd-button[text="Wijzig de looptijd"]')).not.toBeNull();
  });

  it('says what a change means while a quote lies with the client', async () => {
    const { container } = renderForm(assignment(POTENTIAL), {
      quotes: [{ status: 'issued', reference: 'VG-2026-0003', issued_at: '2026-10-01' }],
    });
    await waitFor(() =>
      expect(allText(container)).toContain(
        'Er ligt een offerte bij de opdrachtgever (VG-2026-0003).',
      ),
    );
  });

  it('asks for the period when the assignment has none', async () => {
    const { container } = renderForm(
      assignment({ ...POTENTIAL, start_date: null, end_date: null }),
    );
    await waitFor(() =>
      expect(allText(container)).toContain('De looptijd van de opdracht is nog niet ingevuld.'),
    );
    expect(container.querySelector('nldd-button[text="Vul de looptijd in"]')).not.toBeNull();
  });

  it('tells a reader who can change it, and gives no way to', async () => {
    const reader = assignment({ ...POTENTIAL, permissions: PERMISSIONS.lezer });
    mockApi({
      '/api/assignments/a1/budget': { ...BUDGET, can_edit: false },
      '/api/rates/cards': CARDS,
    });
    const { container } = renderBudgetPart(reader);
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    expect(allText(container)).toContain('Je kunt deze begroting bekijken.');
    expect(container.querySelector('nldd-button[appearance="primary"]')).toBeNull();
    expect(container.querySelector(`${INPUT} nldd-icon-button`)).toBeNull();
    expect(document.querySelector('nldd-sheet')).toBeNull();
  });
});

describe('the downloads under the list', () => {
  it('offers both tables as CSV to who may read the money', async () => {
    const { container } = renderForm();
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    await waitFor(() =>
      expect(
        [...container.querySelectorAll('nldd-link[href*="/financial/csv"]')].map((link) =>
          link.getAttribute('href'),
        ),
      ).toEqual([
        '/api/assignments/a1/financial/csv?year=all&section=lines',
        '/api/assignments/a1/financial/csv?year=all&section=months',
      ]),
    );
  });

  it('offers none to who may not read the money', async () => {
    const { container } = renderForm(
      assignment({ ...POTENTIAL, permissions: { ...PERMISSIONS.planner } }),
    );
    await waitFor(() => expect(container.querySelector(INPUT)).not.toBeNull());
    expect(container.querySelector('nldd-link[href*="/financial/csv"]')).toBeNull();
  });
});
