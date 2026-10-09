import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import type { CostItem } from './api';
import { CostsPage } from './CostsPage';

const ITEM: CostItem = {
  id: 'c-1',
  description: 'Hostingcontract',
  budgeted_cents: 1600000,
  forecast_cents: 1500000,
  actual_cents: 1000000,
  estimate_cents: 500000,
  variance_cents: 100000,
  covered_cents: 1500000,
  uncovered_cents: 0,
  pct_total: '100.00',
  uncovered_pct: '0.00',
  hidden_coverage_pct: '0',
  invoice_lines: [],
  coverages: [],
  may_edit: false,
};

const UNCOVERED = {
  ...ITEM,
  id: 'c-2',
  description: 'Licenties',
  covered_cents: 450000,
  uncovered_cents: 1050000,
  pct_total: '30.00',
  uncovered_pct: '70.00',
};

afterEach(() => vi.unstubAllGlobals());

async function renderCosts(body: object, path = '/kosten') {
  const api = mockApi({ '/api/costs': body, '/api/costs/coverage-options': { items: [] } });
  const view = renderApp(<CostsPage />, { path });
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return { container: view.container, calls: api.calls };
}

/** Amounts carry a non-breaking space after the euro sign; read them with a plain one. */
const plain = (text: string | null | undefined) => (text ?? '').replace(/\u00a0/g, ' ');

const names = (container: ParentNode) => texts(container, 'nldd-table nldd-link');

describe('CostsPage', () => {
  it('shows per cost item the expected total against the budget and the coverage', async () => {
    const { container } = await renderCosts({ items: [ITEM], year: null, may_create: false });
    const link = container.querySelector('nldd-table nldd-link');
    expect(link?.getAttribute('text')).toBe('Hostingcontract');
    expect(link?.getAttribute('href')).toBe('/kosten/c-1');
    const cells = [...container.querySelectorAll('nldd-table nldd-text-cell')];
    expect(cells.some((cell) => cell.getAttribute('text')?.includes('15.000'))).toBe(true);
    expect(
      cells.some((cell) => plain(cell.getAttribute('supporting-text')) === 'van € 16.000 begroot'),
    ).toBe(true);
    expect(container.textContent).toContain('100% gedekt');
    expect(container.querySelector('.cost-mini [data-kind="uncovered"]')).toBeNull();
  });

  it('keeps the order of the server and says what needs attention', async () => {
    // The server puts what needs attention first; the page does not reorder.
    const overrun = { ...ITEM, id: 'c-3', description: 'Advies', variance_cents: -100000 };
    const { container } = await renderCosts({
      items: [UNCOVERED, overrun, ITEM],
      year: null,
      may_create: false,
    });
    expect(names(container)).toEqual(['Licenties', 'Advies', 'Hostingcontract']);
    expect(plain(container.textContent)).toContain('€ 10.500 ongedekt');
    expect(container.textContent).toContain('Overschrijding');
    expect(container.querySelector('.cost-mini [data-kind="uncovered"]')).not.toBeNull();
    expect(container.querySelectorAll('nldd-text-cell[color="critical"]')).toHaveLength(1);
  });

  it('counts a received invoice without its document as attention', async () => {
    const line = {
      id: 'l-1',
      reference: 'HOST-26-01',
      description: null,
      kind: 'actual' as const,
      amount_cents: 1000000,
      period: '2026-03-01',
      attachments: [],
    };
    const { container } = await renderCosts({
      items: [{ ...ITEM, id: 'c-4', description: 'Zonder bijlage', invoice_lines: [line] }, ITEM],
      year: null,
      may_create: false,
    });
    expect(names(container)).toEqual(['Zonder bijlage', 'Hostingcontract']);
    expect(container.textContent).toContain('1 factuur zonder bijlage');
  });

  it('asks for one page and shows where the reader is in a long list', async () => {
    const { container, calls } = await renderCosts(
      { items: [ITEM], total: 120, page: 2, page_size: 50, year: null, may_create: false },
      '/kosten?pagina=2&zoek=host',
    );
    expect(calls.some((call) => call.includes('page=2') && call.includes('q=host'))).toBe(true);
    expect(container.querySelector('[data-page-range]')?.textContent).toBe(
      '51 tot en met 100 van 120 kostenposten',
    );
    const pager = container.querySelector('nldd-pagination');
    expect(pager).toHaveAttribute('current', '2');
    expect(pager).toHaveAttribute('total', '3');
    // The other pages keep the search; the first page has the plain address.
    expect(pager).toHaveAttribute('href-pattern', '/kosten?pagina={page}&zoek=host');
  });

  it('shows no pages for a list that fits on one', async () => {
    const { container } = await renderCosts({
      items: [ITEM],
      total: 1,
      page: 1,
      page_size: 50,
      year: null,
      may_create: false,
    });
    expect(container.querySelector('[data-page-range]')).toBeNull();
    expect(container.querySelector('nldd-pagination')).toBeNull();
  });

  it('offers one primary action, and only to who may add a cost item', async () => {
    const reader = await renderCosts({ items: [ITEM], year: null, may_create: false });
    expect(texts(reader.container, 'nldd-button')).toEqual([]);
    vi.unstubAllGlobals();
    const { container } = await renderCosts({ items: [ITEM], year: null, may_create: true });
    const buttons = [...container.querySelectorAll('nldd-button')];
    expect(buttons.map((button) => button.getAttribute('text'))).toEqual(['Nieuwe kostenpost']);
    expect(buttons[0]?.getAttribute('appearance')).toBe('primary');
    // No form is open, and no row carries a button.
    expect(container.querySelector('nldd-table nldd-button')).toBeNull();
    expect(document.body.querySelector('nldd-sheet[open]')).toBeNull();
  });

  it('asks for the year in the address and carries it to the cost item', async () => {
    const { container, calls } = await renderCosts(
      { items: [ITEM], year: 2026, may_create: false },
      '/kosten?jaar=2026',
    );
    expect(calls.some((url) => url.includes('year=2026'))).toBe(true);
    expect(container.querySelector('nldd-table nldd-link')?.getAttribute('href')).toBe(
      '/kosten/c-1?jaar=2026',
    );
  });

  it('explains an empty list', async () => {
    const { container } = await renderCosts({ items: [], year: null, may_create: false });
    expect(texts(container, 'nldd-inline-dialog[slot="empty"]')).toEqual([
      'Er zijn geen kostenposten om te tonen',
    ]);
  });
});
