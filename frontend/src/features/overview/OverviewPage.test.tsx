import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FIGURES, allText, mockApi, plain } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import { OverviewPage } from './OverviewPage';
import { attentionItems, sharedReference, sortRows } from './model';
import { currentYearChoice } from './years';

afterEach(() => vi.unstubAllGlobals());

const ROW = {
  assignment_id: 'a1',
  name: 'Opdracht Alfa 2026',
  status: 'in_progress',
  phase: 'active' as const,
  client_name: 'Voorbeeldministerie',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  figures: FIGURES,
  pricing_error: null,
  reference_month: '2026-02-01',
  in_year: true,
  attention: [],
};
const OVER = {
  ...ROW,
  assignment_id: 'a3',
  name: 'Opdracht Zeta 2026',
  attention: [
    { kind: 'overrun', text: 'Verwacht totaal € 3.000 boven de begroting.', tab: 'finance' },
    { kind: 'months_not_closed', text: '2 maanden met inzet zijn nog niet afgesloten.', tab: 'monthClose' },
  ],
};
const PIPELINE = { ...FIGURES, budgeted_cents: 5000000, expected_total_cents: 5000000 };
const PROSPECT = {
  ...ROW,
  assignment_id: 'a2',
  name: 'Opdracht Epsilon 2027',
  status: 'quoted',
  phase: 'potential' as const,
  figures: PIPELINE,
  reference_month: null,
};
const LATER = { ...PROSPECT, assignment_id: 'a4', name: 'Opdracht Eta 2027', in_year: false };
const DONE = { ...ROW, assignment_id: 'a5', name: 'Opdracht Gamma 2025', status: 'completed', phase: 'closed' as const };

const FULL = {
  year: 2026,
  rows: [ROW, OVER, PROSPECT, LATER, DONE],
  figures_active: FIGURES,
  figures_potential: PIPELINE,
  figures_closed: FIGURES,
  to_deliver_cents: 1350000,
  to_invoice_cents: 450000,
};

const tables = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-table')].map((t) => t.getAttribute('accessible-label'));

function renderPage(overview: unknown, tasks: unknown = { items: [], counts: {} }) {
  const fetchMock = mockApi({ '/api/overview': overview, '/api/tasks/mine': tasks });
  return { ...renderApp(<OverviewPage />), fetchMock };
}

