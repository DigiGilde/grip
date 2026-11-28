import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { InvestmentPage } from '@/features/money/InvestmentPage';
import { PotentialPage } from '@/features/money/PotentialPage';
import { TurnoverPage } from '@/features/money/TurnoverPage';
import { YearAccountPage } from '@/features/money/YearAccountPage';
import { renderApp } from '@/test/utils';
import { AssignmentReportContent } from './AssignmentReportPage';
import { YearAccountView } from './YearAccountView';

/** Answers every request with the body registered for the start of its path. */
function respond(routes: Record<string, unknown>, status = 200) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const key = Object.keys(routes).find((prefix) => url.startsWith(prefix));
    return Promise.resolve(
      new Response(JSON.stringify(key ? routes[key] : { title: 'Niet gevonden' }), {
        status: key ? status : 404,
        headers: {
          'Content-Type': key && status === 200 ? 'application/json' : 'application/problem+json',
        },
      }),
    );
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const MONTHS = Array.from(
  { length: 12 },
  (_, index) => `2026-${String(index + 1).padStart(2, '0')}`,
);

const TURNOVER = {
  scope: 'all',
  months: MONTHS.map((month, index) => ({
    month,
    realised_cents: index === 0 ? 3590000 : 0,
    forecast_cents: index === 0 ? 300000 : 9190000,
    verbal_cents: 0,
    pipeline_cents: 0,
  })),
  realised_cents: 3590000,
  forecast_cents: 101390000,
  verbal_cents: 0,
  pipeline_cents: 0,
  expected_cents: 104980000,
  figures: {
    budgeted_cents: 115680000,
    realised_cents: 3590000,
    planned_cents: 101390000,
    costs_cents: 1800000,
    expected_total_cents: 106780000,
    variance_cents: 8900000,
    variance_pct: '7.7',
    overrun: false,
    realised_total_cents: 3590000,
    realised_pct: '3.1',
  },
  unpriced_assignments: [],
};

const TOPICS = {
  omzet: { page: <TurnoverPage />, path: '/geld/omzet' },
  potentieel: { page: <PotentialPage />, path: '/geld/potentieel' },
  investeerruimte: { page: <InvestmentPage />, path: '/geld/investeerruimte' },
  jaarverantwoording: { page: <YearAccountPage />, path: '/geld/jaarverantwoording' },
};

function renderTopic(slug: keyof typeof TOPICS, year = '2026') {
  return renderApp(TOPICS[slug].page, { path: `${TOPICS[slug].path}?jaar=${year}` });
}

const cellTexts = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text') ?? '');

afterEach(() => vi.unstubAllGlobals());

