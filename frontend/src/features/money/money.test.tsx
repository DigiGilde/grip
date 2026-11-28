import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BillingPage } from '@/features/billing/BillingPage';
import { DeliveryPage } from '@/features/billing/DeliveryPage';
import { CostItemPage } from '@/features/costs/CostItemPage';
import type { Figures, Overview, OverviewRow } from '@/features/overview/api';
import type { Investment, Steering } from '@/features/reports/api';
import { currentReportYear } from '@/features/reports/years';
import { mockApi } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import { AssignmentsSheet } from './AssignmentsSheet';
import { MoneyPage } from './MoneyPage';
import { moneyRows, runningRows, type MoneySources } from './moneyRows';
import { PotentialPage } from './PotentialPage';
import { RunningAssignmentsPage } from './RunningAssignmentsPage';

afterEach(() => vi.unstubAllGlobals());

const plain = (text: string | null | undefined) => (text ?? '').replace(/\u00a0/g, ' ');

const FIGURES: Figures = {
  budgeted_cents: 115680000,
  realised_cents: 6880000,
  planned_cents: 94550000,
  costs_realised_cents: 840000,
  costs_forecast_cents: 960000,
  costs_cents: 1800000,
  expected_total_cents: 103230000,
  variance_cents: 12450000,
  variance_pct: '10.8',
  overrun: false,
  realised_total_cents: 7720000,
  realised_pct: '6.7',
};

const OVERRUN: Figures = {
  ...FIGURES,
  expected_total_cents: 120000000,
  variance_cents: -4320000,
  variance_pct: '-3.7',
  overrun: true,
};

const row = (over: Partial<OverviewRow>): OverviewRow => ({
  assignment_id: 'a1',
  name: 'Opdracht Alfa 2026',
  status: 'in_progress',
  phase: 'active',
  client_name: 'Voorbeeldministerie',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  figures: FIGURES,
  pricing_error: null,
  reference_month: '2026-02-01',
  in_year: true,
  ...over,
});

const OVERVIEW: Overview = {
  year: 2026,
  rows: [
    row({}),
    row({ assignment_id: 'a2', name: 'Opdracht Beta 2026', reference_month: null }),
    row({
      assignment_id: 'a3',
      name: 'Opdracht Epsilon 2027',
      phase: 'potential',
      status: 'quoted',
      in_year: false,
    }),
    row({
      assignment_id: 'a4',
      name: 'Opdracht Gamma 2025',
      phase: 'closed',
      status: 'completed',
      in_year: false,
    }),
  ],
  figures_active: FIGURES,
  to_deliver_cents: 6880000,
  to_invoice_cents: 0,
};

const STEERING = {
  year: 2026,
  turnover: { scope: 'all', figures: FIGURES },
  pipeline: {
    scope: 'all',
    statuses: [
      { status: 'issued', count: 1, total_cents: 43440000 },
      { status: 'accepted', count: 2, total_cents: 67850000 },
    ],
    waiting: [],
  },
  costs: {
    scope: 'all',
    forecast_cents: 2100000,
    covered_cents: 1800000,
    uncovered_cents: 300000,
    without_document_count: 3,
    items: [],
  },
} as unknown as Steering;

const OWN = {
  ...STEERING,
  turnover: { ...STEERING.turnover, scope: 'own' },
  pipeline: { ...STEERING.pipeline, scope: 'own' },
  costs: { ...STEERING.costs, scope: 'own' },
} as unknown as Steering;

const INVESTMENT = {
  year: 2026,
  money: { room_cents: -40040000, shortfall: true, months: [] },
} as unknown as Investment;

const SOURCES: MoneySources = {
  year: '2026',
  steering: STEERING,
  investment: INVESTMENT,
  overview: OVERVIEW,
  costs: { may_create: false },
};

const notices = (sources: MoneySources) =>
  Object.fromEntries(moneyRows(sources).map((item) => [item.key, plain(item.notice)]));

const keys = (sources: MoneySources) => moneyRows(sources).map((item) => item.key);

