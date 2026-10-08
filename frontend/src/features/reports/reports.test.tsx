import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import { AssignmentReportPage } from './AssignmentReportPage';
import { ReportsPage } from './ReportsPage';
import { SteeringView } from './SteeringView';
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
    pipeline_cents: 0,
  })),
  realised_cents: 3590000,
  forecast_cents: 101390000,
  pipeline_cents: 0,
  unpriced_assignments: [],
};

const OCCUPANCY = {
  scope: 'own',
  months: MONTHS.map((month) => ({
    month,
    allocated_fte: '1.3',
    available_fte: '2',
    pct: '65',
    under: 1,
    full: 0,
    over: 1,
  })),
  persons: [
    {
      person_id: 'p1',
      person_name: 'Mila Medewerker',
      months: ['120', '80', ...Array.from({ length: 9 }, () => '100'), null],
      average_pct: '100',
    },
  ],
};

const cellTexts = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text') ?? '');

afterEach(() => vi.unstubAllGlobals());

describe('SteeringView', () => {
  it('asks for the chosen year', async () => {
    const fetchMock = respond({ '/api/reports/steering': { year: 2026 } });
    renderApp(<SteeringView year="2026" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      '/api/reports/steering?year=2026',
    );
  });

  it('draws only the blocks the API sent', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    renderApp(<SteeringView year="2026" />);
    await screen.findByTestId('turnover');
    for (const absent of ['occupancy', 'pipeline', 'costs', 'billability', 'open-roles']) {
      expect(screen.queryByTestId(absent)).toBeNull();
    }
  });

  it('shows turnover as a chart with the same amounts in a table', async () => {
    respond({ '/api/reports/steering': { year: 2026, turnover: TURNOVER } });
    const { container } = renderApp(<SteeringView year="2026" />);
    const block = await screen.findByTestId('turnover');
    expect(screen.getByRole('group', { name: 'Omzet per maand in 2026' })).toBeInTheDocument();
    expect(block.querySelector('nldd-table')).toHaveAttribute(
      'accessible-label',
      'Omzet per maand in 2026',
    );
    const texts = cellTexts(container);
    expect(texts).toContain('januari 2026');
    expect(texts.some((text) => text.includes('35.900'))).toBe(true);
    expect(texts.some((text) => text.includes('1.013.900'))).toBe(true);
    // No pipeline in the data, so no column for it.
    expect(texts).not.toContain('Nog niet afgesproken');
    expect(block).toHaveTextContent('Alle opdrachten in 2026.');
  });

  it('says when a total covers only what the reader may see', async () => {
    respond({ '/api/reports/steering': { year: 2026, occupancy: OCCUPANCY } });
    const { container } = renderApp(<SteeringView year="2026" />);
    const block = await screen.findByTestId('occupancy');
    expect(block).toHaveTextContent('Alleen de personen van wie je de inzet mag zien');
    const texts = cellTexts(container);
    expect(texts).toContain('Mila Medewerker');
    // Above 100 percent is said in words, not only in colour.
    expect(texts).toContain('jan');
    expect(container.querySelector('nldd-text-cell[text="120%"]')).toHaveAttribute(
      'color',
      'critical',
    );
  });

  it('names what was left out of the turnover', async () => {
    respond({
      '/api/reports/steering': {
        year: 2026,
        turnover: { ...TURNOVER, unpriced_assignments: ['Opdracht Beta'] },
      },
    });
    const { container } = renderApp(<SteeringView year="2026" />);
    await screen.findByTestId('turnover');
    expect(container.querySelector('nldd-banner')?.getAttribute('text')).toContain('Opdracht Beta');
  });

  it('has an empty state for a reader without any block', async () => {
    respond({ '/api/reports/steering': { year: 2026 } });
    const { container } = renderApp(<SteeringView year="2026" />);
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute(
        'text',
        'Er is voor jou geen sturingsinformatie',
      ),
    );
  });

  it('shows the problem the API reports', async () => {
    respond({ '/api/reports/steering': { title: 'Geen toegang', detail: 'Dat mag niet.' } }, 403);
    const { container } = renderApp(<SteeringView year="2026" />);
    await waitFor(() =>
      expect(container.querySelector('nldd-banner')).toHaveAttribute('text', 'Dat mag niet.'),
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
  billed_cents: 2190000,
  to_bill_cents: 0,
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
    // An overrun is said in words.
    expect(
      container.querySelector('nldd-text-cell[supporting-text="Overschrijding"]'),
    ).not.toBeNull();
  });

  it('leaves out every money section for a reader who got no amounts', async () => {
    respond({ '/api/reports/assignments/a1': REPORT });
    renderReport();
    await screen.findByTestId('delivered');
    expect(screen.queryByTestId('agreed')).toBeNull();
    expect(screen.queryByTestId('cost')).toBeNull();
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

describe('ReportsPage', () => {
  it('opens on the steering overview of the current year', async () => {
    const fetchMock = respond({ '/api/reports/steering': { year: 2026 } });
    const { container } = renderApp(<ReportsPage />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Rapportage');
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      `/api/reports/steering?year=${currentReportYear()}`,
    );
    expect(container.querySelector('nldd-segmented-control')).toHaveAttribute('value', 'steering');
    expect(container.querySelector('select')).toHaveValue(currentReportYear());
  });
});