describe('a topic of a report', () => {
  it('asks for the year in the address and offers the way back with it', async () => {
    const fetchMock = respond({ '/api/reports/steering': { year: 2025, turnover: TURNOVER } });
    const { container } = renderTopic('omzet', '2025');
    await screen.findByTestId('turnover');
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      '/api/reports/steering?year=2025',
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Omzet');
    const back = [...container.querySelectorAll('nldd-link')].find(
      (link) => link.getAttribute('text') === 'Terug naar Geld',
    );
    expect(back).toHaveAttribute('href', '/geld');
    expect(container.querySelector('nldd-toolbar select')).toHaveValue('2025');
  });

  it('shows one topic and nothing of the others', async () => {
    respond({
      '/api/reports/steering': {
        year: 2026,
        turnover: TURNOVER,
        costs: { scope: 'all', forecast_cents: 0, covered_cents: 0, uncovered_cents: 0, items: [] },
      },
    });
    renderTopic('omzet');
    await screen.findByTestId('turnover');
    for (const other of ['occupancy', 'potential', 'costs', 'billability']) {
      expect(screen.queryByTestId(other)).toBeNull();
    }
  });

  it('answers first, in the words of the assignment pages', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderTopic('omzet');
    const block = await screen.findByTestId('turnover');
    const figures = screen.getByLabelText('Omzet in het kort');
    expect(figures).toHaveTextContent('Verwacht totaal€ 1.067.800');
    expect(figures).toHaveTextContent('van € 1.156.800 begroot, afwijking € 89.000');
    expect(figures).toHaveTextContent('uitputting 3,1% van de begroting');
    expect(figures).toHaveTextContent('Nog gepland');
    expect(block).not.toHaveTextContent('Prognose');
    expect(block).not.toHaveTextContent('Beschikbaar');
    // The chart is the quick read; the table is there, behind a disclosure.
    expect(screen.getByRole('group', { name: 'Omzet per maand in 2026' })).toBeInTheDocument();
    const disclosure = block.querySelector('details')!;
    expect(disclosure).not.toHaveAttribute('open');
    expect(disclosure.querySelector('summary')).toHaveTextContent('Bedragen per maand als tabel');
    expect(disclosure.querySelector('nldd-table')).toHaveAttribute(
      'accessible-label',
      'Omzet per maand in 2026',
    );
    const texts = cellTexts(container);
    expect(texts).toContain('januari 2026');
    expect(texts.some((text) => text.includes('35.900'))).toBe(true);
    // No pipeline and no verbal agreement in the data, so no column for them.
    expect(texts).not.toContain('Nog niet afgesproken');
    expect(texts).not.toContain('Waarvan mondeling akkoord');
    expect(block).toHaveTextContent('Alle opdrachten in 2026.');
  });

  it('calls out a year that is expected to end above its budget', async () => {
    respond({
      '/api/reports/steering': {
        year: 2026,
        turnover: {
          ...TURNOVER,
          figures: { ...TURNOVER.figures, variance_cents: -500000, overrun: true },
        },
      },
    });
    renderTopic('omzet');
    await screen.findByTestId('turnover');
    expect(screen.getByLabelText('Omzet in het kort')).toHaveTextContent('Boven de begroting');
  });

  it('shows how much of what is planned rests on a verbal agreement', async () => {
    respond({
      '/api/reports/steering': {
        year: 2026,
        turnover: { ...TURNOVER, verbal_cents: 1800000, pipeline_cents: 2500000 },
      },
    });
    const { container } = renderTopic('omzet');
    await screen.findByTestId('turnover');
    expect(screen.getByLabelText('Omzet in het kort')).toHaveTextContent(
      /waarvan € 18\.000 op mondeling akkoord/,
    );
    const texts = cellTexts(container);
    expect(texts).toContain('Waarvan mondeling akkoord');
    expect(texts).toContain('Nog niet afgesproken');
  });

  it('keeps the total bold', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderTopic('omzet');
    await screen.findByTestId('turnover');
    expect(cellTexts(container).some((text) => text.startsWith('**€'))).toBe(true);
  });

  it('says under the turnover that it misses what another organisation keeps', async () => {
    respond({
      '/api/reports/steering': {
        year: 2026,
        turnover: { ...TURNOVER, incomplete_by: ['Voorbeeldgilde', 'Voorbeeldwerkplaats'] },
      },
    });
    renderTopic('omzet');
    await screen.findByTestId('turnover');
    expect(screen.getByLabelText('Omzet in het kort').nextElementSibling).toHaveTextContent(
      'Onvolledig: niet alles is op te halen bij Voorbeeldgilde en Voorbeeldwerkplaats',
    );
  });

  it('says nothing about completeness when nothing is missing', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderTopic('omzet');
    await screen.findByTestId('turnover');
    expect(container.innerHTML).not.toContain('Onvolledig');
  });

  it('names what was left out of the turnover', async () => {
    respond({
      '/api/reports/steering': {
        year: 2026,
        turnover: { ...TURNOVER, unpriced_assignments: ['Opdracht Beta'] },
      },
    });
    const { container } = renderTopic('omzet');
    await screen.findByTestId('turnover');
    expect(container.querySelector('nldd-banner')?.getAttribute('text')).toContain('Opdracht Beta');
  });

  it('says there is nothing to show when the block is not in the answer', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderTopic('potentieel');
    await waitFor(() =>
      expect(container.textContent).toContain('Voor 2026 is hier niets te tonen.'),
    );
    expect(screen.queryByTestId('turnover')).toBeNull();
  });

  it('shows the problem the API reports', async () => {
    respond({ '/api/reports/steering': { title: 'Geen toegang', detail: 'Dat mag niet.' } }, 403);
    const { container } = renderTopic('omzet');
    // A refusal reads the same on every screen: no access, and nothing else.
    await waitFor(() =>
      expect(container.querySelector('[data-state="no-access"]')?.textContent).toContain(
        'Je hebt hier geen toegang',
      ),
    );
  });

  it('holds the year account as a view of its own', async () => {
    const fetchMock = respond({
      '/api/reports/year-account': { year: 2026, scope: 'all', rows: [ROW] },
    });
    renderTopic('jaarverantwoording');
    await screen.findByTestId('year-account');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Jaarverantwoording');
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      '/api/reports/year-account?year=2026',
    );
  });
});