describe('moneyRows', () => {
  it('says what matters in every row, and over which year', () => {
    expect(notices(SOURCES)).toEqual({
      assignments: '2 opdrachten, € 124.500 ruimte in 2026',
      turnover: '€ 1.032.300 verwacht in 2026',
      investment: '€ 400.400 tekort in 2026',
      potential: '€ 434.400, 1 offerte uit 2026 wacht op akkoord',
      costs: '€ 3.000 ongedekt in 2026, 3 facturen zonder bijlage',
      billing: 'Nu € 68.800 nog aan te leveren',
      year: '',
    });
  });

  it('keeps one order, and every row leads to its own page', () => {
    expect(moneyRows(SOURCES).map((item) => [item.text, item.href])).toEqual([
      ['Lopende opdrachten', '/geld/opdrachten'],
      ['Omzet', '/geld/omzet'],
      ['Investeerruimte', '/geld/investeerruimte'],
      ['Potentieel', '/geld/potentieel'],
      ['Kosten', '/geld/kosten?jaar=2026'],
      ['Factureren', '/geld/factureren'],
      ['Jaarverantwoording', '/geld/jaarverantwoording'],
    ]);
  });

  it('says "jouw opdrachten" for figures of the own assignments', () => {
    expect(notices({ ...SOURCES, steering: OWN, investment: { year: 2026 } })).toEqual({
      assignments: '2 van jouw opdrachten, € 124.500 ruimte in 2026',
      turnover: '€ 1.032.300 verwacht in 2026, jouw opdrachten',
      potential: '€ 434.400, 1 offerte uit 2026 wacht op akkoord, jouw opdrachten',
      costs: '€ 3.000 ongedekt in 2026, 3 facturen zonder bijlage, jouw opdrachten',
      billing: 'Nu € 68.800 nog aan te leveren, jouw opdrachten',
      year: '',
    });
  });

  it('has no row for a block the reader did not get', () => {
    expect(keys({ year: '2026' })).toEqual([]);
    const withoutCosts = { ...STEERING, costs: undefined };
    expect(keys({ ...SOURCES, steering: withoutCosts })).not.toContain('costs');
    const withoutPipeline = { ...STEERING, pipeline: undefined };
    expect(keys({ ...SOURCES, steering: withoutPipeline })).not.toContain('potential');
    const noMoneyOverview = { year: 2026, rows: [row({ figures: null })] };
    expect(keys({ year: '2026', overview: noMoneyOverview })).toEqual([]);
  });

  it('keeps the row Kosten for who may add the first cost item', () => {
    const withoutCosts = { ...STEERING, costs: undefined };
    const row = moneyRows({
      ...SOURCES,
      steering: withoutCosts,
      costs: { may_create: true },
    }).find((item) => item.key === 'costs');
    expect(row?.href).toBe('/geld/kosten?jaar=2026');
    expect(row?.notice).toBeUndefined();
  });

  it('has no row Investeerruimte for who has only the time', () => {
    const time = { year: 2026, time: { person_count: 3, free_fte: '1', months: [] } };
    expect(keys({ ...SOURCES, investment: time })).not.toContain('investment');
  });

  it('says that the money is withheld, without an amount', () => {
    const withheld = {
      year: 2026,
      money_withheld: { reason: 'few_targets', min_persons: 5 },
    };
    const item = moneyRows({ ...SOURCES, investment: withheld }).find(
      (entry) => entry.key === 'investment',
    );
    expect(item?.notice).toBe('Niet te tonen voor 2026: te weinig mensen hebben een target');
  });

  it('says what is wrong in the words of the row', () => {
    const fine = {
      ...SOURCES,
      steering: { ...STEERING, costs: { ...STEERING.costs!, uncovered_cents: 0 } },
      investment: {
        year: 2026,
        money: { ...INVESTMENT.money!, room_cents: 100, shortfall: false },
      },
    };
    expect(notices(fine).investment).toBe('€ 1 ruimte in 2026');
    expect(notices(fine).costs).toBe('Alles gedekt in 2026, 3 facturen zonder bijlage');
    const over = { ...SOURCES, overview: { ...OVERVIEW, figures_active: OVERRUN } };
    expect(notices(over).assignments).toBe('2 opdrachten, € 43.200 overschrijding in 2026');
  });

  it('says that billing is about now, with or without an amount', () => {
    expect(notices(SOURCES).billing).toMatch(/^Nu /);
    const none = { ...OVERVIEW, to_deliver_cents: 0, to_invoice_cents: 0 };
    expect(notices({ ...SOURCES, overview: none }).billing).toBe(
      'Nu niets aan te leveren of te factureren',
    );
    const both = { ...OVERVIEW, to_invoice_cents: 120000 };
    expect(notices({ ...SOURCES, overview: both }).billing).toBe(
      'Nu € 68.800 nog aan te leveren, € 1.200 nog te factureren',
    );
    expect(notices({ ...SOURCES, overview: both }).billing).not.toContain('2026');
  });

  it('says how offers stand without one waiting, and in the plural', () => {
    const pipeline = (count: number, total: number) => ({
      ...STEERING,
      pipeline: {
        scope: 'all' as const,
        waiting: [],
        statuses: [{ status: 'issued', count, total_cents: total }],
      },
    });
    expect(notices({ ...SOURCES, steering: pipeline(0, 0) }).potential).toBe(
      'Geen offerte uit 2026 wacht op akkoord',
    );
    expect(notices({ ...SOURCES, steering: pipeline(2, 100) }).potential).toBe(
      '€ 1, 2 offertes uit 2026 wachten op akkoord',
    );
  });

  it('never says Pijplijn', () => {
    expect(JSON.stringify(moneyRows(SOURCES)).toLowerCase()).not.toContain('pijplijn');
  });
});

