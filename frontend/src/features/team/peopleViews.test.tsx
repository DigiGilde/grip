import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { AllocationsPage } from '@/features/allocations/AllocationsPage';
import { board } from '@/features/allocations/board/testing';
import { BillabilityPage } from './BillabilityPage';
import { OccupancyPage } from './OccupancyPage';
import { PeoplePage } from './PeoplePage';
import { mockApi, texts } from './ui/testing';

afterEach(() => vi.unstubAllGlobals());

const PEOPLE = {
  items: [
    {
      id: 'p-1',
      name: 'Rik Medewerker',
      email: 'rik@example.org',
      is_active: true,
      manager_id: null,
      manager_name: null,
    },
  ],
  may_manage: false,
  period_start: '2026-06-01',
  period_end: '2026-06-01',
};

const ALL = ['list', 'board', 'occupancy', 'billability'];

function renderList(views: string[]) {
  mockApi({ '/api/people/views': { views }, '/api/people': PEOPLE });
  return renderApp(<PeoplePage />, { path: '/mensen' });
}

const tabs = (container: HTMLElement) => {
  const items = [...container.querySelectorAll('nldd-menu-bar-item')];
  return {
    texts: items.map((item) => item.getAttribute('text')),
    hrefs: items.map((item) => item.getAttribute('href')),
    current: items
      .filter((item) => item.hasAttribute('current'))
      .map((i) => i.getAttribute('text')),
  };
};

describe('the views of Mensen', () => {
  it('are the tabs the server lists, in its order, with the current one marked', async () => {
    const { container } = renderList(ALL);
    await waitFor(() => expect(container.querySelector('nldd-menu-bar-item')).not.toBeNull());
    expect(tabs(container)).toEqual({
      texts: ['Lijst', 'Bord', 'Bezetting', 'Declarabiliteit'],
      hrefs: ['/mensen', '/mensen/bord', '/mensen/bezetting', '/mensen/declarabiliteit'],
      current: ['Lijst'],
    });
  });

  it('are only those the server lists for this reader', async () => {
    const { container } = renderList(['list', 'board', 'occupancy']);
    await waitFor(() => expect(container.querySelector('nldd-menu-bar-item')).not.toBeNull());
    expect(tabs(container).texts).toEqual(['Lijst', 'Bord', 'Bezetting']);
  });

  it('draw no bar for a reader who has one view', async () => {
    const { container } = renderList(['list']);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
  });

  it('have no choice of view in the filters of the list', async () => {
    const { container } = renderList(ALL);
    await waitFor(() => expect(container.querySelector('nldd-menu-bar-item')).not.toBeNull());
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    // The list has no filters at all for this reader: any dropdown would be a choice of view.
    expect(container.querySelectorAll('nldd-dropdown')).toHaveLength(0);
  });

  it('put the board on the tab Bord, titled Bord', async () => {
    mockApi({
      '/api/people/views': { views: ALL },
      '/api/allocations/board': board(),
      '/api/vacancies/unfilled-roles': [],
      '/api/allocations/options': { people: [], lines: [] },
    });
    const { container } = renderApp(<AllocationsPage />, { path: '/mensen/bord' });
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    await waitFor(() => expect(tabs(container).current).toEqual(['Bord']));
    expect(container.querySelector('h1')).toHaveTextContent('Bord');
  });
});

