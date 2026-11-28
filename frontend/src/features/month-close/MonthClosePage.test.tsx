import { waitFor } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AssignmentDetail } from '@/features/assignments/api';
import { AssignmentShellContext } from '@/features/assignments/shell';
import { PERMISSIONS, assignment, plain } from '@/features/assignments/testing';
import { clickButton, mockApi, texts } from '@/features/quotes/testing';
import { renderApp } from '@/test/utils';
import { PrimaryTakenContext } from '@/ui/primary';
import { normalisePercent, percentInput } from './api';
import type { BillingOverview, BillingPeriod, PeriodMonth } from './billingApi';
import { MonthClosePage } from './MonthClosePage';
import {
  invoiceDifferenceText,
  periodLine,
  periodStateText,
  stepAction,
  stepLine,
  stepTitle,
} from './periodText';

function month(key: string, label: string, state: PeriodMonth['state'], cents = 1440000) {
  return {
    month: key,
    label,
    state,
    closed_at: state === 'closed' ? '2026-04-02T09:00:00Z' : null,
    closed_by_name: state === 'closed' ? 'Opdracht Manager' : null,
    amount_cents: state === 'upcoming' ? null : cents,
    delivered_cents: null,
    correction_cents: 0,
  } satisfies PeriodMonth;
}

const Q1: BillingPeriod = {
  key: '2026-Q1',
  label: 'eerste kwartaal 2026',
  span: 'januari t/m maart 2026',
  state: 'invoiced',
  months: [
    { ...month('2026-01', 'januari 2026', 'closed'), delivered_cents: 1440000 },
    { ...month('2026-02', 'februari 2026', 'closed'), delivered_cents: 1440000 },
    { ...month('2026-03', 'maart 2026', 'closed'), delivered_cents: 1440000 },
  ],
  closed_cents: 4320000,
  to_deliver_cents: 0,
  delivered_cents: 4320000,
  invoiced_cents: 4320000,
  deliveries: [
    {
      id: 'd-1',
      reference: 'VG-2026-0004/2026-Q1',
      period_key: '2026-Q1',
      total_cents: 4320000,
      via: 'mail',
      recipient: 'facturen@voorbeeld.example',
      delivered_at: '2026-04-03T09:00:00Z',
      delivered_by_name: 'Opdracht Manager',
      has_document: true,
      mail_state: 'sent',
      invoice_id: 'i-1',
      invoice_number: 'F-2026-014',
    },
  ],
  invoice_numbers: ['F-2026-014'],
  awaits_invoice: false,
  last_step_at: '2026-04-03T09:00:00Z',
};

const Q2: BillingPeriod = {
  key: '2026-Q2',
  label: 'tweede kwartaal 2026',
  span: 'april t/m juni 2026',
  state: 'ready',
  months: [
    month('2026-04', 'april 2026', 'closed'),
    month('2026-05', 'mei 2026', 'closed'),
    month('2026-06', 'juni 2026', 'closed'),
  ],
  closed_cents: 4320000,
  to_deliver_cents: 4320000,
  delivered_cents: 0,
  invoiced_cents: 0,
  deliveries: [],
  invoice_numbers: [],
  awaits_invoice: false,
  last_step_at: '2026-07-02T09:00:00Z',
};

const Q3: BillingPeriod = {
  key: '2026-Q3',
  label: 'derde kwartaal 2026',
  span: 'juli t/m september 2026',
  state: 'to_close',
  months: [
    month('2026-07', 'juli 2026', 'to_close'),
    month('2026-08', 'augustus 2026', 'to_close'),
    month('2026-09', 'september 2026', 'to_close'),
  ],
  closed_cents: 0,
  to_deliver_cents: null,
  delivered_cents: 0,
  invoiced_cents: 0,
  deliveries: [],
  invoice_numbers: [],
  awaits_invoice: false,
  last_step_at: null,
};

const OVERVIEW: BillingOverview = {
  assignment_id: 'a-1',
  assignment_name: 'Opdracht Alfa',
  client_name: 'Voorbeeldministerie',
  closing_started: true,
  billable: true,
  may_close: true,
  may_deliver: true,
  may_record_invoice: true,
  may_edit_terms: true,
  terms: {
    rhythm: 'quarter',
    rhythm_is_default: false,
    details: {
      organisation: 'Voorbeeldministerie',
      address: 'Postbus 1',
      postcode_city: '1000 AA Voorbeeldstad',
    },
    missing_details: [],
    names_on_specification: false,
  },
  next_step: {
    kind: 'deliver',
    month: null,
    month_label: null,
    period_key: '2026-Q2',
    period_label: 'tweede kwartaal 2026',
    amount_cents: 4320000,
    from_date: null,
  },
  periods: [Q1, Q2, Q3],
  upcoming_count: 1,
  upcoming_until: 'december 2026',
  closed_cents: 8640000,
  delivered_cents: 4320000,
  invoiced_cents: 4320000,
  can_mail: false,
  recipient: null,
};