describe('runningRows', () => {
  it('holds running work with amounts, in the chosen year', () => {
    expect(runningRows(OVERVIEW).map((item) => item.assignment_id)).toEqual(['a1', 'a2']);
  });

  it('leaves out a row whose amounts the reader may not see, not one that cannot be priced', () => {
    const rows = runningRows({
      year: 2026,
      rows: [
        row({ assignment_id: 'hidden', figures: null }),
        row({ assignment_id: 'broken', figures: null, pricing_error: 'Geen tarief' }),
      ],
    });
    expect(rows.map((item) => item.assignment_id)).toEqual(['broken']);
  });
});

const YEAR = currentReportYear();

describe('MoneyPage', () => {
  const routes = {
    '/api/reports/steering': STEERING,
    '/api/reports/investment': INVESTMENT,
    '/api/overview': OVERVIEW,
    '/api/costs': { items: [], total: 0, page: 1, page_size: 50, year: 2026, may_create: false },
  };

  it('is a page of rows, without a choice of year', async () => {
    mockApi(routes);
    const { container } = renderApp(<MoneyPage />, { path: '/geld' });
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Geld');
    expect(container.querySelectorAll('nldd-list-item')).toHaveLength(7);
    expect(container.querySelector('select')).toBeNull();
    expect(container.querySelector('nldd-toolbar')).toBeNull();
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(container.querySelector('.grip-tiles, .grip-tile')).toBeNull();
  });

  it('asks every source for the current year, and the cost list only without the block', async () => {
    const { calls } = mockApi(routes);
    const { container } = renderApp(<MoneyPage />, { path: '/geld' });
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(calls).toContain(`/api/reports/steering?year=${YEAR}`);
    expect(calls).toContain(`/api/reports/investment?year=${YEAR}`);
    expect(calls).toContain(`/api/overview?year=${YEAR}`);
    expect(calls.some((call) => call.startsWith('/api/costs'))).toBe(false);
  });

  it('keeps the row Kosten for a reader who may add a first item, without a notice', async () => {
    const { calls } = mockApi({
      ...routes,
      '/api/reports/steering': { ...STEERING, costs: undefined },
      '/api/costs': { items: [], total: 0, page: 1, page_size: 50, year: 2026, may_create: true },
    });
    const { container } = renderApp(<MoneyPage />, { path: '/geld' });
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    await waitFor(() => expect(container.querySelector('[text="Kosten"]')).not.toBeNull());
    expect(calls.some((call) => call.startsWith('/api/costs'))).toBe(true);
    expect(container.querySelectorAll('nldd-list-item')).toHaveLength(7);
  });

  it('shows the rows it has when one source fails', async () => {
    mockApi({ ...routes, '/api/reports/investment': undefined });
    const fetchMock = vi.mocked(fetch);
    const answer = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, init) =>
      String(input).startsWith('/api/reports/investment')
        ? Promise.resolve(
            new Response(JSON.stringify({ title: 'Fout', status: 500 }), {
              status: 500,
              headers: { 'Content-Type': 'application/problem+json' },
            }),
          )
        : answer(input, init),
    );
    const { container } = renderApp(<MoneyPage />, { path: '/geld' });
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(container.querySelectorAll('nldd-list-item')).toHaveLength(6);
  });

  it('says so to a reader without a single figure', async () => {
    mockApi({
      '/api/reports/steering': { year: 2026 },
      '/api/reports/investment': { year: 2026 },
      '/api/overview': { year: 2026, rows: [] },
      '/api/costs': { items: [], total: 0, page: 1, page_size: 1, year: 2026 },
    });
    const { container } = renderApp(<MoneyPage />, { path: '/geld' });
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog[data-state="empty"]')).toHaveAttribute(
        'text',
        'Er zijn voor jou geen cijfers',
      ),
    );
    expect(container.querySelector('nldd-list')).toBeNull();
  });
});