const ROW = {
  assignment_id: 'a1',
  uri: 'https://grip.example/id/opdracht/a1',
  name: 'Opdracht Alfa',
  kind: 'external',
  client_name: 'Voorbeeldministerie',
  status: 'in_progress',
  start_date: '2026-07-01',
  end_date: '2027-06-30',
};

const AMOUNTS = {
  agreed_cents: 15300000,
  budgeted_cents: 15300000,
  realised_cents: 2190000,
  forecast_cents: 12750000,
  costs_cents: 450000,
  delivered_cents: 2190000,
  to_deliver_cents: 0,
  invoiced_cents: 0,
  to_invoice_cents: 2190000,
  difference_cents: 13110000,
  pricing_error: null,
};

describe('YearAccountView', () => {
  it('links each assignment and offers the CSV', async () => {
    respond({
      '/api/reports/year-account': {
        year: 2026,
        scope: 'all',
        rows: [{ ...ROW, ...AMOUNTS }],
        totals: { ...AMOUNTS },
      },
    });
    const { container } = renderApp(<YearAccountView year="2026" />);
    await screen.findByTestId('year-account');
    const links = [...container.querySelectorAll('nldd-link')].map((link) =>
      link.getAttribute('href'),
    );
    expect(links).toContain('/opdrachten/a1/rapport');
    expect(links).toContain('/api/reports/year-account/csv?year=2026');
    const texts = cellTexts(container);
    expect(texts).toContain('Afgesproken');
    expect(texts.some((text) => text.includes('153.000'))).toBe(true);
    expect(container.querySelector('nldd-badge')).toHaveAttribute('text', 'In uitvoering');
    const figures = screen.getByLabelText('Jaarverantwoording in het kort');
    expect(figures).toHaveTextContent('Afgesproken€ 153.000');
    expect(figures).toHaveTextContent('€ 21.900 is aangeleverd');
    expect(figures).not.toHaveTextContent('nog niet aangeleverd');
    // Delivered is not invoiced: until an invoice is recorded it is all still to invoice.
    expect(figures).toHaveTextContent('Nog te factureren€ 21.900');
    expect(figures).toHaveTextContent('Aangeleverd, geen factuur vastgelegd');
    expect(figures).toHaveTextContent('€ 0 is gefactureerd');
    expect(texts).toContain('Gefactureerd');
    expect(texts).toContain('Nog te factureren');
    expect(texts).toContain('Aangeleverd');
    expect(texts).toContain('Nog aan te leveren');
    expect(texts).toContain('Nog gepland');
    expect(texts).not.toContain('Prognose');
  });

  it('calls out what is realised and not delivered yet', async () => {
    const open = { ...AMOUNTS, delivered_cents: 0, to_deliver_cents: 2190000 };
    respond({
      '/api/reports/year-account': {
        year: 2026,
        scope: 'all',
        rows: [{ ...ROW, ...open }],
        totals: { ...open },
      },
    });
    const { container } = renderApp(<YearAccountView year="2026" />);
    await screen.findByTestId('year-account');
    expect(screen.getByLabelText('Jaarverantwoording in het kort')).toHaveTextContent(
      'Gerealiseerde inzet, nog niet aangeleverd',
    );
    expect(
      container.querySelector('nldd-text-cell[supporting-text="Nog aan te leveren"]'),
    ).not.toBeNull();
  });

  it('shows no amount columns and no CSV to a reader who got no amounts', async () => {
    respond({ '/api/reports/year-account': { year: 2026, scope: 'all', rows: [ROW] } });
    const { container } = renderApp(<YearAccountView year="2026" />);
    await screen.findByTestId('year-account');
    expect(cellTexts(container)).not.toContain('Afgesproken');
    const links = [...container.querySelectorAll('nldd-link')].map((link) =>
      link.getAttribute('href'),
    );
    expect(links).toEqual(['/opdrachten/a1']);
  });

  it('opens the report of a row with amounts and the landing of a row without', async () => {
    respond({
      '/api/reports/year-account': {
        year: 2026,
        scope: 'all',
        rows: [
          { ...ROW, ...AMOUNTS, status: 'completed' },
          { ...ROW, assignment_id: 'a2', status: 'completed' },
          { ...ROW, ...AMOUNTS, assignment_id: 'a3', status: 'accounted' },
          { ...ROW, ...AMOUNTS, assignment_id: 'a4', status: 'in_progress' },
        ],
        totals: AMOUNTS,
      },
    });
    const { container } = renderApp(<YearAccountView year="2026" />);
    await screen.findByTestId('year-account');
    expect(
      [...container.querySelectorAll('nldd-table nldd-link')].map((link) =>
        link.getAttribute('href'),
      ),
    ).toEqual([
      '/opdrachten/a1/rapport',
      '/opdrachten/a2',
      '/opdrachten/a3/rapport',
      '/opdrachten/a4/rapport',
    ]);
  });

  it('says that an assignment has no agreement instead of showing zero', async () => {
    respond({
      '/api/reports/year-account': {
        year: 2026,
        scope: 'own',
        rows: [{ ...ROW, ...AMOUNTS, agreed_cents: null, difference_cents: null }],
        totals: { ...AMOUNTS, agreed_cents: 0 },
      },
    });
    const { container } = renderApp(<YearAccountView year="2026" />);
    const block = await screen.findByTestId('year-account');
    expect(
      container.querySelector('nldd-text-cell[supporting-text="Geen akkoord"]'),
    ).not.toBeNull();
    expect(block).toHaveTextContent('De opdrachten waar je bij betrokken bent');
  });

  it('has an empty state', async () => {
    respond({ '/api/reports/year-account': { year: 2025, scope: 'own', rows: [] } });
    const { container } = renderApp(<YearAccountView year="2025" />);
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute(
        'text',
        'Er zijn geen opdrachten in 2025',
      ),
    );
  });
});