const CLOSE_STEP = {
  kind: 'close_month' as const,
  month: '2026-07',
  month_label: 'juli 2026',
  period_key: null,
  period_label: null,
  amount_cents: 1440000,
  from_date: null,
};

const LINE = {
  allocation_id: 'al-1',
  person_id: 'p-2',
  person_name: 'Teamlid Voorbeeld',
  description: 'Productmanager',
  planned_fte_pct: '80.000',
  established_fte_pct: null,
  category: 'D',
  monthly_rate_cents: 1800000,
  planned_amount_cents: 1440000,
  established_amount_cents: null,
};

const OPEN_MONTH = {
  assignment_id: 'a-1',
  month: '2026-07',
  closed: false,
  closable: true,
  closed_at: null,
  closed_by_name: null,
  may_close: true,
  may_reopen: false,
  pricing_problem: null,
  lines: [LINE],
  history: [],
  planned_total_cents: 1440000,
  established_total_cents: null,
};

const NO_INVOICES = { assignment_id: 'a-1', year: null, billable: true, may_record_invoice: true };

afterEach(() => vi.unstubAllGlobals());

function renderTab(
  overview: unknown,
  replies: Record<string, unknown> = {},
  path = '/opdrachten/a-1/afsluiten',
  shell: AssignmentDetail = assignment({ id: 'a-1', permissions: PERMISSIONS.lezer }),
) {
  const api = mockApi({
    '/api/assignments/a-1/billing': overview,
    '/api/assignments/a-1/billing-status': NO_INVOICES,
    '/api/assignments/a-1/financial?year=all': { key_figures: {} },
    ...replies,
  });
  const view = renderApp(
    <AssignmentShellContext.Provider value={shell}>
      <Routes>
        <Route path="/opdrachten/:assignmentId/afsluiten" element={<MonthClosePage />} />
      </Routes>
    </AssignmentShellContext.Provider>,
    { path },
  );
  return { ...api, container: view.container };
}

const openSheet = () =>
  [...document.querySelectorAll('nldd-sheet')].find((sheet) => sheet.hasAttribute('open'));

const primaryButtons = (root: ParentNode) =>
  [...root.querySelectorAll('nldd-button[appearance="primary"]')].map((el) =>
    el.getAttribute('text'),
  );

describe('normalisePercent', () => {
  it('accepts a Dutch decimal comma and a percent sign', () => {
    expect(normalisePercent('62,5')).toBe('62.5');
    expect(normalisePercent(' 80% ')).toBe('80');
    expect(normalisePercent('0')).toBe('0');
    expect(normalisePercent('100')).toBe('100');
  });

  it('refuses anything that is not a percentage between 0 and 100', () => {
    for (const input of ['', 'tachtig', '101', '-5', '1e2', '12.3456', '50,5,5']) {
      expect(normalisePercent(input)).toBeNull();
    }
  });

  it('shows an API percentage with a comma and without trailing zeros', () => {
    expect(percentInput('80.000')).toBe('80');
    expect(percentInput('62.500')).toBe('62,5');
    expect(percentInput(null)).toBe('');
  });
});

describe('the words of the one thing to do', () => {
  it('names the thing and its amount, and keeps the button to a verb', () => {
    expect(stepTitle(OVERVIEW.next_step)).toMatch(
      /^Het tweede kwartaal 2026 is klaar: €\s43\.200$/,
    );
    expect(stepAction(OVERVIEW.next_step)).toBe('Lever aan');
    expect(stepTitle(CLOSE_STEP)).toBe('Juli 2026 is voorbij');
    expect(stepAction(CLOSE_STEP)).toBe('Sluit juli 2026 af');
    expect(stepLine(CLOSE_STEP, OVERVIEW)).toMatch(/^Gepland was €\s14\.400\./);
  });

  it('says when the next thing comes when nothing is due', () => {
    const none = {
      ...CLOSE_STEP,
      kind: 'none' as const,
      month: '2026-10',
      month_label: 'oktober 2026',
      amount_cents: null,
      from_date: '2026-11-01',
    };
    expect(stepTitle(none)).toBe('Er staat niets open');
    expect(stepLine(none, OVERVIEW)).toBe('Vanaf 1 nov 2026 sluit je oktober 2026 af.');
  });

  it('calls a change after the invoice a naverrekening, with the invoice that went out', () => {
    const step = {
      ...OVERVIEW.next_step,
      kind: 'deliver' as const,
      period_key: '2026-Q1',
      period_label: 'eerste kwartaal 2026',
      amount_cents: 500000,
      correction: true,
      invoice_numbers: ['F-2026-0412'],
      invoiced_on: '2026-04-08',
      delivered_on: '2026-04-02',
    };
    expect(stepTitle(step)).toMatch(/^Naverrekening over het eerste kwartaal 2026: €\s5\.000$/);
    expect(stepLine(step, OVERVIEW)).toBe(
      'De periode zelf is gefactureerd op 8 apr 2026 (factuur F-2026-0412). Na die tijd is er iets gewijzigd; lever het verschil aan.',
    );
    expect(stepAction(step)).toBe('Lever de naverrekening aan');
    expect(stepLine({ ...step, invoice_numbers: [], invoiced_on: null }, OVERVIEW)).toMatch(
      /^De periode zelf is aangeleverd op 2 apr 2026\./,
    );
    const period = { ...Q1, state: 'ready' as const, correction: true };
    expect(periodStateText(period)).toBe('Naverrekening');
    expect(periodLine(period)).toBe('Gefactureerd, factuur F-2026-014; daarna gewijzigd');
    expect(periodStateText(Q2)).toBe('Klaar om aan te leveren');
  });

  it('says so when less or more was invoiced than delivered', () => {
    expect(invoiceDifferenceText({ ...Q1, invoice_difference_cents: -10000 })).toMatch(
      /^€\s100 minder gefactureerd dan aangeleverd$/,
    );
    expect(periodLine({ ...Q1, invoice_difference_cents: -10000 })).toMatch(
      /^Factuur F-2026-014; €\s100 minder gefactureerd dan aangeleverd$/,
    );
    expect(invoiceDifferenceText({ ...Q1, invoice_difference_cents: 0 })).toBeNull();
    expect(invoiceDifferenceText(Q1)).toBeNull();
  });

  it('gives each period one line for its last step', () => {
    expect(periodLine(Q1)).toBe('Factuur F-2026-014');
    expect(periodLine(Q2)).toBe('Alle 3 maanden afgesloten');
    expect(periodLine(Q3)).toBe('0 van 3 maanden afgesloten');
  });
});

