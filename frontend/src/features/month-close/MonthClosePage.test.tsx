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

describe('MonthClosePage', () => {
  it('opens the first month that waits to be closed, with the plan as proposal', async () => {
    const { container } = renderMonths({ '/api/assignments/a-1/months/2026-02': OPEN_MONTH });
    await waitFor(() =>
      expect(container.querySelector('nldd-text-field')?.getAttribute('value')).toBe('80'),
    );
    expect(container.querySelector('nldd-text-field')?.getAttribute('accessible-label')).toBe(
      'Vastgesteld percentage van Teamlid Voorbeeld',
    );
    expect(texts(container, 'nldd-button')).toContain('Sluit maand af');
    const badges = texts(container, 'nldd-badge');
    expect(badges).toEqual(['Afgesloten', 'Open']);
    expect(
      [...container.querySelectorAll('nldd-text-cell')].map((el) =>
        el.getAttribute('supporting-text'),
      ),
    ).toContain('1 keer heropend');
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
    clickButton(container, 'Sluit maand af');
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
    clickButton(container, 'Sluit maand af');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text'),
      ).toContain('Teamlid Voorbeeld'),
    );
    expect(calls.filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('shows a closed month as established, with the trail and the billing data', async () => {
    const { container } = renderMonths(
      { '/api/assignments/a-1/months/2026-01': CLOSED_MONTH },
      '/opdrachten/a-1/maandafsluiting?maand=2026-01',
    );
    await waitFor(() => expect(container.textContent).toContain('Totaal vastgesteld'));
    expect(container.querySelector('nldd-text-field')).toBeNull();
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('60%');
    expect(cells).toContain('Inzet was 60 procent');
    expect(texts(container, 'nldd-button')).not.toContain('Sluit maand af');
    // Not a beheerder: no way to reopen.
    expect(texts(container, 'nldd-button')).not.toContain('Heropen maand');
    expect(texts(container, 'nldd-button')).toContain('Lever factuurgegevens aan');
  });

  it('draws no column for what the reader may not see', async () => {
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
    const { container } = renderMonths({ '/api/assignments/a-1/months/2026-02': roster });
    await waitFor(() =>
      expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Teamlid Voorbeeld'),
    );
    const headers = texts(container, 'nldd-table-row[slot="header"] nldd-text-cell');
    expect(headers).not.toContain('Gepland');
    expect(headers).not.toContain('Maandtarief');
    expect(container.textContent).not.toContain('€');
    expect(texts(container, 'nldd-button')).not.toContain('Sluit maand af');
  });
});