const TOTALS = {
  budgeted_cents: 31365000,
  realised_cents: 2190000,
  forecast_cents: 28815000,
  coverage_cents: 450000,
  used_cents: 31455000,
  available_cents: -90000,
  overrun: true,
};

const REPORT = {
  assignment_id: 'a1',
  uri: 'https://grip.example/id/opdracht/a1',
  name: 'Opdracht Alfa',
  kind: 'external',
  status: 'in_progress',
  client_name: 'Voorbeeldministerie',
  contractor_name: null,
  start_date: '2026-07-01',
  end_date: '2027-06-30',
  context_refs: [],
  audience: 'client',
  generated_on: '2026-10-08',
  months_total: 12,
  months_closed: 1,
  status_history: [
    { occurred_at: '2026-06-01T10:00:00Z', old_status: null, new_status: 'draft', reason: null },
    {
      occurred_at: '2026-06-20T10:00:00Z',
      old_status: 'draft',
      new_status: 'quoted',
      reason: null,
    },
  ],
  final_report: null,
  months: [],
  lines: [{ budget_line_id: 'l1', description: 'Productmanager', kind: 'personnel' }],
};

const FINANCIAL = {
  agreed: {
    quote_id: 'q1',
    quote_uri: 'https://grip.example/id/offerte/q1',
    issued_at: '2026-06-20T10:00:00Z',
    accepted_at: '2026-06-25T10:00:00Z',
    form: 'signing_link',
    total_cents: 31365000,
    lines: [
      {
        description: 'Productmanager',
        kind: 'personnel',
        role: 'Productmanager',
        fte: '1',
        start_date: '2026-07-01',
        end_date: '2027-06-30',
        amount_cents: 22140000,
      },
    ],
    subtotals: [
      { year: 2026, amount_cents: 15300000 },
      { year: 2027, amount_cents: 16065000 },
    ],
  },
  quoted_amount_cents: null,
  totals: TOTALS,
  pricing_error: null,
  periods: [{ year: 2026, totals: TOTALS, pricing_error: null }],
  lines: [
    {
      budget_line_id: 'l1',
      description: 'Productmanager',
      kind: 'personnel',
      totals: TOTALS,
      pricing_error: null,
    },
  ],
  costs: [
    {
      cost_item_id: 'c1',
      description: 'Hostingcontract',
      budget_line_description: 'Productmanager',
      pct: '30',
      amount_cents: 450000,
    },
  ],
};

