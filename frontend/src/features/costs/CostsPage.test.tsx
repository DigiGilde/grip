import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import { CostsPage } from './CostsPage';

const ITEM = {
  id: 'c-1',
  description: 'Hostingcontract',
  budgeted_cents: 1600000,
  forecast_cents: 1500000,
  actual_cents: 1000000,
  estimate_cents: 500000,
  covered_cents: 450000,
  uncovered_cents: 1050000,
  pct_total: '30.00',
  hidden_coverage_pct: '0',
  invoice_lines: [],
  coverages: [],
  may_edit: false,
};

afterEach(() => vi.unstubAllGlobals());

async function renderCosts(body: object) {
  mockApi({ '/api/costs': body, '/api/costs/coverage-options': { items: [] } });
  const view = renderApp(<CostsPage />, { path: '/kosten' });
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return view.container;
}

describe('CostsPage', () => {
  it('shows budgeted, forecast, covered and the uncovered remainder', async () => {
    const container = await renderCosts({ items: [ITEM], year: null, may_create: false });
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('Hostingcontract');
    expect(cells.some((text) => text.includes('16.000'))).toBe(true);
    expect(cells.some((text) => text.includes('15.000'))).toBe(true);
    expect(cells.some((text) => text.includes('4.500'))).toBe(true);
    expect(cells.some((text) => text.includes('10.500'))).toBe(true);
    expect(cells).toContain('30%');
    expect(texts(container, 'nldd-button')).not.toContain('Kostenpost toevoegen');
  });

  it('says unknown instead of an amount when the shares exceed 100 percent', async () => {
    const container = await renderCosts({
      items: [{ ...ITEM, covered_cents: null, uncovered_cents: null, pct_total: '120.00' }],
      year: null,
      may_create: true,
    });
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells.filter((text) => text === 'Onbekend')).toHaveLength(2);
    expect(texts(container, 'nldd-button')).toContain('Kostenpost toevoegen');
  });

  it('flags a forecast above the budget', async () => {
    const container = await renderCosts({
      items: [{ ...ITEM, forecast_cents: 1700000 }],
      year: null,
      may_create: false,
    });
    const flagged = container.querySelector('nldd-text-cell[color="critical"]');
    expect(flagged?.getAttribute('supporting-text')).toBe('Boven begroting');
  });

  it('explains an empty list', async () => {
    const container = await renderCosts({ items: [], year: null, may_create: false });
    expect(texts(container, 'nldd-inline-dialog[slot="empty"]')).toEqual([
      'Er zijn geen kostenposten om te tonen',
    ]);
  });
});
