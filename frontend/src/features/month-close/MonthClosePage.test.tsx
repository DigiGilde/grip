import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { clickButton, mockApi, texts } from '@/features/quotes/testing';
import { renderApp } from '@/test/utils';
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
  path = '/opdrachten/a-1/maandafsluiting',
) {
  const api = mockApi({
    '/api/assignments/a-1/billing': overview,
    '/api/assignments/a-1/billing-status': NO_INVOICES,
    ...replies,
  });
  const view = renderApp(
    <Routes>
      <Route path="/opdrachten/:assignmentId/maandafsluiting" element={<MonthClosePage />} />
    </Routes>,
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
    expect(block.querySelector('nldd-title')?.getAttribute('overline')).toBe('Nu te doen');
    expect(block.querySelector('nldd-title')?.getAttribute('text')).toMatch(
      /^Het tweede kwartaal 2026 is klaar: €/,
    );
    expect(primaryButtons(container)).toEqual(['Lever aan']);
    // The block comes before the course.
    const table = container.querySelector('nldd-table') as Element;
    expect(block.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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
      'Klopt dit met wat er in juli 2026 is gewerkt?',
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

  it('refuses to close on a percentage that is none', async () => {
    const overview = { ...OVERVIEW, next_step: CLOSE_STEP, periods: [Q3] };
    const { calls } = renderTab(
      overview,
      { '/api/assignments/a-1/months/2026-07': OPEN_MONTH },
      '/opdrachten/a-1/maandafsluiting?maand=2026-07',
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
    expect(texts(sheet, 'nldd-title')).toContain('Waar gaat de factuur heen?');
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
      '/opdrachten/a-1/maandafsluiting?factuur=2026-04,2026-05',
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
});