describe('OverviewPage', () => {
  it('asks for the current year by default', async () => {
    const { fetchMock } = renderPage({ year: 2026, rows: [] });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calls = (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain(`/api/overview?year=${currentYearChoice()}`);
  });

  it('starts with what needs attention, each point a link to where it is solved', async () => {
    const { container } = renderPage(FULL);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    // Above the figures and the lists.
    const order = [...container.querySelectorAll('nldd-title[text], .grip-tiles, nldd-table')];
    expect(order[0]?.getAttribute('text')).toBe('Wat vraagt aandacht');
    const links = [...container.querySelectorAll('nldd-link')].map((link) => link.getAttribute('href'));
    expect(links).toContain('/opdrachten/a3/financieel');
    expect(links).toContain('/opdrachten/a3/maandafsluiting');
    expect(allText(container)).toContain('Verwacht totaal € 3.000 boven de begroting.');
  });

  it('says nothing about attention when there is nothing', async () => {
    const { container } = renderPage({ ...FULL, rows: [ROW] });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-title[text="Wat vraagt aandacht"]')).toBeNull();
  });

  it('shows a few figures for running work, and the pipeline apart', async () => {
    const { container } = renderPage(FULL);
    await waitFor(() => expect(container.querySelector('.grip-tiles')).not.toBeNull());
    const labels = [...container.querySelectorAll('.grip-tile__label')].map((el) => el.textContent);
    expect(labels).toEqual([
      'Verwacht totaal lopend werk, 2026',
      'Gerealiseerd',
      'Nog aan te leveren',
      'Pijplijn',
    ]);
    const text = plain(allText(container));
    expect(text).toContain('t/m februari 2026');
    expect(text).toContain('als alle potentiële opdrachten doorgaan; telt niet mee in lopend werk');
    expect(text).toContain('€ 13.500');
  });

  it('lists running work compactly: four columns, the reference month said once', async () => {
    const { container } = renderPage(FULL);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(tables(container)).toEqual(['Lopende opdrachten, 2026', 'Potentiële opdrachten, 2026']);
    const header = container.querySelector('nldd-table nldd-table-row[slot="header"]');
    expect([...(header?.children ?? [])].map((cell) => cell.getAttribute('text'))).toEqual([
      'Opdracht',
      'Begroot',
      'Verwacht totaal',
      'Afwijking',
    ]);
    const text = allText(container);
    expect(text.split('Stand t/m februari 2026').length - 1).toBe(1);
    // What needs attention comes first in the list.
    const names = [...container.querySelectorAll('nldd-table')][0]?.querySelectorAll('nldd-link');
    expect([...(names ?? [])].map((link) => link.getAttribute('text'))).toEqual([
      'Opdracht Zeta 2026',
      'Opdracht Alfa 2026',
    ]);
  });

  it('leaves out what does not run in the year, says so, and keeps closed work behind a button', async () => {
    const { container } = renderPage(FULL);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const text = allText(container);
    expect(text).not.toContain('Opdracht Eta 2027');
    expect(text).toContain('1 opdracht loopt niet in 2026 en staat hier niet.');
    expect(container.querySelector('nldd-button[text="Toon de hele looptijd"]')).not.toBeNull();
    expect(text).not.toContain('Opdracht Gamma 2025');
    container
      .querySelector('nldd-button[text="Toon afgesloten opdrachten (1)"]')
      ?.dispatchEvent(new Event('click'));
    await waitFor(() => expect(allText(container)).toContain('Opdracht Gamma 2025'));
  });

  it('gives a reader without money rights names and statuses, and no tiles', async () => {
    const bare = (row: typeof ROW) => {
      const { figures: _figures, pricing_error: _error, reference_month: _month, ...rest } = row;
      return rest;
    };
    const { container } = renderPage({
      year: 2026,
      rows: [
        {
          ...bare(ROW),
          attention: [
            {
              kind: 'rate_mismatch',
              text: '1 persoon declareert in een andere schaal dan de begrotingsregel aanneemt.',
              tab: 'staffing',
            },
          ],
        },
      ],
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('.grip-tiles')).toBeNull();
    const header = container.querySelector('nldd-table nldd-table-row[slot="header"]');
    expect(header?.children.length).toBe(1);
    expect(allText(container)).not.toContain('€');
    expect(
      [...container.querySelectorAll('nldd-link')].map((link) => link.getAttribute('href')),
    ).toContain('/opdrachten/a1/bemensing');
  });

  it('shows the first tasks of the reader with a link to Taken', async () => {
    const task = (id: string, due: string | null) => ({
      id,
      title: `Taak ${id}`,
      case_label: 'Opdracht Alfa 2026',
      status: 'todo',
      due_on: due,
      link: `/opdrachten/a1/taken?taak=${id}`,
    });
    const { container } = renderPage(FULL, {
      items: [task('t2', '2026-11-01'), task('t1', '2026-10-10'), { ...task('t3', null), status: 'done' }],
      counts: {},
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-title[text="Mijn taken"]')).not.toBeNull(),
    );
    const links = [...container.querySelectorAll('nldd-link')].map((link) => link.getAttribute('text'));
    expect(links.indexOf('Taak t1')).toBeLessThan(links.indexOf('Taak t2'));
    expect(links).not.toContain('Taak t3');
    expect(links).toContain('Naar Taken');
  });
});

describe('start page model', () => {
  it('puts an overrun first, then other points, then the rest by name', () => {
    const other = { ...ROW, assignment_id: 'b', name: 'Beta', attention: [{ kind: 'not_priced', text: 'x.', tab: 'budget' }] };
    expect(sortRows([ROW, other, OVER], 'attention').map((row) => row.name)).toEqual([
      'Opdracht Zeta 2026',
      'Beta',
      'Opdracht Alfa 2026',
    ]);
    expect(sortRows([OVER, ROW], 'name').map((row) => row.name)).toEqual([
      'Opdracht Alfa 2026',
      'Opdracht Zeta 2026',
    ]);
    expect(attentionItems([ROW, OVER]).map((item) => item.href)).toEqual([
      '/opdrachten/a3/financieel',
      '/opdrachten/a3/maandafsluiting',
    ]);
  });

  it('knows when one reference month holds for all rows', () => {
    expect(sharedReference([ROW, OVER])).toBe('2026-02-01');
    expect(sharedReference([ROW, { ...OVER, reference_month: null }])).toBeUndefined();
    expect(sharedReference([{ ...ROW, reference_month: null }])).toBeNull();
  });
});