describe('Lopende opdrachten', () => {
  const routes = {
    '/api/overview': OVERVIEW,
    '/api/reports/steering': STEERING,
  };

  const cells = (container: HTMLElement) =>
    [...container.querySelectorAll('nldd-text-cell')].map((cell) => [
      plain(cell.getAttribute('text')),
      plain(cell.getAttribute('supporting-text')),
    ]);

  it('is one row per running assignment and a row with the total', async () => {
    mockApi(routes);
    const { container } = renderApp(<RunningAssignmentsPage />, {
      path: '/geld/opdrachten?jaar=2026',
    });
    const sheet = await screen.findByTestId('assignments-sheet');
    expect(sheet.querySelectorAll('nldd-table-row')).toHaveLength(4);
    expect(cells(container).map(([text]) => text)).toEqual(
      expect.arrayContaining([
        'Begroot',
        'Verwacht totaal',
        'Afwijking',
        'Uitputting',
        '**Samen**',
      ]),
    );
    expect(cells(container)).toContainEqual(['**€ 1.156.800**', '']);
    expect(cells(container)).toContainEqual(['**€ 124.500**', '10,8%, ruimte']);
    expect(cells(container)).toContainEqual(['**6,7%**', '€ 77.200 gerealiseerd']);
  });

  it('opens the landing of an assignment from its name', async () => {
    mockApi(routes);
    const { container } = renderApp(<RunningAssignmentsPage />, {
      path: '/geld/opdrachten?jaar=2026',
    });
    await screen.findByTestId('assignments-sheet');
    const links = [...container.querySelectorAll('nldd-table nldd-link')];
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/opdrachten/a1',
      '/opdrachten/a2',
    ]);
  });

  it('says on top which period it is, and who it is about', async () => {
    mockApi(routes);
    const { container } = renderApp(<RunningAssignmentsPage />, {
      path: '/geld/opdrachten?jaar=2026',
    });
    await screen.findByTestId('assignments-sheet');
    await waitFor(() =>
      expect(container.textContent).toContain(
        '2026. Van een opdracht over meer jaren tellen de maanden van dit jaar.',
      ),
    );
    expect(container.querySelector('nldd-toolbar select')).toHaveValue('2026');
    expect(container.textContent).toContain('2 opdrachten lopen niet in 2026 en staan hier niet.');
  });

  it('says "jouw opdrachten" for the own assignments', async () => {
    mockApi({ ...routes, '/api/reports/steering': OWN });
    const { container } = renderApp(<RunningAssignmentsPage />, {
      path: '/geld/opdrachten?jaar=2026',
    });
    await waitFor(() =>
      expect(container.textContent).toContain('2026, jouw opdrachten. Van een opdracht'),
    );
  });

  it('can show the whole duration', async () => {
    const { calls } = mockApi(routes);
    const { container } = renderApp(<RunningAssignmentsPage />, {
      path: '/geld/opdrachten?jaar=all',
    });
    await screen.findByTestId('assignments-sheet');
    expect(calls).toContain('/api/overview?year=all');
    await waitFor(() => expect(container.textContent).toContain('De hele looptijd.'));
    expect(container.querySelector('nldd-toolbar select')).toHaveValue('all');
  });

  it('says an overrun in words and in colour, and what cannot be computed', () => {
    const { container } = renderApp(
      <AssignmentsSheet
        rows={[
          row({ figures: OVERRUN }),
          row({ assignment_id: 'a2', figures: null, pricing_error: 'Geen tarief voor 2026' }),
        ]}
        total={OVERRUN}
        label="Lopende opdrachten, 2026"
        perRowStand
      />,
    );
    const over = [...container.querySelectorAll('nldd-text-cell')].find(
      (cell) => plain(cell.getAttribute('supporting-text')) === '-3,7%, overschrijding',
    );
    expect(plain(over?.getAttribute('text'))).toBe('€ 43.200');
    expect(over).toHaveAttribute('color', 'critical');
    expect(container.textContent).toContain('Geen tarief voor 2026');
    expect(
      [...container.querySelectorAll('nldd-text-cell')].some(
        (cell) => cell.getAttribute('text') === 'Niet berekend',
      ),
    ).toBe(true);
    expect(container.textContent).toContain('Voorbeeldministerie · Stand t/m');
  });

  it('says how far the rows are closed once, when they all stand the same', async () => {
    mockApi({
      ...routes,
      '/api/overview': { ...OVERVIEW, rows: [row({}), row({ assignment_id: 'a2' })] },
    });
    const { container } = renderApp(<RunningAssignmentsPage />, {
      path: '/geld/opdrachten?jaar=2026',
    });
    await screen.findByTestId('assignments-sheet');
    await waitFor(() => expect(container.textContent).toContain('(laatst afgesloten maand)'));
    expect(container.querySelector('nldd-table')?.textContent).not.toContain('Stand t/m');
  });
});

