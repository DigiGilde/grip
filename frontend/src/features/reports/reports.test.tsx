import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import { AssignmentReportPage } from './AssignmentReportPage';
import { ReportsPage } from './ReportsPage';
import { landingTiles } from './tiles';
import { ReportTopicPage } from './ReportTopicPage';
import { YearAccountView } from './YearAccountView';
import { currentReportYear } from './years';

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

const MONTHS = Array.from({ length: 12 }, (_, index) => `2026-${String(index + 1).padStart(2, '0')}`);

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

function renderTopic(slug: string, year = '2026') {
  return renderApp(
    <Routes>
      <Route path={PATHS.reportTopic} element={<ReportTopicPage />} />
    </Routes>,
    { path: `/rapportage/${slug}?jaar=${year}` },
  );
}

const cellTexts = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text') ?? '');

afterEach(() => vi.unstubAllGlobals());

describe('a topic of Rapportage', () => {
  it('asks for the year in the address and offers the way back with it', async () => {
    const fetchMock = respond({ '/api/reports/steering': { year: 2025, turnover: TURNOVER } });
    const { container } = renderTopic('omzet', '2025');
    await screen.findByTestId('turnover');
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      '/api/reports/steering?year=2025',
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Omzet');
    const back = [...container.querySelectorAll('nldd-link')].find(
      (link) => link.getAttribute('text') === 'Terug naar Rapportage',
    );
    expect(back).toHaveAttribute('href', '/rapportage?jaar=2025');
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
    for (const other of ['occupancy', 'pipeline', 'costs', 'billability', 'open-roles']) {
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

  it('mutes a zero and keeps the total bold', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderTopic('omzet');
    await screen.findByTestId('turnover');
    const zero = [...container.querySelectorAll('nldd-text-cell')].find((cell) =>
      /^€\s0$/.test(cell.getAttribute('text') ?? ''),
    );
    expect(zero).toHaveAttribute('color', 'secondary');
    expect(cellTexts(container).some((text) => text.startsWith('**€'))).toBe(true);
  });

  it('calls out uncovered costs', async () => {
    respond({ '/api/reports/steering': { year: 2026, costs: COSTS } });
    renderTopic('kosten');
    await screen.findByTestId('costs');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Kosten');
    expect(screen.getByLabelText('Kosten in het kort')).toHaveTextContent(
      'Geen begrotingsregel dekt dit',
    );
  });

  it('puts people below target first and says when there is no target', async () => {
    respond({ '/api/reports/steering': { year: 2026, billability: BILLABILITY } });
    const { container } = renderTopic('declarabiliteit');
    await screen.findByTestId('billability');
    const figures = screen.getByLabelText('Declarabiliteit in het kort');
    expect(figures).toHaveTextContent('Verwacht onder target1 persoon');
    expect(figures).toHaveTextContent('Haalt het target niet');
    const names = cellTexts(container).filter((text) =>
      ['Mila Medewerker', 'Cas Collega'].includes(text),
    );
    expect(names).toEqual(['Mila Medewerker', 'Cas Collega']);
    expect(cellTexts(container)).toContain('Geen target');
    expect(
      container.querySelector('nldd-text-cell[supporting-text="Onder target"]'),
    ).toHaveAttribute('color', 'critical');
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

  it('says so when the topic is not for the reader', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderTopic('declarabiliteit');
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute(
        'text',
        'Dit onderdeel is er voor jou niet',
      ),
    );
    expect(screen.queryByTestId('turnover')).toBeNull();
  });

  it('has an answer for an address that is no topic', () => {
    respond({});
    const { container } = renderTopic('bestaat-niet');
    expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute(
      'text',
      'Deze rapportage bestaat niet',
    );
  });

  it('shows the problem the API reports', async () => {
    respond({ '/api/reports/steering': { title: 'Geen toegang', detail: 'Dat mag niet.' } }, 403);
    const { container } = renderTopic('omzet');
    await waitFor(() =>
      expect(container.querySelector('nldd-banner')).toHaveAttribute('text', 'Dat mag niet.'),
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

const COSTS = {
  scope: 'all',
  forecast_cents: 2100000,
  covered_cents: 1800000,
  uncovered_cents: 300000,
  items: [
    {
      cost_item_id: 'c1',
      description: 'Hostingcontract',
      forecast_cents: 2100000,
      covered_cents: 1800000,
      uncovered_cents: 300000,
      pct_total: '80',
    },
  ],
};

const BILLABILITY = {
  scope: 'own',
  target_cents: 19440000,
  realised_cents: 1440000,
  forecast_cents: 9000000,
  realisation_cents: 10440000,
  with_target_count: 1,
  below_target_count: 1,
  persons: [
    {
      person_id: 'p2',
      person_name: 'Cas Collega',
      year: 2026,
      target_pct: null,
      target_cents: null,
      realised_cents: 750000,
      forecast_cents: 3750000,
      realisation_cents: 4500000,
      unavailable_reason: null,
    },
    {
      person_id: 'p1',
      person_name: 'Mila Medewerker',
      year: 2026,
      target_pct: '90',
      target_cents: 19440000,
      realised_cents: 1440000,
      forecast_cents: 9000000,
      realisation_cents: 10440000,
      unavailable_reason: null,
    },
  ],
};

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
  it('links each assignment to its report and offers the CSV', async () => {
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
    expect(links).toContain('/rapportage/opdrachten/a1');
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
      'Gerealiseerd, nog niet aangeleverd',
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
    expect(links).toEqual(['/rapportage/opdrachten/a1']);
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
    expect(container.querySelector('nldd-text-cell[supporting-text="Geen akkoord"]')).not.toBeNull();
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
    { occurred_at: '2026-06-20T10:00:00Z', old_status: 'draft', new_status: 'quoted', reason: null },
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
  return renderApp(
    <Routes>
      <Route path={PATHS.reportAssignment} element={<AssignmentReportPage />} />
    </Routes>,
    { path: '/rapportage/opdrachten/a1' },
  );
}

describe('AssignmentReportPage', () => {
  it('asks for the client version first and links to its printable page', async () => {
    const fetchMock = respond({ '/api/reports/assignments/a1': { ...REPORT, ...FINANCIAL } });
    const { container } = renderReport();
    await screen.findByTestId('agreed');
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      '/api/reports/assignments/a1?audience=client',
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Rapportage Opdracht Alfa');
    const links = [...container.querySelectorAll('nldd-link')].map((link) =>
      link.getAttribute('href'),
    );
    expect(links).toContain('/api/reports/assignments/a1/document?audience=client');
    expect(links).toContain('/rapportage');
    expect(links).toContain('/opdrachten/a1');
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
    expect(texts).toContain('Offerte uitgegeven');
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
      expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute(
        'text',
        'Deze opdracht is niet gevonden',
      ),
    );
  });
});

const OCCUPANCY_SUMMARY = {
  scope: 'all',
  summary: {
    person_count: 13,
    average_pct: '42.4',
    over_count: 2,
    over_months: ['2026-09'],
    current_month: '2026-10',
    window: ['2026-10', '2026-11', '2026-12', '2027-01'].map((month, index) => ({
      month,
      allocated_fte: '6',
      tentative_fte: '0',
      available_fte: '13',
      free_fte: ['7', '7', '7.5', '12.5'][index],
      pct: '46.2',
      under: 6,
      full: 5,
      over: 2,
    })),
    idle_count: 6,
  },
  months: [],
  persons: [],
  not_deployable: [],
};

const OPEN_ROLES = {
  scope: 'all',
  unfilled_fte: '4.7',
  roles: [
    {
      assignment_id: 'a1',
      assignment_name: 'Opdracht Alfa',
      budget_line_id: 'l1',
      description: 'Ontwerper',
      unfilled_fte: '0.6',
      start_date: null,
      end_date: null,
      vacancy_status: null,
    },
  ],
};

const PIPELINE = {
  scope: 'all',
  statuses: [
    { status: 'issued', count: 2, total_cents: 43440000 },
    { status: 'accepted', count: 3, total_cents: 111290000 },
  ],
  waiting: [],
};

describe('landingTiles', () => {
  it('gives one figure per block the reader got, with a line of context', () => {
    const tiles = landingTiles({
      year: 2026,
      turnover: TURNOVER,
      occupancy: OCCUPANCY_SUMMARY,
      pipeline: PIPELINE,
      costs: COSTS,
      billability: BILLABILITY,
      open_roles: OPEN_ROLES,
    } as never);
    // The formatter writes a non-breaking space after the euro sign.
    const plain = (text: string | undefined) => text?.replace(/\s/g, ' ');
    expect(tiles.map((tile) => [tile.topic, plain(tile.value)])).toEqual([
      ['omzet', '€ 1.067.800'],
      ['bezetting', '46,2%'],
      ['pijplijn', '€ 434.400'],
      ['kosten', '€ 3.000'],
      ['declarabiliteit', '1 persoon'],
      ['open-rollen', '4,7 FTE'],
    ]);
    const byTopic = Object.fromEntries(tiles.map((tile) => [tile.topic, tile]));
    expect(plain(byTopic.omzet?.context)).toBe('van € 1.156.800 begroot, € 35.900 gerealiseerd');
    expect(byTopic.bezetting?.label).toBe('Bezetting in oktober 2026');
    expect(plain(byTopic.bezetting?.context)).toBe('vrij: nov 7, dec 7,5, jan 12,5 FTE');
    expect(byTopic.pijplijn?.context).toBe('2 offertes');
  });

  it('signals only what needs attention', () => {
    const tiles = landingTiles({
      year: 2026,
      turnover: TURNOVER,
      occupancy: OCCUPANCY_SUMMARY,
      pipeline: PIPELINE,
      costs: { ...COSTS, uncovered_cents: 0 },
      billability: { ...BILLABILITY, below_target_count: 0 },
      open_roles: OPEN_ROLES,
    } as never);
    const attention = Object.fromEntries(tiles.map((tile) => [tile.topic, tile.attention]));
    expect(attention).toEqual({
      omzet: undefined,
      bezetting: '2 mensen boven 100%',
      pijplijn: undefined,
      kosten: undefined,
      declarabiliteit: undefined,
      'open-rollen': '1 rol zonder vacature',
    });
  });

  it('has no tile for a block the reader may not see', () => {
    // What a planner gets: occupancy and open roles, nothing with money.
    const tiles = landingTiles({
      year: 2026,
      occupancy: OCCUPANCY_SUMMARY,
      open_roles: OPEN_ROLES,
    } as never);
    expect(tiles.map((tile) => tile.topic)).toEqual(['bezetting', 'open-rollen']);
    expect(landingTiles({ year: 2026 })).toEqual([]);
  });
});

describe('ReportsPage', () => {
  it('opens on the headline figures of the current year and nothing else', async () => {
    const fetchMock = respond({
      '/api/reports/steering': { year: 2026, turnover: TURNOVER, costs: COSTS },
    });
    const { container } = renderApp(<ReportsPage />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Rapportage');
    const list = await screen.findByRole('list', { name: `Kerncijfers ${currentReportYear()}` });
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      `/api/reports/steering?year=${currentReportYear()}`,
    );
    expect(list.querySelectorAll('li')).toHaveLength(2);
    // No table, no chart, no heat map on the landing view.
    expect(container.querySelector('nldd-table, table, svg, figure')).toBeNull();
    expect(container.querySelector('nldd-toolbar select')).toHaveValue(currentReportYear());
  });

  it('makes each tile the way into its own view, with the year', async () => {
    respond({ '/api/reports/steering': { year: 2025, turnover: TURNOVER, costs: COSTS } });
    renderApp(<ReportsPage />, { path: '/rapportage?jaar=2025' });
    const turnover = await screen.findByTestId('tile-omzet');
    expect(turnover).toHaveAttribute('href', '/rapportage/omzet?jaar=2025');
    expect(turnover).toHaveTextContent('Omzet');
    expect(turnover).toHaveTextContent('€ 1.067.800');
    expect(turnover).not.toHaveClass('grip-tile--attention');
    const costs = screen.getByTestId('tile-kosten');
    expect(costs).toHaveAttribute('href', '/rapportage/kosten?jaar=2025');
    expect(costs).toHaveClass('grip-tile--attention');
    expect(costs).toHaveTextContent('Geen begrotingsregel dekt dit');
    expect(screen.queryByTestId('tile-bezetting')).toBeNull();
  });

  it('links to the year account from the row of filters', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderApp(<ReportsPage />, { path: '/rapportage?jaar=2026' });
    await screen.findByTestId('tile-omzet');
    expect(
      container.querySelector('nldd-toolbar nldd-button[text="Jaarverantwoording"]'),
    ).toHaveAttribute('href', '/rapportage/jaarverantwoording?jaar=2026');
  });

  it('has an empty state for a reader without any block', async () => {
    respond({ '/api/reports/steering': { year: 2026 } });
    const { container } = renderApp(<ReportsPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute(
        'text',
        'Er is voor jou geen sturingsinformatie',
      ),
    );
  });
});