const KEY_FIGURES = {
  agreed_cents: 19000000,
  budgeted_cents: 18780000,
  expected_total_cents: 16650000,
  agreed_minus_budgeted_cents: 220000,
  budgeted_minus_expected_cents: 2130000,
  realised_cents: 2700000,
  realised_pct: '16.0',
  delivered_cents: 1350000,
  to_deliver_cents: 1250000,
  invoiced_cents: 900000,
  to_invoice_cents: 450000,
};

type FigureValues = { [K in keyof typeof KEY_FIGURES]?: (typeof KEY_FIGURES)[K] | null };

function renderInShell(
  shell: AssignmentDetail,
  figures: FigureValues = {},
  overview: unknown = OVERVIEW,
) {
  const api = mockApi({
    '/api/assignments/a-1/billing': overview,
    '/api/assignments/a-1/billing-status': NO_INVOICES,
    '/api/assignments/a-1/financial?year=all': { key_figures: { ...KEY_FIGURES, ...figures } },
  });
  const view = renderApp(
    <AssignmentShellContext.Provider value={shell}>
      <Routes>
        <Route path="/opdrachten/:assignmentId/afsluiten" element={<MonthClosePage />} />
      </Routes>
    </AssignmentShellContext.Provider>,
    { path: '/opdrachten/a-1/afsluiten' },
  );
  return { ...api, container: view.container };
}