describe('Potentieel', () => {
  it('shows the offers that wait, under the word Potentieel', async () => {
    mockApi({
      '/api/reports/steering': {
        ...STEERING,
        pipeline: {
          ...STEERING.pipeline,
          waiting: [
            {
              quote_id: 'q1',
              assignment_id: 'a3',
              assignment_name: 'Opdracht Epsilon 2027',
              client_name: 'Voorbeelddienst',
              status: 'issued',
              total_cents: 43440000,
              issued_at: '2026-10-01',
              valid_until: '2026-11-30',
            },
          ],
        },
      },
    });
    const { container } = renderApp(<PotentialPage />, { path: '/geld/potentieel?jaar=2026' });
    await screen.findByTestId('potential');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Potentieel');
    expect(container.querySelector('nldd-table nldd-link')).toHaveAttribute(
      'href',
      '/opdrachten/a3',
    );
    expect(container.textContent?.toLowerCase()).not.toContain('pijplijn');
  });
});

const PERIOD = {
  key: '2026-Q1',
  label: 'eerste kwartaal 2026',
  span: '',
  state: 'to_close',
  months: [
    { month: '2026-01', label: 'januari 2026', state: 'closed' },
    { month: '2026-02', label: 'februari 2026', state: 'closed' },
    { month: '2026-03', label: 'maart 2026', state: 'to_close' },
  ],
  closed_cents: 6880000,
  last_step_at: null,
};

const billingOf = (periods: unknown[], over: object = {}) => ({
  assignments: [
    {
      assignment_id: 'a1',
      assignment_name: 'Opdracht Alfa 2026',
      client_name: 'Voorbeeldministerie',
      may_deliver: true,
      terms: { missing_details: [], names_on_specification: false },
      periods,
      ...over,
    },
  ],
  can_mail: false,
  reads_money: true,
});

const DELIVERY = {
  id: 'd1',
  reference: 'O-1/2026-Q1',
  period_key: '2026-Q1',
  total_cents: 6880000,
  via: 'self',
  recipient: null,
  delivered_at: '2026-04-02T10:00:00Z',
  delivered_by_name: 'Priya Product',
  has_document: true,
  mail_state: null,
  invoice_id: null,
  invoice_number: null,
  may_open: true,
};