function renderReport() {
  return renderApp(<AssignmentReportContent assignmentId="a1" />, {
    path: '/opdrachten/a1/rapport',
  });
}

describe('AssignmentReportPage', () => {
  it('asks for the client version first and links to its printable page', async () => {
    const fetchMock = respond({ '/api/reports/assignments/a1': { ...REPORT, ...FINANCIAL } });
    const { container } = renderReport();
    await screen.findByTestId('agreed');
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      '/api/reports/assignments/a1?audience=client',
    );
    const links = [...container.querySelectorAll('nldd-link')].map((link) =>
      link.getAttribute('href'),
    );
    expect(links).toContain('/api/reports/assignments/a1/document?audience=client');
    expect(links).not.toContain('/opdrachten/a1');
    expect(screen.queryByTestId('staffing')).toBeNull();
  });

  it('shows agreed, delivered and cost', async () => {
    respond({ '/api/reports/assignments/a1': { ...REPORT, ...FINANCIAL } });
    const { container } = renderReport();
    const agreed = await screen.findByTestId('agreed');
    expect(agreed).toHaveTextContent('Akkoord op 25 jun 2026, via een tekenlink.');
    const texts = cellTexts(container);
    expect(texts).toContain('Subtotaal 2026');
    expect(texts.some((text) => text.includes('313.650'))).toBe(true);
    expect(screen.getByTestId('delivered')).toHaveTextContent(
      'Van de 12 maanden van de opdracht zijn er 1 afgesloten',
    );
    expect(texts).toContain('Offerte gemaakt');
    expect(screen.getByTestId('cost')).toBeInTheDocument();
    expect(texts).toContain('Hostingcontract');
    // An overrun is said in words, in the table and in the figures on top.
    expect(
      container.querySelector('nldd-text-cell[supporting-text="Overschrijding"]'),
    ).not.toBeNull();
    const figures = screen.getByLabelText('De opdracht in het kort');
    expect(figures).toHaveTextContent('Afgesproken€ 313.650');
    expect(figures).toHaveTextContent('Overschrijding van de begroting');
  });

  it('says on a total that it misses what another organisation keeps', async () => {
    const incomplete = { ...TOTALS, incomplete_by: ['Voorbeeldgilde'] };
    respond({
      '/api/reports/assignments/a1': {
        ...REPORT,
        ...FINANCIAL,
        totals: incomplete,
        periods: [{ year: 2026, totals: incomplete, pricing_error: null }],
      },
    });
    const { container } = renderReport();
    await screen.findByTestId('cost');
    const notes = [...container.querySelectorAll('nldd-text-cell')].map((cell) =>
      cell.getAttribute('supporting-text'),
    );
    expect(
      notes.filter((note) => note === 'Onvolledig: niet alles is op te halen bij Voorbeeldgilde'),
    ).toHaveLength(2);
  });

  it('leaves out every money section for a reader who got no amounts', async () => {
    respond({ '/api/reports/assignments/a1': REPORT });
    renderReport();
    await screen.findByTestId('delivered');
    expect(screen.queryByTestId('agreed')).toBeNull();
    expect(screen.queryByTestId('cost')).toBeNull();
    expect(screen.queryByLabelText('De opdracht in het kort')).toBeNull();
  });

  it('says so when the assignment is not for the reader', async () => {
    respond({});
    const { container } = renderReport();
    await waitFor(() =>
      expect(container.querySelector('[data-state="not-found"]')?.textContent).toContain(
        'Deze opdracht is niet gevonden',
      ),
    );
  });
});