describe('where delivery and invoicing stand', () => {
  const external = assignment({ id: 'a-1' });

  it('stands above the periods of an external assignment, over the whole period', async () => {
    const { container, calls } = renderInShell(external);
    await waitFor(() =>
      expect(container.querySelector('dl[aria-label="Aanleveren en factureren"]')).not.toBeNull(),
    );
    const block = container.querySelector('dl[aria-label="Aanleveren en factureren"]') as Element;
    const pairs = [...block.querySelectorAll('.key-figure')].map((figure) => [
      figure.querySelector('dt')?.textContent,
      plain(figure.querySelector('dd')?.textContent),
    ]);
    expect(pairs).toEqual([
      ['Aangeleverd', '€ 13.500'],
      ['Nog aan te leveren', '€ 12.500'],
      ['Gefactureerd', '€ 9.000'],
      ['Nog te factureren', '€ 4.500'],
    ]);
    const table = container.querySelector('nldd-table') as Element;
    expect(block.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(calls.map((call) => call.url)).toContain('/api/assignments/a-1/financial?year=all');
  });

  it('says so when more was invoiced than delivered', async () => {
    const { container } = renderInShell(external, { to_invoice_cents: -10000 });
    await waitFor(() => expect(container.querySelector('.key-figures')).not.toBeNull());
    expect(container.querySelector('.key-figure-value.critical')?.textContent).toMatch(/100/);
    expect(container.textContent).toContain('Meer gefactureerd dan aangeleverd');
  });

  it('says that a figure is not known rather than zero', async () => {
    const { container } = renderInShell(external, { to_deliver_cents: null });
    await waitFor(() => expect(container.querySelector('.key-figures')).not.toBeNull());
    const known = [...container.querySelectorAll('.key-figure-value')].map((el) => el.textContent);
    expect(known.filter((value) => value === 'Niet bekend')).toHaveLength(1);
  });

  it('leaves out what is zero, and the block when nothing is left', async () => {
    const { container } = renderInShell(external, { delivered_cents: 0, invoiced_cents: 0 });
    await waitFor(() => expect(container.querySelector('.key-figures')).not.toBeNull());
    const labels = [...container.querySelectorAll('.key-figure dt')].map((el) => el.textContent);
    expect(labels).toEqual(['Nog aan te leveren', 'Nog te factureren']);
    vi.unstubAllGlobals();
    const none = renderInShell(external, {
      delivered_cents: 0,
      to_deliver_cents: 0,
      invoiced_cents: 0,
      to_invoice_cents: 0,
    });
    await waitFor(() => expect(none.container.querySelector('nldd-table')).not.toBeNull());
    expect(none.container.querySelector('.key-figures')).toBeNull();
  });

  it('is asked for again after a month is closed on this page', async () => {
    const overview = { ...OVERVIEW, next_step: CLOSE_STEP, periods: [Q3] };
    const url = '/api/assignments/a-1/financial?year=all';
    const { calls } = (() => {
      const api = mockApi({
        '/api/assignments/a-1/billing': overview,
        '/api/assignments/a-1/billing-status': NO_INVOICES,
        [url]: { key_figures: KEY_FIGURES },
        '/api/assignments/a-1/months/2026-07': OPEN_MONTH,
        'POST /api/assignments/a-1/months/2026-07/close': { ...OPEN_MONTH, closed: true },
      });
      renderApp(
        <AssignmentShellContext.Provider value={external}>
          <Routes>
            <Route path="/opdrachten/:assignmentId/afsluiten" element={<MonthClosePage />} />
          </Routes>
        </AssignmentShellContext.Provider>,
        { path: '/opdrachten/a-1/afsluiten?maand=2026-07' },
      );
      return api;
    })();
    await waitFor(() => expect(openSheet()?.querySelector('nldd-table')).toBeTruthy());
    expect(calls.filter((call) => call.url === url)).toHaveLength(1);
    (openSheet() as Element)
      .querySelector('nldd-form')
      ?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/close'))).toBe(true));
    await waitFor(() => expect(calls.filter((call) => call.url === url)).toHaveLength(2));
  });

  it('is not there for an internal assignment, which has no invoices', async () => {
    const { container, calls } = renderInShell(assignment({ id: 'a-1', kind: 'internal' }));
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('.key-figures')).toBeNull();
    expect(calls.some((call) => call.url.includes('/financial'))).toBe(false);
  });

  it('is not asked for by who may not read the money', async () => {
    const { container, calls } = renderInShell(
      assignment({ id: 'a-1', permissions: PERMISSIONS.planner }),
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('.key-figures')).toBeNull();
    expect(calls.some((call) => call.url.includes('/financial'))).toBe(false);
  });
});

function Search() {
  return <span data-testid="search">{useLocation().search}</span>;
}

describe('an address that asks for a month', () => {
  function renderAt(path: string) {
    mockApi({
      '/api/assignments/a-1/billing': { ...OVERVIEW, next_step: CLOSE_STEP, periods: [Q3] },
      '/api/assignments/a-1/billing-status': NO_INVOICES,
      '/api/assignments/a-1/months/2026-07': OPEN_MONTH,
    });
    return renderApp(
      <Routes>
        <Route
          path="/opdrachten/:assignmentId/afsluiten"
          element={
            <>
              <MonthClosePage />
              <Search />
            </>
          }
        />
      </Routes>,
      { path },
    );
  }

  it('opens a month that is in a period', async () => {
    renderAt('/opdrachten/a-1/afsluiten?maand=2026-07');
    await waitFor(() => expect(openSheet()).toBeDefined());
    expect(document.querySelector('[data-testid="search"]')?.textContent).toBe('?maand=2026-07');
  });

  it('opens nothing for a month that is in no period, and drops it from the address', async () => {
    const { container } = renderAt('/opdrachten/a-1/afsluiten?maand=2030-01');
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    await waitFor(() =>
      expect(document.querySelector('[data-testid="search"]')?.textContent).toBe(''),
    );
    expect(openSheet()).toBeUndefined();
  });
});

