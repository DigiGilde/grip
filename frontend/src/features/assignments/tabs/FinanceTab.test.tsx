import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { AssignmentShellContext } from '../shell';
import { referenceText, signalText, varianceText, varianceWord } from '../financeText';
import { FIGURES, allText, assignment, finance, mockApi, plain } from '../testing';
import { startingYear } from '@/features/overview/years';
import { FinanceTab } from './FinanceTab';

afterEach(() => vi.unstubAllGlobals());

function renderTab(data = finance(), shell = assignment()) {
  const fetchMock = mockApi({ '/api/assignments/a1/financial': data });
  const view = renderApp(
    <AssignmentShellContext.Provider value={shell}>
      <FinanceTab />
    </AssignmentShellContext.Provider>,
  );
  return { ...view, fetchMock };
}

const cells = (container: HTMLElement, selector: string) =>
  [...container.querySelectorAll(selector)].map((cell) => cell.getAttribute('text'));

describe('FinanceTab', () => {
  it('names the state of the money in the columns', async () => {
    const { container } = renderTab();
    await waitFor(() =>
      expect(container.querySelector('nldd-table[accessible-label^="Stand per"]')).not.toBeNull(),
    );
    const table = container.querySelector(
      'nldd-table[accessible-label^="Stand per"]',
    ) as HTMLElement;
    expect(cells(table, 'nldd-table-row[slot="header"] nldd-text-cell')).toEqual([
      'Begrotingsregel',
      'Begroot',
      'Gerealiseerd',
      'Nog gepland',
      'Kosten',
      'Verwacht totaal',
      'Afwijking',
      'Uitputting',
    ]);
  });

  it('shows the figures of the service and never its own sums', async () => {
    // Figures that do not add up on purpose: the screen must show them as sent.
    const odd = {
      ...FIGURES,
      expected_total_cents: 12345600,
      variance_cents: 99900,
      variance_pct: '0.5',
    };
    const { container } = renderTab(finance({ totals: odd }));
    await waitFor(() => expect(allText(container)).toContain('123.456'));
    const text = allText(container);
    expect(text).toContain('€ 999 (0,5%)');
    expect(text).toContain('Ruimte');
  });

  it('gives the reference date of the figures', async () => {
    const { container } = renderTab();
    await waitFor(() =>
      expect(allText(container)).toContain('Stand t/m februari 2026 (laatst afgesloten maand)'),
    );
  });

  it('puts the quote next to the budget, and says what is left to bill', async () => {
    const { container } = renderTab();
    await waitFor(() =>
      expect(
        container.querySelector('dl[aria-label="Offerte, aangeleverd en gefactureerd"]'),
      ).not.toBeNull(),
    );
    const text = allText(container);
    expect(text).toContain('€ 190.000');
    expect(text).toContain('hoger dan de begroting');
    // Delivered and invoiced are different facts, each with its own figure.
    expect(text).toContain('Aangeleverd');
    expect(text).toContain('Nog aan te leveren');
    expect(text).toContain('€ 13.500');
    expect(text).toContain('Gefactureerd');
    expect(text).toContain('€ 9.000');
    expect(text).toContain('Nog te factureren');
    expect(text).toContain('€ 4.500');
  });

  it('calls out the signals above the table, an overrun in words', async () => {
    const { container } = renderTab(
      finance({
        signals: [
          {
            kind: 'overrun',
            budget_line_id: 'l1',
            description: 'Productmanager',
            amount_cents: 500000,
            pct: '2.9',
            count: null,
            months: [],
          },
          {
            kind: 'months_not_closed',
            budget_line_id: null,
            description: null,
            amount_cents: null,
            pct: null,
            count: 2,
            months: ['2026-03-01', '2026-04-01'],
          },
        ],
      }),
    );
    await waitFor(() => expect(container.querySelectorAll('.signal').length).toBe(2));
    const signals = [...container.querySelectorAll('.signal')];
    const said = signals.map((signal) =>
      (signal.querySelector('nldd-text')?.textContent ?? '').replace(/\u00a0/g, ' '),
    );
    expect(said[0]).toContain('Overschrijding op Productmanager');
    expect(said[0]).toContain('€ 5.000');
    expect(said[1]).toContain('2 maanden zijn voorbij en nog niet afgesloten');
    expect(signals[0]).toHaveClass('signal-critical');
    // Above the table: attention comes before the figures.
    const table = container.querySelector('nldd-table') as Element;
    expect(
      signals[0]!.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('keeps the detail behind a row that opens, with persons and cost coverage', async () => {
    const { container } = renderTab();
    await waitFor(() => expect(container.querySelector('nldd-list[type="tree"]')).not.toBeNull());
    const row = container.querySelector('nldd-list[type="tree"] > nldd-list-item') as HTMLElement;
    expect(row).not.toHaveAttribute('expanded');
    const children = [...row.querySelectorAll('nldd-list-item[slot="children"]')];
    expect(children).toHaveLength(2);
    expect(allText(children[0] as HTMLElement)).toContain('Voorbeeld Een');
    expect(allText(children[0] as HTMLElement)).toContain('€ 162.000');
    expect(allText(children[1] as HTMLElement)).toContain('Hostingcontract');
    row.dispatchEvent(new Event('click', { bubbles: true }));
    await waitFor(() => expect(row).toHaveAttribute('expanded'));
  });

  it('says when amounts per person are withheld', async () => {
    const base = finance();
    const line = { ...base.lines[0]!, persons: [], persons_hidden: 2 };
    const { container } = renderTab(finance({ lines: [line] }));
    await waitFor(() => expect(allText(container)).toContain('2 personen zit in het totaal'));
    expect(allText(container)).not.toContain('Voorbeeld Een');
  });

  it('shows the months with closed ones marked, and the chart with its table', async () => {
    const { container } = renderTab();
    await waitFor(() =>
      expect(
        container.querySelector('nldd-table[accessible-label^="Inzet per maand"]'),
      ).not.toBeNull(),
    );
    const table = container.querySelector(
      'nldd-table[accessible-label^="Inzet per maand"]',
    ) as HTMLElement;
    const text = allText(table);
    expect(text).toContain('Afgesloten');
    expect(text).toContain('Open');
    expect(text).toContain('Onder de begroting');
    expect(container.querySelector('svg')).not.toBeNull();
    expect(allText(container)).toContain('€ 15.000 van de begroting');
  });

  it('offers the table as CSV for the chosen period', async () => {
    const { container } = renderTab();
    await waitFor(() => expect(container.querySelector('nldd-toolbar')).not.toBeNull());
    const year = new Date().getFullYear();
    const links = [...container.querySelectorAll('nldd-button[href]')].map((b) =>
      b.getAttribute('href'),
    );
    expect(links).toEqual([
      `/api/assignments/a1/financial/csv?year=${year}&section=lines`,
      `/api/assignments/a1/financial/csv?year=${year}&section=months`,
    ]);
  });

  it('warns that a potential assignment is pipeline', async () => {
    const { container } = renderTab(
      finance(),
      assignment({ phase: 'potential', status: 'quoted' }),
    );
    await waitFor(() =>
      expect(
        container.querySelector('nldd-banner[text="Deze opdracht is nog niet akkoord"]'),
      ).not.toBeNull(),
    );
  });
});

describe('finance wording', () => {
  it('says room, overrun or none', () => {
    expect(varianceWord({ variance_cents: 1 })).toBe('Ruimte');
    expect(varianceWord({ variance_cents: -1 })).toBe('Overschrijding');
    expect(varianceWord({ variance_cents: 0 })).toBe('Geen ruimte');
    expect(plain(varianceText({ variance_cents: -500000, variance_pct: '-2.9' }))).toBe(
      '€ -5.000 (-2,9%)',
    );
    expect(plain(varianceText({ variance_cents: 0, variance_pct: null }))).toBe('€ 0');
  });

  it('says so when no month is closed', () => {
    expect(referenceText(null)).toContain('nog geen maand afgesloten');
  });

  it('names free room against the threshold', () => {
    const text = signalText(
      {
        kind: 'free_room',
        budget_line_id: 'l1',
        description: 'Ontwerper',
        amount_cents: 2000000,
        pct: '18.5',
        count: null,
        months: [],
      },
      '10',
    );
    expect(text.variant).toBe('neutral');
    expect(plain(text.text)).toContain('Vrije ruimte op Ontwerper');
    expect(text.text).toContain('18,5%');
    expect(text.text).toContain('drempel van 10%');
  });
});

describe('the year the tab opens on', () => {
  const now = new Date('2026-10-08T12:00:00');

  it('is this year when the assignment runs in it', () => {
    expect(startingYear('2026-01-01', '2026-12-31', now)).toBe('2026');
    expect(startingYear('2025-07-01', '2027-06-30', now)).toBe('2026');
    expect(startingYear(null, null, now)).toBe('2026');
  });

  it('is the first year of an assignment that lies in another year', () => {
    expect(startingYear('2027-01-01', '2027-12-31', now)).toBe('2027');
    expect(startingYear('2025-01-01', '2025-12-31', now)).toBe('2025');
  });

  it('is the whole period when that year is not on offer', () => {
    expect(startingYear('2031-01-01', '2031-12-31', now)).toBe('all');
  });
});