describe('Factureren', () => {
  const page = (billing: object, overview: object = OVERVIEW, steering: object = STEERING) => {
    mockApi({
      '/api/billing': billing,
      '/api/overview': overview,
      '/api/reports/steering': steering,
    });
    return renderApp(<BillingPage />, { path: '/geld/factureren' });
  };

  it('says that the amount is real but not ready yet, in the words of the row on Geld', async () => {
    const { container } = page(billingOf([PERIOD]));
    await waitFor(() =>
      expect(plain(container.textContent)).toContain(
        'De € 68.800 die nog aan te leveren is, zit in perioden die nog niet helemaal zijn afgesloten.',
      ),
    );
    expect(container.textContent).toContain('Er staat nu niets klaar om aan te leveren.');
  });

  it('says it is about now, of all assignments or of the own', async () => {
    const lead = (container: HTMLElement) =>
      container.querySelector('[slot="header"] nldd-text')?.textContent;
    const all = page(billingOf([PERIOD]));
    await waitFor(() =>
      expect(lead(all.container)).toBe('Wat er nu openstaat op alle opdrachten, over alle jaren.'),
    );
    all.unmount();
    vi.unstubAllGlobals();
    const own = page(billingOf([PERIOD]), OVERVIEW, OWN);
    await waitFor(() =>
      expect(lead(own.container)).toBe('Wat er nu openstaat op jouw opdrachten, over alle jaren.'),
    );
    expect(own.container.querySelector('nldd-toolbar select')).toBeNull();
  });

  it('says nothing about an amount when nothing is open', async () => {
    const { container } = page(billingOf([]), { ...OVERVIEW, to_deliver_cents: 0 });
    await waitFor(() =>
      expect(container.textContent).toContain('Er staat nu niets klaar om aan te leveren.'),
    );
    expect(container.textContent).not.toContain('die nog aan te leveren is');
  });

  it('names the rest when only part of it is ready', async () => {
    const ready = { ...PERIOD, state: 'ready', to_deliver_cents: 3000000, closed_cents: 3000000 };
    const { container } = page({ ...billingOf([ready]), ready_cents: 3000000 });
    await waitFor(() =>
      expect(plain(container.textContent)).toContain(
        'In totaal is € 68.800 nog aan te leveren. De rest zit in perioden',
      ),
    );
    expect(plain(container.querySelector('nldd-card nldd-title')?.getAttribute('text'))).toBe(
      '1 periode is klaar: € 30.000',
    );
  });

  it('has the way back to Geld and fits three columns', async () => {
    const { container } = page(billingOf([PERIOD]));
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(
      [...container.querySelectorAll('nldd-link')].find(
        (link) => link.getAttribute('text') === 'Terug naar Geld',
      ),
    ).toHaveAttribute('href', '/geld');
    expect(container.querySelector('nldd-table')).toHaveAttribute(
      'columns',
      'minmax(220px,1.2fr) minmax(220px,1.4fr) 120px',
    );
  });

  it('opens the request from a delivered period', async () => {
    const delivered = {
      ...PERIOD,
      state: 'delivered',
      delivered_cents: 6880000,
      deliveries: [DELIVERY],
    };
    const { container } = page(billingOf([delivered]));
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-table nldd-link')).toHaveAttribute(
      'href',
      '/geld/factureren/d1',
    );
  });

  it('opens the assignment instead when the server says the reader may not open the request', async () => {
    const delivered = {
      ...PERIOD,
      state: 'delivered',
      delivered_cents: 6880000,
      deliveries: [{ ...DELIVERY, may_open: false }],
    };
    const { container } = page(billingOf([delivered], { may_deliver: true }));
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-table nldd-link')?.getAttribute('href')).toContain(
      '/opdrachten/a1/afsluiten',
    );
  });
});

describe('the way back from one thing', () => {
  const backLink = (container: HTMLElement, text: string) =>
    [...container.querySelectorAll('nldd-link')].find((link) => link.getAttribute('text') === text);

  it('leads from a delivery to Factureren', async () => {
    mockApi({
      '/api/billing/deliveries/d1': {
        id: 'd1',
        reference: 'O-1',
        assignment_name: 'Opdracht Alfa 2026',
        client_name: null,
        period_label: 'eerste kwartaal 2026',
        total_cents: 100,
        in_force_cents: 100,
        delivered_at: '2026-04-02T10:00:00Z',
        delivered_by_name: null,
        has_document: false,
        details: {},
        lines: [],
      },
    });
    const { container } = renderApp(
      <Routes>
        <Route path="/geld/factureren/:deliveryId" element={<DeliveryPage />} />
      </Routes>,
      { path: '/geld/factureren/d1' },
    );
    await screen.findByRole('heading', { level: 1, name: 'Factuurverzoek O-1' });
    expect(backLink(container, 'Terug naar Factureren')).toHaveAttribute(
      'href',
      '/geld/factureren',
    );
  });

  it('leads from a cost item to Kosten, with its year', async () => {
    mockApi({
      '/api/costs/c1': {
        id: 'c1',
        description: 'Hostingcontract',
        budgeted_cents: 100,
        forecast_cents: 100,
        actual_cents: 0,
        estimate_cents: 100,
        variance_cents: 0,
        covered_cents: 100,
        uncovered_cents: 0,
        pct_total: '100',
        uncovered_pct: '0',
        hidden_coverage_pct: '0',
        invoice_lines: [],
        coverages: [],
        may_edit: false,
      },
      '/api/costs/coverage-options': { items: [] },
    });
    const { container } = renderApp(
      <Routes>
        <Route path="/geld/kosten/:costItemId" element={<CostItemPage />} />
      </Routes>,
      { path: '/geld/kosten/c1?jaar=2026' },
    );
    await screen.findByRole('heading', { level: 1, name: 'Hostingcontract' });
    expect(backLink(container, 'Terug naar Kosten')).toHaveAttribute(
      'href',
      '/geld/kosten?jaar=2026',
    );
  });
});