describe('the periods', () => {
  const lineAbove = (container: Element) =>
    plain(container.querySelector('[data-periods-line]')?.textContent);

  it('has no heading of its own: the title of the part says it', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-title[text="Perioden"]')).toBeNull();
  });

  it('says how the assignment is billed and what is to be closed above the table', async () => {
    const overview = { ...OVERVIEW, next_step: CLOSE_STEP, periods: [Q1, Q3] };
    const { container } = renderTab(overview);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(lineAbove(container)).toBe(
      'Factureren per kwartaal, factuur aan Voorbeeldministerie. 3 maanden af te sluiten. Nog 1 kwartaal te gaan, t/m december 2026.',
    );
    const line = container.querySelector('[data-periods-line]') as Element;
    const table = container.querySelector('nldd-table') as Element;
    expect(line.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('speaks of one month in the singular, and leaves out what there is not', async () => {
    const one = { ...Q3, months: [month('2026-07', 'juli 2026', 'to_close')] };
    const overview = { ...OVERVIEW, periods: [Q1, one], upcoming_count: 0, upcoming_until: null };
    const { container } = renderTab(overview);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(lineAbove(container)).toBe(
      'Factureren per kwartaal, factuur aan Voorbeeldministerie. 1 maand af te sluiten.',
    );
  });

  it('does not name who the invoice goes to for who may not read that', async () => {
    const overview = { ...OVERVIEW, terms: { rhythm: 'quarter', rhythm_is_default: false } };
    const { container } = renderTab(overview);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(lineAbove(container)).toContain('Factureren per kwartaal.');
    expect(lineAbove(container)).not.toContain('Voorbeeldministerie');
  });

  it('says nothing about invoices on an internal assignment', async () => {
    const { container } = renderInShell(
      assignment({ id: 'a-1', kind: 'internal' }),
      {},
      {
        ...OVERVIEW,
        periods: [Q3],
        upcoming_count: 0,
      },
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(lineAbove(container)).toBe('3 maanden af te sluiten.');
    expect(container.querySelector('nldd-link[text="Wijzig factuurafspraken"]')).toBeNull();
  });

  it('adds up to the total of the service, in a row of its own', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const rows = [...container.querySelectorAll('nldd-table > nldd-table-row:not([slot])')];
    const total = rows.at(-1) as Element;
    const cells = [...total.querySelectorAll('nldd-text-cell')].map((cell) =>
      plain(cell.getAttribute('text')),
    );
    expect(cells).toEqual(['**Totaal afgesloten**', '', '**€ 86.400**']);
    // A figure the server did not add up the same way is shown as sent.
    vi.unstubAllGlobals();
    const other = renderTab({ ...OVERVIEW, closed_cents: 123400 });
    await waitFor(() => expect(other.container.querySelector('nldd-table')).not.toBeNull());
    expect(
      [...other.container.querySelectorAll('nldd-text-cell')].some(
        (cell) => plain(cell.getAttribute('text')) === '**€ 1.234**',
      ),
    ).toBe(true);
  });

  it('has no total without an amount: nothing closed, or nothing to read', async () => {
    const { container } = renderTab({ ...OVERVIEW, closed_cents: 0 });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-text-cell[text="**Totaal afgesloten**"]')).toBeNull();
    vi.unstubAllGlobals();
    const other = renderTab({ ...OVERVIEW, closed_cents: undefined });
    await waitFor(() => expect(other.container.querySelector('nldd-table')).not.toBeNull());
    expect(
      other.container.querySelector('nldd-text-cell[text="**Totaal afgesloten**"]'),
    ).toBeNull();
  });

  it('keeps the Bedrag column for who may read amounts, also when a month has no price', async () => {
    const { container } = renderTab({ ...OVERVIEW, closed_cents: null });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(
      container.querySelector('nldd-table-row[slot="header"] nldd-text-cell[text="Bedrag"]'),
    ).not.toBeNull();
  });

  it('leaves out the Bedrag column for who may not read amounts', async () => {
    const { container } = renderTab(
      OVERVIEW,
      {},
      undefined,
      assignment({ id: 'a-1', permissions: PERMISSIONS.planner }),
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(
      container.querySelector('nldd-table-row[slot="header"] nldd-text-cell[text="Bedrag"]'),
    ).toBeNull();
  });

  it('keeps the total to the columns of a narrow screen', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const total = container.querySelector('nldd-text-cell[text="**Totaal afgesloten**"]')
      ?.parentElement as Element;
    expect(total.children).toHaveLength(5);
    expect(total.children[2]).toHaveAttribute('hide-below', 'md');
  });

  it('puts the way to the terms under the table, for who may change them', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const link = container.querySelector('nldd-link[text="Wijzig factuurafspraken"]') as Element;
    const table = container.querySelector('nldd-table') as Element;
    expect(table.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    vi.unstubAllGlobals();
    const other = renderTab({ ...OVERVIEW, may_edit_terms: false });
    await waitFor(() => expect(other.container.querySelector('nldd-table')).not.toBeNull());
    expect(other.container.querySelector('nldd-link[text="Wijzig factuurafspraken"]')).toBeNull();
  });
});

describe('MonthClosePage', () => {
  it('is one calm state until there is an agreement', async () => {
    const { container } = renderTab({ ...OVERVIEW, closing_started: false, periods: [] });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toEqual([
        'Maanden afsluiten kan zodra er an akkoord is'.replace(' an ', ' een '),
      ]),
    );
    expect(container.querySelector('nldd-card')).toBeNull();
    expect(container.querySelector('nldd-table')).toBeNull();
  });

  it('leads with the one thing to do, and that is the only accent', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-card')).not.toBeNull());
    const block = container.querySelector('nldd-card') as Element;
    // The head of the assignment says "now"; the block does not say it again.
    expect(block.querySelector('nldd-title')?.getAttribute('overline')).toBeNull();
    expect(block.querySelector('nldd-title')?.getAttribute('text')).toMatch(
      /^Het tweede kwartaal 2026 is klaar: €/,
    );
    expect(primaryButtons(container)).toEqual(['Lever aan']);
    // The block comes before the course.
    const table = container.querySelector('nldd-table') as Element;
    expect(block.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('leaves the heading and the section to the page of the part', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('h1')).toBeNull();
    expect(container.querySelector('nldd-simple-section')).toBeNull();
  });

  it('leaves the step to the head of the part when the head carries it', async () => {
    mockApi({
      '/api/assignments/a-1/billing': OVERVIEW,
      '/api/assignments/a-1/billing-status': NO_INVOICES,
    });
    const { container } = renderApp(
      <PrimaryTakenContext.Provider value={true}>
        <Routes>
          <Route path="/opdrachten/:assignmentId/afsluiten" element={<MonthClosePage />} />
        </Routes>
      </PrimaryTakenContext.Provider>,
      { path: '/opdrachten/a-1/afsluiten' },
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-card')).toBeNull();
    expect(primaryButtons(container)).toEqual([]);
  });

  it('keeps period, state and amount on a narrow screen and lets only the step go', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const table = container.querySelector('nldd-table') as Element;
    expect(table.getAttribute('sm-columns')?.trim().split(' ')).toHaveLength(4);
    const header = (text: string) =>
      table.querySelector(`nldd-table-row[slot="header"] nldd-text-cell[text="${text}"]`);
    expect(header('Periode')).not.toHaveAttribute('hide-below');
    expect(header('Stand')).not.toHaveAttribute('hide-below');
    expect(header('Bedrag')).not.toHaveAttribute('hide-below');
    expect(header('Stap')).toHaveAttribute('hide-below', 'md');
    expect(table.querySelector('nldd-cell[hide-below]')).toBeNull();
    expect(table.querySelector('[hide-above]')).toBeNull();
  });

  it('shows periods as the course: one tag per row, colour only on the next step', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const badges = [...container.querySelectorAll('nldd-table nldd-badge')];
    expect(badges.map((badge) => badge.getAttribute('text'))).toEqual([
      'Gefactureerd',
      'Klaar om aan te leveren',
      'Af te sluiten',
    ]);
    expect(badges.map((badge) => badge.getAttribute('color'))).toEqual([
      'neutral',
      'accent',
      'neutral',
    ]);
    // No button sits in a row: the row opens, the rest is in its menu.
    expect(container.querySelectorAll('nldd-table nldd-button').length).toBe(0);
    // Periods that have not begun are one quiet line, not rows.
    expect(container.textContent).toContain('Nog 1 kwartaal te gaan, t/m december 2026');
    expect(container.textContent).toContain('Factureren per kwartaal');
  });

  it('says that the amount of a period still being closed is what is already closed', async () => {
    const part = { ...Q3, closed_cents: 6880000 };
    const { container } = renderTab({ ...OVERVIEW, periods: [part] });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const cell = [...container.querySelectorAll('nldd-text-cell')].find(
      (el) => plain(el.getAttribute('text')) === '**€ 68.800**',
    );
    expect(cell?.getAttribute('supporting-text')).toBe('afgesloten');
  });

  it('opens only the period of the next step; months of others come on demand', async () => {
    const { container } = renderTab(OVERVIEW);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.textContent).toContain('april 2026');
    expect(container.textContent).not.toContain('juli 2026');
    const badge = [...container.querySelectorAll('nldd-table nldd-badge')].find(
      (el) => el.getAttribute('text') === 'Af te sluiten',
    );
    badge?.closest('nldd-table-row')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await waitFor(() => expect(container.textContent).toContain('juli 2026'));
  });

  it('asks one question when a month is to be closed, and sends only what differs', async () => {
    const overview = { ...OVERVIEW, next_step: CLOSE_STEP, periods: [Q3] };
    const { container, calls } = renderTab(overview, {
      '/api/assignments/a-1/months/2026-07': OPEN_MONTH,
      'POST /api/assignments/a-1/months/2026-07/close': { ...OPEN_MONTH, closed: true },
      'POST /api/assignments/a-1/months/2026-07/preview': {
        month: '2026-07',
        lines: [{ allocation_id: 'al-1', amount_cents: 1080000 }],
        total_cents: 1080000,
      },
    });
    await waitFor(() => expect(primaryButtons(container)).toEqual(['Sluit juli 2026 af']));
    expect(openSheet()).toBeUndefined();
    clickButton(container, 'Sluit juli 2026 af');
    await waitFor(() => expect(openSheet()?.querySelector('nldd-table')).toBeTruthy());
    const sheet = openSheet() as Element;
    expect(sheet.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe(
      'Juli 2026 afsluiten',
    );
    expect(primaryButtons(sheet)).toEqual(['Sluit juli 2026 af']);
    const field = sheet.querySelector('nldd-text-field') as Element;
    field.dispatchEvent(new CustomEvent('input', { detail: { value: '60' } }));
    // What differs from the plan is marked, with the planned figure beside it.
    await waitFor(() =>
      expect(
        [...sheet.querySelectorAll('nldd-text-cell')].some((cell) =>
          cell.getAttribute('supporting-text')?.includes('gepland 80%'),
        ),
      ).toBe(true),
    );
    // The amount follows the percentage, priced by the server, before closing.
    await waitFor(() =>
      expect(sheet.querySelector('[data-month-total]')?.textContent).toMatch(
        /De maand komt op €\s10\.800; gepland was €\s14\.400\./,
      ),
    );
    expect(
      [...sheet.querySelectorAll('nldd-text-cell')].some(
        (cell) =>
          /€\s10\.800/.test(cell.getAttribute('text') ?? '') &&
          /gepland €\s14\.400/.test(cell.getAttribute('supporting-text') ?? ''),
      ),
    ).toBe(true);
    expect(calls.find((call) => call.url.endsWith('/preview'))?.body).toEqual({
      established: [{ allocation_id: 'al-1', fte_pct: '60' }],
    });
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/close'))).toBe(true));
    expect(calls.find((call) => call.url.endsWith('/close'))?.body).toEqual({
      established: [{ allocation_id: 'al-1', fte_pct: '60' }],
    });
  });

  it('lets a beheerder reopen a closed month, and says what that does to a delivered one', async () => {
    const closed = {
      ...OPEN_MONTH,
      month: '2026-02',
      closed: true,
      closable: false,
      closed_at: '2026-03-03T12:00:00Z',
      closed_by_name: 'Voorbeeld Een',
      may_close: false,
      may_reopen: true,
    };
    renderTab(
      { ...OVERVIEW, periods: [Q1] },
      { '/api/assignments/a-1/months/2026-02': closed },
      '/opdrachten/a-1/afsluiten?maand=2026-02',
    );
    await waitFor(() =>
      expect(document.querySelector('nldd-button[text="Heropen de maand"]')).not.toBeNull(),
    );
    document
      .querySelector('nldd-button[text="Heropen de maand"]')
      ?.dispatchEvent(new Event('click'));
    await waitFor(() =>
      expect(
        document.querySelector(
          'nldd-banner[text="Deze maand is al aangeleverd aan de financiële administratie"]',
        ),
      ).not.toBeNull(),
    );
  });

  it('offers reopening each closed month from the menu of its period, for who may', async () => {
    const closed = {
      ...OPEN_MONTH,
      month: '2026-02',
      closed: true,
      closable: false,
      may_close: false,
      may_reopen: true,
    };
    const { container } = renderTab(
      { ...OVERVIEW, may_reopen: true, periods: [Q1] },
      { '/api/assignments/a-1/months/2026-02': closed },
    );
    await waitFor(() =>
      expect(
        container.querySelector('nldd-menu-item[text="Heropen februari 2026"]'),
      ).not.toBeNull(),
    );
    container
      .querySelector('nldd-menu-item[text="Heropen februari 2026"]')
      ?.dispatchEvent(new Event('select'));
    // The sheet opens at the question itself, with the warning for a delivered month.
    await waitFor(() =>
      expect(
        document.querySelector(
          'nldd-banner[text="Deze maand is al aangeleverd aan de financiële administratie"]',
        ),
      ).not.toBeNull(),
    );
    expect(
      document.querySelector('nldd-button[text="Heropen de maand"][type="submit"]'),
    ).not.toBeNull();

    vi.unstubAllGlobals();
    const other = renderTab({ ...OVERVIEW, periods: [Q1] });
    await waitFor(() => expect(other.container.querySelector('nldd-table-row')).not.toBeNull());
    expect(other.container.querySelector('nldd-menu-item[text^="Heropen"]')).toBeNull();
  });

  it('tells who closes months where the way back is', async () => {
    // The detail of a closed month says may_close false; the tab knows who closes.
    const closed = {
      ...OPEN_MONTH,
      month: '2026-02',
      closed: true,
      closable: false,
      may_close: false,
    };
    renderTab(
      { ...OVERVIEW, periods: [Q1] },
      { '/api/assignments/a-1/months/2026-02': closed },
      '/opdrachten/a-1/afsluiten?maand=2026-02',
    );
    await waitFor(() =>
      expect(document.body.textContent).toContain(
        'Een afgesloten maand heropent alleen een beheerder.',
      ),
    );
    expect(document.querySelector('nldd-button[text="Heropen de maand"]')).toBeNull();
  });

  it('refuses to close on a percentage that is none', async () => {
    const overview = { ...OVERVIEW, next_step: CLOSE_STEP, periods: [Q3] };
    const { calls } = renderTab(
      overview,
      { '/api/assignments/a-1/months/2026-07': OPEN_MONTH },
      '/opdrachten/a-1/afsluiten?maand=2026-07',
    );
    await waitFor(() => expect(openSheet()?.querySelector('nldd-text-field')).toBeTruthy());
    const sheet = openSheet() as Element;
    sheet
      .querySelector('nldd-text-field')
      ?.dispatchEvent(new CustomEvent('input', { detail: { value: 'veel' } }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-text-field')?.getAttribute('value')).toBe('veel'),
    );
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner')?.getAttribute('text')).toContain(
        'geen getal tussen 0 en 100',
      ),
    );
    expect(calls.some((call) => call.method === 'POST')).toBe(false);
  });

  it('delivers a period from its sheet, which says where the invoice goes', async () => {
    const { container, calls } = renderTab(OVERVIEW, {
      'POST /api/assignments/a-1/billing/deliveries': OVERVIEW,
    });
    await waitFor(() => expect(primaryButtons(container)).toEqual(['Lever aan']));
    clickButton(container, 'Lever aan');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    expect(sheet.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe(
      'Lever het tweede kwartaal 2026 aan',
    );
    expect(texts(sheet, 'nldd-text-cell')).toContain('Postbus 1');
    // The address is known, so nothing is asked.
    expect(sheet.querySelectorAll('nldd-text-field').length).toBe(0);
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      period_key: '2026-Q2',
      via: 'self',
    });
  });

  it('asks for the invoice address in the same sheet when it is not known', async () => {
    const overview = {
      ...OVERVIEW,
      terms: { ...OVERVIEW.terms, details: {}, missing_details: ['organisation', 'address'] },
    };
    const { container, calls } = renderTab(overview);
    await waitFor(() => expect(primaryButtons(container)).toEqual(['Lever aan']));
    clickButton(container, 'Lever aan');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    expect(texts(sheet, 'nldd-title')).toContain('Adres voor de factuur');
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner')?.getAttribute('text')).toBe('Vul in: organisatie.'),
    );
    expect(calls.some((call) => call.method !== 'GET')).toBe(false);
  });

  it('opens the sheet to record an invoice for the months in the address', async () => {
    const delivered = {
      ...Q2,
      state: 'delivered' as const,
      to_deliver_cents: 0,
      delivered_cents: 4320000,
      awaits_invoice: true,
    };
    const overview = {
      ...OVERVIEW,
      periods: [Q1, delivered],
      next_step: { ...OVERVIEW.next_step, kind: 'record_invoice' as const },
    };
    const { calls } = renderTab(
      overview,
      { 'POST /api/assignments/a-1/billing/periods/2026-Q2/invoice': overview },
      '/opdrachten/a-1/afsluiten?factuur=2026-04,2026-05',
    );
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    expect(sheet.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe(
      'Factuur over het tweede kwartaal 2026',
    );
    const fields = [...sheet.querySelectorAll('nldd-text-field')];
    // The amount proposes what was delivered.
    expect(fields[1]?.getAttribute('value')).toBe('43200');
    fields[0]?.dispatchEvent(new CustomEvent('input', { detail: { value: 'F-2026-031' } }));
    await waitFor(() => expect(fields[0]?.getAttribute('value')).toBe('F-2026-031'));
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    expect(calls.find((call) => call.method === 'POST')?.body).toMatchObject({
      invoice_number: 'F-2026-031',
      amount_cents: 4320000,
    });
  });

  it('shows no figures and no actions to someone who may not see or do them', async () => {
    const strip = (period: BillingPeriod) => {
      const rest: Partial<BillingPeriod> = { ...period };
      delete rest.closed_cents;
      delete rest.to_deliver_cents;
      delete rest.delivered_cents;
      return {
        ...rest,
        months: period.months.map((entry) => {
          const month: Partial<PeriodMonth> = { ...entry };
          delete month.amount_cents;
          delete month.delivered_cents;
          return month;
        }),
      };
    };
    const overview = {
      ...OVERVIEW,
      may_close: false,
      may_deliver: false,
      may_record_invoice: false,
      may_edit_terms: false,
      periods: [Q1, Q2, Q3].map(strip),
      next_step: { ...OVERVIEW.next_step, amount_cents: undefined },
      closed_cents: undefined,
      delivered_cents: undefined,
      invoiced_cents: undefined,
      terms: { rhythm: 'quarter', rhythm_is_default: false },
    };
    const { container } = renderTab(overview);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.textContent).not.toContain('€');
    expect(container.querySelectorAll('nldd-button').length).toBe(0);
    // No call to act for who cannot act: one calm line of what is open and who can.
    expect(container.querySelector('nldd-card')).toBeNull();
    expect(container.querySelector('[data-waiting]')?.textContent).toContain(
      'Dit kan de eigenaar of een manager van de opdracht.',
    );
    expect(container.textContent).not.toContain('Wijzig factuurafspraken');
  });

  it('says the dossier is closed instead of who can act', async () => {
    const { container } = renderTab(
      {
        ...OVERVIEW,
        may_close: false,
        may_reopen: false,
        may_deliver: false,
        may_record_invoice: false,
        may_edit_terms: false,
      },
      { '/api/assignments/a-1/billing-status': { ...NO_INVOICES, may_record_invoice: false } },
      '/opdrachten/a-1/afsluiten',
      assignment({ id: 'a-1', permissions: PERMISSIONS.lezer, dossier_closed_on: '2026-11-25' }),
    );
    await waitFor(() => expect(container.querySelector('[data-waiting]')).not.toBeNull());
    const waiting = container.querySelector('[data-waiting]')?.textContent ?? '';
    expect(waiting).toContain(
      'Het dossier is gesloten; wijzigen kan weer als de beheerder het heropent.',
    );
    expect(waiting).not.toContain('Dit kan de eigenaar');
    expect(primaryButtons(container)).toEqual([]);
  });
});