describe('the board', () => {
  it('draws nothing of its own until the bar is known, so it does not jump', async () => {
    let answer: (response: Response) => void = () => {};
    const views = new Promise<Response>((resolve) => (answer = resolve));
    const rest = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0];
      const body =
        path === '/api/allocations/board'
          ? board()
          : path === '/api/allocations/options'
            ? { people: [], lines: [] }
            : [];
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', (input: RequestInfo | URL) =>
      String(input).startsWith('/api/people/views') ? views : rest(input),
    );
    const { container } = renderApp(<AllocationsPage />, { path: '/mensen/bord' });
    await waitFor(() => expect(container.querySelector('[data-state="loading"]')).not.toBeNull());
    expect(container.querySelector('table[role="grid"]')).toBeNull();
    expect(container.querySelector('nldd-action-bar, [aria-label^="Bord"]')).toBeNull();
    answer(
      new Response(JSON.stringify({ views: ALL }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    expect(tabs(container).current).toEqual(['Bord']);
  });
});

describe('Declarabiliteit', () => {
  const row = (over: Record<string, unknown>) => ({
    person_id: 'p-1',
    person_name: 'Rik Medewerker',
    year: 2026,
    target_pct: '90.00',
    target_cents: 19440000,
    realised_cents: 1800000,
    forecast_cents: 19800000,
    realisation_cents: 21600000,
    gap_cents: 2160000,
    unavailable_reason: null,
    ...over,
  });
  const KPI = {
    items: [
      row({
        person_id: 'p-2',
        person_name: 'Ilse Onder',
        target_cents: 20000000,
        realisation_cents: 15000000,
        gap_cents: -5000000,
      }),
      row({}),
      row({
        person_id: 'p-3',
        person_name: 'Noor Nieuw',
        target_pct: null,
        target_cents: null,
        realisation_cents: 1000000,
        gap_cents: null,
      }),
      row({
        person_id: 'p-4',
        person_name: 'Tim Tarief',
        target_pct: null,
        target_cents: null,
        realised_cents: null,
        forecast_cents: null,
        realisation_cents: null,
        gap_cents: null,
        unavailable_reason: 'De KPI kan niet worden berekend.',
      }),
    ],
    totals: {
      target_cents: 39440000,
      realised_cents: 3600000,
      forecast_cents: 40000000,
      realisation_cents: 37600000,
      gap_cents: -1840000,
    },
    scope: 'own',
    year: 2026,
    may_manage: false,
  };
  const BILLABILITY = {
    scope: 'own',
    persons: [],
    target_cents: 39440000,
    realised_cents: 3600000,
    forecast_cents: 40000000,
    realisation_cents: 37600000,
    with_target_count: 2,
    below_target_count: 1,
  };

  async function renderBillability() {
    mockApi({
      '/api/people/views': { views: ALL },
      '/api/reports/steering': { year: 2026, billability: BILLABILITY },
      '/api/kpi': KPI,
    });
    const view = renderApp(<BillabilityPage />, { path: '/mensen/declarabiliteit' });
    await waitFor(() => expect(view.container.querySelector('dl.grip-figures')).not.toBeNull());
    await waitFor(() => expect(view.container.querySelector('nldd-table-row')).not.toBeNull());
    return view.container;
  }

  it('has the short figures above one table, with the year chosen once', async () => {
    const container = await renderBillability();
    expect(container.querySelectorAll('nldd-table')).toHaveLength(1);
    expect(container.querySelectorAll('nldd-dropdown[accessible-label="Jaar"]')).toHaveLength(1);
    expect(container.querySelector('nldd-link[text^="Terug naar"]')).toBeNull();
    expect(container.querySelector('dl.grip-figures')?.textContent).toContain(
      'gerealiseerde inzet',
    );
    expect(texts(container, 'nldd-table-row[slot="header"] nldd-text-cell')).toContain(
      'Gerealiseerde inzet',
    );
    expect(tabs(container).current).toEqual(['Declarabiliteit']);
  });

  it('puts the year above what it changes, and says whose figures these are', async () => {
    const container = await renderBillability();
    const year = container.querySelector('nldd-dropdown[accessible-label="Jaar"]');
    const figures = container.querySelector('dl.grip-figures');
    const table = container.querySelector('nldd-table');
    expect(year && figures && table).toBeTruthy();
    const before = Node.DOCUMENT_POSITION_FOLLOWING;
    expect(year!.compareDocumentPosition(figures!) & before).toBeTruthy();
    expect(figures!.compareDocumentPosition(table!) & before).toBeTruthy();
    expect(container.textContent).toContain('Alleen de personen van wie je de KPI mag zien');
    const note = [...container.querySelectorAll('nldd-text')].find((el) =>
      el.textContent?.includes('Alleen de personen van wie je de KPI mag zien'),
    );
    expect(note!.compareDocumentPosition(figures!) & before).toBeTruthy();
  });

  it('shows who is under target in the first row, in words and in critical', async () => {
    const container = await renderBillability();
    const rows = [...container.querySelectorAll('nldd-table-row:not([slot="header"])')];
    const first = rows[0]!.querySelectorAll('nldd-text-cell');
    expect(first[0]).toHaveAttribute('text', 'Ilse Onder');
    expect(first[1]).toHaveAttribute('color', 'critical');
    expect(first[1]).toHaveAttribute('supporting-text', 'Onder target');
    expect(first[1]).toHaveAttribute('text', expect.stringContaining('50.000'));
    const second = rows[1]!.querySelectorAll('nldd-text-cell');
    expect(second[1]).not.toHaveAttribute('color', 'critical');
    expect(second[1]).toHaveAttribute('supporting-text', 'Op of boven target');
  });

  it('says Niet berekend when the server could not work it out, and Geen target when none is set', async () => {
    const container = await renderBillability();
    const rows = [...container.querySelectorAll('nldd-table-row:not([slot="header"])')];
    const cell = (index: number) => rows[index]!.querySelectorAll('nldd-text-cell')[1];
    expect(cell(2)).toHaveAttribute('text', 'Geen target');
    expect(cell(3)).toHaveAttribute('text', 'Niet berekend');
  });

  it('ends with the totals the server gave, and names a person in each row header', async () => {
    const container = await renderBillability();
    const rows = [...container.querySelectorAll('nldd-table-row:not([slot="header"])')];
    const last = rows[rows.length - 1]!.querySelectorAll('nldd-text-cell');
    expect(last[0]).toHaveAttribute('text', '**Totaal**');
    expect(last[3]).toHaveAttribute('text', expect.stringContaining('394.400'));
    for (const row of rows) {
      expect(row.querySelector('nldd-text-cell')).toHaveAttribute('row-header');
    }
  });

  it('shows the total against the target when the server gives it, and nothing when it does not', async () => {
    const container = await renderBillability();
    const total = (root: ParentNode) => {
      const rows = [...root.querySelectorAll('nldd-table-row:not([slot="header"])')];
      return rows[rows.length - 1]!.querySelectorAll('nldd-text-cell')[1];
    };
    expect(total(container)).toHaveAttribute('text', expect.stringContaining('18.400'));
    expect(total(container)).toHaveAttribute('color', 'critical');
    vi.unstubAllGlobals();
    const { gap_cents: _gap, ...totals } = KPI.totals;
    mockApi({
      '/api/people/views': { views: ALL },
      '/api/reports/steering': { year: 2026, billability: BILLABILITY },
      '/api/kpi': { ...KPI, totals },
    });
    const older = renderApp(<BillabilityPage />, { path: '/mensen/declarabiliteit' });
    await waitFor(() => expect(older.container.querySelector('nldd-table-row')).not.toBeNull());
    expect(total(older.container)).not.toHaveAttribute('text');
  });

  it('keeps Stel target in within reach on a narrow screen, in the row menu', async () => {
    mockApi({
      '/api/people/views': { views: ALL },
      '/api/reports/steering': { year: 2026, billability: BILLABILITY },
      '/api/kpi': { ...KPI, may_manage: true },
    });
    const { container } = renderApp(<BillabilityPage />, { path: '/mensen/declarabiliteit' });
    await waitFor(() => expect(container.querySelector('nldd-table-row')).not.toBeNull());
    const table = container.querySelector('nldd-table')!;
    expect(table.getAttribute('sm-columns')).toMatch(/48px$/);
    const items = container.querySelectorAll('nldd-menu-item[text="Stel target in"]');
    expect(items).toHaveLength(4);
    expect(container.querySelector('nldd-button[text="Stel target in"]')).toBeNull();
    const header = container.querySelector('nldd-table-row[slot="header"]')!;
    expect(header.querySelector('[hide-below]:last-child')).toBeNull();
  });

  it('keeps the person and the outcome on a narrow screen', async () => {
    const container = await renderBillability();
    const table = container.querySelector('nldd-table')!;
    expect(table.getAttribute('sm-columns')).toBeTruthy();
    const headers = [...container.querySelectorAll('nldd-table-row[slot="header"] nldd-text-cell')];
    const kept = headers
      .filter((cell) => !cell.hasAttribute('hide-below'))
      .map((cell) => cell.getAttribute('text'));
    expect(kept).toEqual(['Persoon', 'Ten opzichte van target']);
  });
});

describe('Bezetting', () => {
  const TIME = {
    person_count: 3,
    free_fte: '1.5',
    months: [{ month: '2026-06', available_fte: '3', free_fte: '1.5' }],
  };

  it('has the investeerruimte in time under the heat map, without the report page', async () => {
    mockApi({
      '/api/people/views': { views: ALL },
      '/api/reports/steering': { year: 2026 },
      '/api/reports/investment': { year: 2026, time: TIME },
    });
    const { container } = renderApp(<OccupancyPage />, { path: '/mensen/bezetting' });
    await waitFor(() =>
      expect(container.querySelector('[data-testid="investment-time"]')).not.toBeNull(),
    );
    expect(container.querySelector('nldd-title[text="Investeerruimte in tijd"]')).not.toBeNull();
    expect(tabs(container).current).toEqual(['Bezetting']);
    expect(container.querySelector('h1')).toHaveTextContent('Bezetting');
  });

  it('says there is nothing for the year, and keeps the year filter, when there are no figures', async () => {
    mockApi({
      '/api/people/views': { views: ALL },
      '/api/reports/steering': { year: 2026 },
      '/api/reports/investment': { year: 2026 },
    });
    const { container } = renderApp(<OccupancyPage />, { path: '/mensen/bezetting' });
    await waitFor(() =>
      expect(container.textContent).toContain('Voor 2026 zijn er geen bezettingsgegevens.'),
    );
    expect(container.textContent).not.toContain('geen toegang');
    expect(container.querySelector('nldd-dropdown[accessible-label="Jaar"]')).not.toBeNull();
  });
});

describe('the bar of Mensen', () => {
  const PEOPLE_EMPTY = {
    items: [],
    may_manage: false,
    period_start: '2026-06-01',
    period_end: '2026-06-01',
  };

  it('is there as soon as the content is, so nothing moves down when it arrives', async () => {
    mockApi({ '/api/people/views': { views: ALL }, '/api/people': PEOPLE_EMPTY });
    const { container } = renderApp(<PeoplePage />, { path: '/mensen' });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-menu-bar-item')).not.toBeNull();
  });

  it('is not drawn, nor waited for, when the server cannot say which views there are', async () => {
    mockApi({ '/api/people': PEOPLE_EMPTY });
    const { container } = renderApp(<PeoplePage />, { path: '/mensen' });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-menu-bar-item')).toBeNull();
  });
});