const MONEY = {
  expected_cents: 101430000,
  realised_cents: 6880000,
  planned_cents: 94550000,
  verbal_cents: 0,
  pipeline_cents: 43440000,
  target_cents: 69750000,
  target_person_count: 9,
  uncovered_cents: 300000,
  internal_budget_cents: 4100000,
  internal_count: 1,
  room_cents: 27280000,
  shortfall: false,
  room_with_pipeline_cents: 70720000,
  months: MONTHS.map((month, index) => ({
    month,
    realised_cents: index === 0 ? 3590000 : 0,
    planned_cents: 7900000,
    target_cents: 5812500,
    turnover_minus_target_cents: index === 0 ? 5677500 : 2087500,
  })),
  unpriced_assignments: [],
};

const TIME = {
  person_count: 13,
  free_fte: '33.5',
  value_cents: 45000000,
  months: ['2026-10', '2026-11', '2026-12', '2027-01'].map((month, index) => ({
    month,
    available_fte: '13',
    free_fte: ['7', '7', '7', '12.5'][index],
    value_cents: [9400000, 9400000, 9400000, 16800000][index],
    unvalued_count: 0,
  })),
};

function renderInvestment(body: unknown) {
  respond({ '/api/reports/investment': body });
  return renderTopic('investeerruimte');
}

