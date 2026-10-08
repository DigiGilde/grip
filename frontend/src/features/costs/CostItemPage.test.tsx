import { fireEvent, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import type { CostItem } from './api';
import { CostItemPage } from './CostItemPage';

const RECEIVED = {
  id: 'l-1',
  reference: 'HOST-26-01',
  description: null,
  kind: 'actual' as const,
  amount_cents: 375000,
  period: '2026-01-01',
  attachments: [
    {
      id: 'a-1',
      filename: 'factuur-januari.pdf',
      content_type: 'application/pdf',
      size_bytes: 86016,
      uploaded_at: '2026-02-02T09:00:00Z',
      uploaded_by_name: 'Een beheerder',
    },
  ],
};

const ITEM: CostItem = {
  id: 'c-1',
  description: 'Hostingcontract',
  budgeted_cents: 1500000,
  forecast_cents: 1500000,
  actual_cents: 750000,
  estimate_cents: 750000,
  variance_cents: 0,
  covered_cents: 1200000,
  uncovered_cents: 300000,
  pct_total: '80.00',
  uncovered_pct: '20.00',
  hidden_coverage_pct: '0',
  invoice_lines: [
    { ...RECEIVED, id: 'l-3', reference: 'HOST-26-03', kind: 'estimate', period: '2026-10-01', attachments: [], amount_cents: 750000 },
    { ...RECEIVED, id: 'l-2', reference: 'HOST-26-02', period: '2026-04-01', attachments: [] },
    RECEIVED,
  ],
  coverages: [
    {
      budget_line_id: 'b-1',
      budget_line_description: 'Hosting en licenties',
      assignment_id: 'as-1',
      assignment_name: 'Opdracht Alfa 2026',
      pct: '30.00',
      amount_cents: 450000,
      may_edit: true,
    },
    {
      budget_line_id: 'b-2',
      budget_line_description: 'Hosting 2026',
      assignment_id: 'as-2',
      assignment_name: 'Opdracht Delta 2026-2027',
      pct: '50.00',
      amount_cents: 750000,
      may_edit: false,
    },
  ],
  may_edit: true,
};

const OPTIONS = {
  items: [
    {
      budget_line_id: 'b-9',
      description: 'Materieel',
      kind: 'material',
      assignment_id: 'as-1',
      assignment_name: 'Opdracht Alfa 2026',
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

interface Call {
  method: string;
  url: string;
  body?: string;
}

async function renderPage(item: CostItem, refuse?: { status: number; detail: string }) {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ method, url, body: typeof init?.body === 'string' ? init.body : undefined });
      if (method === 'PUT' && refuse) {
        return Promise.resolve(
          new Response(JSON.stringify({ title: 'Fout', status: refuse.status, detail: refuse.detail }), {
            status: refuse.status,
            headers: { 'Content-Type': 'application/problem+json' },
          }),
        );
      }
      const body = url.startsWith('/api/costs/coverage-options') ? OPTIONS : item;
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  const view = renderApp(
    <Routes>
      <Route path="/kosten/:costItemId" element={<CostItemPage />} />
    </Routes>,
    { path: '/kosten/c-1' },
  );
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return { page: view.container, calls };
}

/** Amounts carry a non-breaking space after the euro sign; read them with a plain one. */
const plain = (text: string | null | undefined) => (text ?? '').replace(/\u00a0/g, ' ');

const button = (root: ParentNode, text: string) =>
  [...root.querySelectorAll('nldd-button')].find((el) => el.getAttribute('text') === text);

const openSheet = () =>
  document.body.querySelector('nldd-sheet[open]') as HTMLElement | null;

describe('CostItemPage', () => {
  it('leads with three figures and says the variance in words', async () => {
    const { page } = await renderPage(ITEM);
    const figures = [...page.querySelectorAll('.grip-figure')].map((el) => el.textContent);
    expect(figures).toHaveLength(3);
    expect(figures[0]).toContain('Begroot');
    expect(figures[1]).toContain('Verwacht totaal');
    expect(figures[2]).toContain('Afwijking');
    expect(figures[2]).toContain('Precies begroot');
    expect(page.querySelector('.grip-figure--attention')).toBeNull();
    expect(page.innerHTML.toLowerCase()).not.toContain('prognose');
  });

  it('flags an overrun in the headline', async () => {
    const { page } = await renderPage({ ...ITEM, forecast_cents: 1600000, variance_cents: -100000 });
    expect(page.querySelector('.grip-figure--attention')?.textContent).toContain('Overschrijding');
  });

  it('draws what came in and what is expected against the budget, with the values as text', async () => {
    const { page } = await renderPage(ITEM);
    const bars = page.querySelectorAll('.cost-bar');
    expect(bars).toHaveLength(2);
    const forecast = bars[0] as HTMLElement;
    expect(plain(forecast.querySelector('[role="img"]')?.getAttribute('aria-label'))).toBe(
      'Ontvangen € 7.500, nog verwacht € 7.500, begroot € 15.000',
    );
    expect(forecast.querySelectorAll('.cost-bar__track .cost-seg')).toHaveLength(2);
    expect(forecast.querySelector('.cost-bar__mark')).not.toBeNull();
    expect(plain(forecast.querySelector('.cost-legend')?.textContent)).toContain('Nog verwacht € 7.500');
  });

  it('marks what nobody pays for as a part of its own, with the amount', async () => {
    const { page } = await renderPage(ITEM);
    const coverage = page.querySelectorAll('.cost-bar')[1] as HTMLElement;
    const segments = [...coverage.querySelectorAll('.cost-bar__track .cost-seg')];
    expect(segments.map((el) => el.getAttribute('data-kind') ?? el.getAttribute('data-step'))).toEqual([
      '1',
      '2',
      'uncovered',
    ]);
    expect(plain(coverage.querySelector('.cost-legend__attention')?.textContent)).toContain(
      'Ongedekt € 3.000 (20%)',
    );
    expect(plain(coverage.querySelector('[role="img"]')?.getAttribute('aria-label'))).toBe(
      'Gedekt € 12.000 (80%), ongedekt € 3.000 (20%)',
    );
  });

  it('lists the invoices in the order of time, the expected one marked', async () => {
    const { page } = await renderPage(ITEM);
    const table = page.querySelectorAll('nldd-table')[0] as HTMLElement;
    const rows = [...table.querySelectorAll('nldd-table-row:not([slot])')];
    expect(rows.map((row) => row.querySelector('nldd-link')?.getAttribute('text'))).toEqual([
      'HOST-26-01',
      'HOST-26-02',
      'HOST-26-03',
    ]);
    expect(rows.map((row) => row.querySelector('nldd-badge')?.getAttribute('text') ?? null)).toEqual([
      null,
      null,
      'Verwacht',
    ]);
  });

  it('shows a document as a download, and says it is missing only on a received invoice', async () => {
    const { page } = await renderPage(ITEM);
    const table = page.querySelectorAll('nldd-table')[0] as HTMLElement;
    const download = table.querySelector('nldd-link[start-icon="download"]');
    expect(download?.getAttribute('href')).toBe('/api/costs/c-1/invoice-lines/l-1/attachments/a-1');
    expect(download?.getAttribute('accessible-label')).toBe('Download factuur-januari.pdf, 84 kB');
    const missing = texts(table, 'nldd-table-row:not([slot]) nldd-text-cell[color="secondary"][size="sm"]');
    expect(missing).toEqual(['Bijlage ontbreekt', '']);
    expect(page.innerHTML).not.toContain('Geen bijlage');
  });

  it('has one primary action and opens no form by default', async () => {
    const { page } = await renderPage(ITEM);
    const primary = [...page.querySelectorAll('nldd-button[appearance="primary"]')];
    expect(primary.map((el) => el.getAttribute('text'))).toEqual(['Voeg factuur toe']);
    expect(openSheet()).toBeNull();
    expect(page.querySelector('nldd-table nldd-button')).toBeNull();
    expect(texts(page, 'nldd-title[heading-level="2"]')).toEqual(['Facturen', 'Dekking']);
  });

  it('opens an invoice from its row, with its attachments, and validates on submit', async () => {
    const { page, calls } = await renderPage(ITEM);
    fireEvent.click(page.querySelector('nldd-table nldd-link[text="HOST-26-01"]') as Element);
    await waitFor(() => expect(openSheet()).not.toBeNull());
    const sheet = openSheet() as HTMLElement;
    expect(sheet.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe('Factuur HOST-26-01');
    expect(sheet.querySelector('nldd-list nldd-link')?.getAttribute('text')).toBe('factuur-januari.pdf');
    expect(sheet.querySelector('nldd-file-field')).not.toBeNull();
    expect(sheet.querySelector('nldd-banner')).toBeNull();

    fireEvent.click(button(page, 'Voeg factuur toe') as Element);
    await waitFor(() =>
      expect(openSheet()?.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe('Nieuwe factuur'),
    );
    const form = openSheet()?.querySelector('nldd-form') as HTMLElement;
    fireEvent(form, new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(openSheet()?.querySelector('nldd-banner')?.getAttribute('text')).toBe(
        'Vul een bedrag in euro in.',
      ),
    );
    expect(calls.some((call) => call.method === 'POST')).toBe(false);
  });

  it('asks before deleting an invoice and says what goes with it', async () => {
    const { page, calls } = await renderPage(ITEM);
    const item = [...page.querySelectorAll('nldd-menu-item')].find(
      (el) => el.getAttribute('text') === 'Verwijder factuur',
    ) as HTMLElement;
    expect(item.hasAttribute('destructive')).toBe(true);
    fireEvent(item, new Event('select'));
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);
    const dialog = [...document.body.querySelectorAll('nldd-modal-dialog[open]')].find((el) =>
      el.getAttribute('text')?.includes("Factuur 'HOST-26-01'"),
    ) as HTMLElement;
    expect(dialog.getAttribute('supporting-text')).toContain('1 bijlage wordt mee verwijderd');
    fireEvent.click(button(dialog, 'Verwijder factuur') as Element);
    await waitFor(() =>
      expect(calls).toContainEqual(
        expect.objectContaining({ method: 'DELETE', url: '/api/costs/c-1/invoice-lines/l-1' }),
      ),
    );
  });

  it('names per share the assignment and its budget line, with a way to its finances', async () => {
    const { page } = await renderPage(ITEM);
    const table = page.querySelectorAll('nldd-table')[1] as HTMLElement;
    const links = [...table.querySelectorAll('nldd-link')];
    expect(links.map((el) => el.getAttribute('text'))).toEqual([
      'Opdracht Alfa 2026',
      'Opdracht Delta 2026-2027',
    ]);
    expect(links[0]?.getAttribute('href')).toBe('/opdrachten/as-1/financieel');
    expect(table.textContent).toContain('Hosting en licenties');
    expect(table.textContent).toContain('Ongedekt');
    // Only the share on an assignment the reader manages can be changed.
    const menus = [...table.querySelectorAll('nldd-icon-button')];
    expect(menus).toHaveLength(1);
  });

  it('starts dividing the remainder from the share nobody covers', async () => {
    const { page, calls } = await renderPage(ITEM);
    await waitFor(() => expect(button(page, 'Verdeel het restant')).toBeDefined());
    fireEvent.click(button(page, 'Verdeel het restant') as Element);
    await waitFor(() => expect(openSheet()).not.toBeNull());
    const sheet = openSheet() as HTMLElement;
    expect(sheet.querySelector('nldd-text-field')?.getAttribute('value')).toBe('20');
    expect(texts(sheet, 'nldd-button')).toEqual(['Leg dekking vast']);
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
  });

  it('shows a refusal of the server at the share field', async () => {
    const refusal = 'De dekking van deze kostenpost komt op 110 procent; meer dan 100 kan niet.';
    const { page, calls } = await renderPage(ITEM, { status: 422, detail: refusal });
    const change = [...page.querySelectorAll('nldd-menu-item')].find(
      (el) => el.getAttribute('text') === 'Wijzig aandeel',
    ) as HTMLElement;
    fireEvent(change, new Event('select'));
    await waitFor(() => expect(openSheet()).not.toBeNull());
    const sheet = openSheet() as HTMLElement;
    expect(sheet.querySelector('nldd-text-field')?.getAttribute('value')).toBe('30');
    fireEvent(sheet.querySelector('nldd-form') as HTMLElement, new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-validation-item')?.textContent).toBe(refusal),
    );
    expect(sheet.querySelector('nldd-text-field')?.hasAttribute('invalid')).toBe(true);
    expect(sheet.querySelector('nldd-banner')).toBeNull();
  });

  it('offers a reader no action and says once who can change', async () => {
    const { page } = await renderPage({
      ...ITEM,
      may_edit: false,
      coverages: ITEM.coverages.map((coverage) => ({ ...coverage, may_edit: false })),
    });
    expect(page.querySelector('nldd-toolbar nldd-button')).toBeNull();
    expect(page.querySelector('nldd-icon-button')).toBeNull();
    expect(page.querySelector('nldd-table nldd-link[href="#"]')).toBeNull();
    expect(page.textContent).toContain(
      'Wijzigen kan een manager van een opdracht die de kostenpost dekt, of de beheerder.',
    );
    // The document itself stays within reach.
    expect(page.querySelector('nldd-link[start-icon="download"]')).not.toBeNull();
  });
});
