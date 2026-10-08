import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { clickButton, mockApi, texts } from '@/features/quotes/testing';
import { renderApp } from '@/test/utils';
import { normalisePercent, percentInput } from './api';
import { MonthClosePage } from './MonthClosePage';

const TIMELINE = {
  assignment_id: 'a-1',
  assignment_name: 'Opdracht Alfa',
  closing_started: true,
  may_close: true,
  months: [
    {
      month: '2026-01',
      closed: true,
      closable: false,
      closed_at: '2026-02-02T09:00:00Z',
      closed_by_name: 'Opdracht Manager',
      reopen_count: 1,
    },
    {
      month: '2026-02',
      closed: false,
      closable: true,
      closed_at: null,
      closed_by_name: null,
      reopen_count: 0,
    },
  ],
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
  month: '2026-02',
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

const CLOSED_MONTH = {
  ...OPEN_MONTH,
  month: '2026-01',
  closed: true,
  closable: false,
  closed_at: '2026-02-02T09:00:00Z',
  closed_by_name: 'Opdracht Manager',
  may_close: false,
  may_reopen: false,
  lines: [{ ...LINE, established_fte_pct: '60.000', established_amount_cents: 1080000 }],
  history: [
    {
      closed_at: '2026-02-01T09:00:00Z',
      closed_by_name: 'Opdracht Manager',
      reopened_at: '2026-02-01T15:00:00Z',
      reopened_by_name: 'Beheerder Voorbeeld',
      reopen_reason: 'Inzet was 60 procent',
    },
    {
      closed_at: '2026-02-02T09:00:00Z',
      closed_by_name: 'Opdracht Manager',
      reopened_at: null,
      reopened_by_name: null,
      reopen_reason: null,
    },
  ],
  established_total_cents: 1080000,
};

// A reader without the financial class: no amounts, months or invoices.
const NO_BILLING = { assignment_id: 'a-1', year: null, billable: true, may_record_invoice: false };

afterEach(() => vi.unstubAllGlobals());

function renderMonths(replies: Record<string, unknown>, path = '/opdrachten/a-1/maandafsluiting') {
  const api = mockApi({
    '/api/assignments/a-1/months': TIMELINE,
    '/api/assignments/a-1/billing-exports': { exports: [] },
    '/api/assignments/a-1/billing-status': NO_BILLING,
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

const DELIVERED = {
  month: '2026-01',
  closed: true,
  state: 'delivered',
  deliverable_cents: 1080000,
  to_deliver_cents: 0,
  export_id: 'e-1',
  delivered_at: '2026-02-03T09:00:00Z',
  delivered_by_name: 'Opdracht Manager',
  delivered_cents: 1080000,
  invoice_id: null,
  invoice_number: null,
  invoice_date: null,
  invoiced_cents: null,
  invoice_on_earlier_delivery: false,
};

const BILLING = {
  assignment_id: 'a-1',
  year: null,
  billable: true,
  may_record_invoice: true,
  deliverable_cents: 1080000,
  delivered_cents: 1080000,
  to_deliver_cents: 0,
  invoiced_cents: 0,
  to_invoice_cents: 1080000,
  months: [DELIVERED],
  invoices: [],
};

const openSheet = () =>
  [...document.body.querySelectorAll('nldd-sheet')].find((el) => el.hasAttribute('open'));

describe('MonthClosePage', () => {
  it('is one calm state until there is an agreement', async () => {
    const { container } = renderMonths({
      '/api/assignments/a-1/months': { ...TIMELINE, closing_started: false },
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
        'Maanden afsluiten kan zodra er een akkoord is',
      ),
    );
    // No month that is not over, no billing, no zeros.
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(texts(container, 'nldd-button')).toEqual([]);
    expect(container.textContent).not.toContain('€');
  });

  it('leads with the oldest month to close, and its one primary action', async () => {
    const { container } = renderMonths({ '/api/assignments/a-1/months/2026-02': OPEN_MONTH });
    await waitFor(() =>
      expect(container.querySelector('nldd-text-field')?.getAttribute('value')).toBe('80'),
    );
    expect(texts(container, 'nldd-title[heading-level="2"]')[0]).toBe('februari 2026 afsluiten');
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual([
      'Sluit februari 2026 af',
    ]);
    expect(container.querySelector('nldd-text-field')?.getAttribute('accessible-label')).toBe(
      'Vastgesteld percentage van Teamlid Voorbeeld',
    );
    // The month on screen has no row action; nothing says "Getoond".
    expect(texts(container, 'nldd-button')).not.toContain('Getoond');
    expect(texts(container, 'nldd-button')).not.toContain('Toon');
  });

  it('gives a month that is not over no action at all', async () => {
    const future = { ...TIMELINE.months[1], month: '2026-12', closable: false };
    const { container } = renderMonths({
      '/api/assignments/a-1/months': { ...TIMELINE, months: [future] },
    });
    await waitFor(() => expect(texts(container, 'nldd-badge')).toEqual(['Nog niet voorbij']));
    expect(texts(container, 'nldd-button')).toEqual([]);
    expect(container.querySelector('nldd-icon-button')).toBeNull();
  });

  it('sends only the percentages that differ from the plan', async () => {
    const { container, calls } = renderMonths({
      '/api/assignments/a-1/months/2026-02': OPEN_MONTH,
      'POST /api/assignments/a-1/months/2026-02/close': { ...OPEN_MONTH, closed: true },
    });
    await waitFor(() => expect(container.querySelector('nldd-text-field')).not.toBeNull());
    container
      .querySelector('nldd-text-field')
      ?.dispatchEvent(new CustomEvent('input', { detail: { value: '62,5' } }));
    await waitFor(() =>
      expect(container.querySelector('nldd-text-field')?.getAttribute('value')).toBe('62,5'),
    );
    clickButton(container, 'Sluit februari 2026 af');
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      established: [{ allocation_id: 'al-1', fte_pct: '62.5' }],
    });
  });

  it('refuses to close on a percentage that is none', async () => {
    const { container, calls } = renderMonths({
      '/api/assignments/a-1/months/2026-02': OPEN_MONTH,
    });
    await waitFor(() => expect(container.querySelector('nldd-text-field')).not.toBeNull());
    container
      .querySelector('nldd-text-field')
      ?.dispatchEvent(new CustomEvent('input', { detail: { value: 'veel' } }));
    await waitFor(() =>
      expect(container.querySelector('nldd-text-field')?.hasAttribute('invalid')).toBe(true),
    );
    clickButton(container, 'Sluit februari 2026 af');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text'),
      ).toContain('Teamlid Voorbeeld'),
    );
    expect(calls.filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('carries the next step of a closed month in its own row', async () => {
    const { container } = renderMonths({
      '/api/assignments/a-1/months/2026-02': OPEN_MONTH,
      '/api/assignments/a-1/billing-status': {
        ...BILLING,
        delivered_cents: 0,
        to_deliver_cents: 1080000,
        to_invoice_cents: 0,
        months: [{ ...DELIVERED, state: 'not_delivered', export_id: null, delivered_cents: null }],
      },
    });
    await waitFor(() => expect(texts(container, 'nldd-button')).toContain('Lever aan'));
    const labels = [...container.querySelectorAll('nldd-button')].map((el) =>
      el.getAttribute('accessible-label'),
    );
    expect(labels).toContain('Lever de factuurgegevens van januari 2026 aan');
  });

  it('offers to record the invoice once a month was delivered, and says where it stands', async () => {
    const { container } = renderMonths({
      '/api/assignments/a-1/months/2026-02': OPEN_MONTH,
      '/api/assignments/a-1/billing-status': BILLING,
    });
    await waitFor(() => expect(texts(container, 'nldd-button')).toContain('Leg factuur vast'));
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells.some((text) => text.startsWith('Aangeleverd op 3 feb 2026'))).toBe(true);
    expect(texts(container, 'nldd-badge')).toEqual(['Aangeleverd', 'Af te sluiten']);
    // The four figures appear because a month is closed and billing is possible.
    expect(
      container.querySelector('nldd-table[accessible-label^="Aangeleverd en gefactureerd"]'),
    ).not.toBeNull();
    clickButton(container, 'Leg factuur vast');
    await waitFor(() =>
      expect(openSheet()?.querySelector('nldd-title')?.getAttribute('text')).toBe(
        'Factuur vastleggen',
      ),
    );
  });

  it('opens the invoice sheet for the months in the address', async () => {
    renderMonths(
      {
        '/api/assignments/a-1/months/2026-02': OPEN_MONTH,
        '/api/assignments/a-1/billing-status': BILLING,
      },
      '/opdrachten/a-1/maandafsluiting?factuur=2026-01',
    );
    await waitFor(() =>
      expect(openSheet()?.querySelector('nldd-title')?.getAttribute('text')).toBe(
        'Factuur vastleggen',
      ),
    );
    expect(openSheet()?.textContent).toContain('januari 2026, aangeleverd');
  });

  it('shows a closed month as established, with the trail', async () => {
    const { container } = renderMonths(
      { '/api/assignments/a-1/months/2026-01': CLOSED_MONTH },
      '/opdrachten/a-1/maandafsluiting?maand=2026-01',
    );
    await waitFor(() => expect(container.textContent).toContain('vastgesteld'));
    expect(container.querySelector('nldd-text-field')).toBeNull();
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('60%');
    expect(cells).toContain('Inzet was 60 procent');
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual([]);
    // Not a beheerder: no way to reopen.
    expect(texts(container, 'nldd-button')).not.toContain('Heropen');
  });

  it('shows no figures and no billing to someone who may not see them', async () => {
    const roster = {
      ...OPEN_MONTH,
      may_close: false,
      lines: [
        {
          allocation_id: 'al-1',
          person_id: 'p-2',
          person_name: 'Teamlid Voorbeeld',
          description: 'Productmanager',
        },
      ],
    };
    delete (roster as { planned_total_cents?: number }).planned_total_cents;
    const { container } = renderMonths(
      {
        '/api/assignments/a-1/months': { ...TIMELINE, may_close: false },
        '/api/assignments/a-1/months/2026-02': roster,
      },
      '/opdrachten/a-1/maandafsluiting?maand=2026-02',
    );
    await waitFor(() =>
      expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Teamlid Voorbeeld'),
    );
    const headers = texts(container, 'nldd-table-row[slot="header"] nldd-text-cell');
    expect(headers).not.toContain('Gepland');
    expect(headers).not.toContain('Maandtarief');
    expect(container.textContent).not.toContain('€');
    expect(texts(container, 'nldd-button')).toEqual([]);
  });
});