describe('Investeerruimte', () => {
  it('shows the money reading as a derivation that adds up to the figure', async () => {
    renderInvestment({ year: 2026, money: MONEY, time: TIME });
    const table = await screen.findByTestId('investment-money');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Investeerruimte');
    const rows = [...table.querySelectorAll('tr')].map((row) => [
      row.querySelector('a')?.textContent ?? row.querySelector('th')?.textContent,
      row.querySelector('td')?.textContent?.replace(/\s/g, ' '),
    ]);
    expect(rows).toEqual([
      ['Verwachte omzet van externe opdrachten', '€ 1.014.300'],
      ['Declarabiliteitstargets', '− € 697.500'],
      ['Ongedekte kosten', '− € 3.000'],
      ['Begroot voor interne opdrachten', '− € 41.000'],
      ['Investeerruimte', '€ 272.800'],
      ['Als het potentieel doorgaat', '€ 707.200'],
    ]);
    // Realised to date and still expected are told apart.
    expect(table).toHaveTextContent('€ 68.800 gerealiseerde inzet, € 945.500 nog gepland');
    expect(table).toHaveTextContent('wat 9 mensen samen moeten binnenbrengen');
    expect(table).toHaveTextContent('telt niet mee');
  });

  it('makes every line the way into the view that explains it', async () => {
    renderInvestment({ year: 2026, money: MONEY });
    const table = await screen.findByTestId('investment-money');
    expect([...table.querySelectorAll('a')].map((link) => link.getAttribute('href'))).toEqual([
      '/geld/omzet?jaar=2026',
      '/mensen/declarabiliteit?jaar=2026',
      '/geld/kosten?jaar=2026',
      '/geld/jaarverantwoording?jaar=2026',
      '/geld/potentieel?jaar=2026',
    ]);
  });

  it('says plainly when it is a shortfall', async () => {
    renderInvestment({
      year: 2026,
      money: { ...MONEY, room_cents: -5550000, shortfall: true, pipeline_cents: 0 },
    });
    const table = await screen.findByTestId('investment-money');
    const total = table.querySelector('.grip-derivation__total')!;
    expect(total.querySelector('th')).toHaveTextContent('Tekort');
    // The word carries the sign; the amount is written without a minus.
    expect(screen.getByTestId('investment-room').textContent?.replace(/\s/g, ' ')).toBe('€ 55.500');
    expect(table).not.toHaveTextContent('Als het potentieel doorgaat');
  });

  it('says in one quiet line what each reading counts', async () => {
    renderInvestment({ year: 2026, money: MONEY, time: TIME });
    const block = await screen.findByTestId('investment');
    const quiet = [...block.querySelectorAll('nldd-text[size="sm"]')].map(
      (text) => text.textContent ?? '',
    );
    expect(quiet.some((text) => text.includes('Voorlopige definitie'))).toBe(true);
    expect(quiet.some((text) => text.includes('min wat de mensen volgens hun target'))).toBe(true);
  });

  it('leaves the time out: that reading is at Mensen', async () => {
    const { container } = renderInvestment({ year: 2026, money: MONEY, time: TIME });
    await screen.findByTestId('investment-money');
    expect(screen.queryByTestId('investment-time')).toBeNull();
    expect(cellTexts(container)).not.toContain('Vrij (FTE)');
  });

  it('is not for a planner who has only the time', async () => {
    const { container } = renderInvestment({ year: 2026, time: TIME });
    await waitFor(() => expect(container.textContent).toContain('Je hebt hier geen toegang'));
    expect(container.querySelector('[data-state="no-access"]')).not.toBeNull();
    expect(container.textContent).not.toContain('er voor jou niet');
    expect(container.textContent).not.toContain('FTE');
  });

  it('leaves the targets per month out for a reader who may not see them', async () => {
    const months = MONEY.months.map((month) => ({
      ...month,
      target_cents: null,
      turnover_minus_target_cents: null,
    }));
    const { container } = renderInvestment({ year: 2026, money: { ...MONEY, months } });
    await screen.findByTestId('investment-money');
    const texts = cellTexts(container);
    expect(texts).toContain('Nog gepland');
    expect(texts).not.toContain('Targets');
    expect(texts).not.toContain('Omzet min targets');
    // Nor does the line lead to a page that is not for this reader.
    const table = screen.getByTestId('investment-money');
    expect(table).toHaveTextContent('Declarabiliteitstargets');
    expect(table.querySelector('a[href^="/mensen"]')).toBeNull();
  });

  it('says why the money reading is not shown when it would give a target away', async () => {
    renderInvestment({ year: 2026, money_withheld: { reason: 'few_targets', min_persons: 5 } });
    const notice = await screen.findByTestId('investment-withheld');
    expect(notice).toHaveAttribute('text', 'De investeerruimte in geld is niet te tonen');
    expect(notice.getAttribute('supporting-text')).toContain(
      'Minder dan 5 mensen hebben een target',
    );
    expect(screen.queryByTestId('investment-money')).toBeNull();
  });

  it('has an answer for a reader it is not for', async () => {
    const { container } = renderInvestment({ year: 2026 });
    await waitFor(() => expect(container.textContent).toContain('Je hebt hier geen toegang'));
    expect(container.querySelector('[data-state="no-access"]')).not.toBeNull();
    expect(container.textContent).not.toContain('er voor jou niet');
  });
});
