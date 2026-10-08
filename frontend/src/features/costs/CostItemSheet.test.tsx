import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import type { CostItem } from './api';
import { CostItemSheet } from './CostItemSheet';

const LINE = {
  id: 'l-1',
  reference: 'HOST-26-01',
  description: null,
  kind: 'actual' as const,
  amount_cents: 1000000,
  period: '2026-03-01',
  attachments: [
    {
      id: 'a-1',
      filename: 'factuur-maart.pdf',
      content_type: 'application/pdf',
      size_bytes: 86016,
      uploaded_at: '2026-04-02T09:00:00Z',
      uploaded_by_name: 'Olga Opdrachteigenaar',
    },
  ],
};

const ITEM: CostItem = {
  id: 'c-1',
  description: 'Hostingcontract',
  budgeted_cents: 1600000,
  forecast_cents: 1500000,
  actual_cents: 1000000,
  estimate_cents: 500000,
  variance_cents: 100000,
  covered_cents: 450000,
  uncovered_cents: 1050000,
  pct_total: '30.00',
  hidden_coverage_pct: '0',
  invoice_lines: [LINE, { ...LINE, id: 'l-2', reference: 'HOST-26-02', attachments: [] }],
  coverages: [],
  may_edit: true,
};

afterEach(() => vi.unstubAllGlobals());

function renderSheet(item: CostItem) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ method: init?.method ?? 'GET', url: String(input) });
      return Promise.resolve(
        new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  renderApp(<CostItemSheet item={item} onClose={() => {}} />);
  return { sheet: document.body.querySelector('nldd-sheet') as HTMLElement, calls };
}

const button = (root: ParentNode, text: string) =>
  [...root.querySelectorAll('nldd-button')].find((el) => el.getAttribute('text') === text);

describe('CostItemSheet', () => {
  it('shows what is there and opens no form by default', () => {
    const { sheet } = renderSheet(ITEM);
    expect(sheet.querySelector('form')).toBeNull();
    expect(sheet.querySelector('nldd-banner')).toBeNull();
    expect(texts(sheet, 'nldd-container > nldd-title[heading-level="2"]')).toEqual([
      'Bedragen',
      'Facturen',
      'Dekking',
    ]);
    expect(texts(sheet, 'nldd-title nldd-button')).toEqual(['Wijzig gegevens', 'Voeg factuur toe']);
  });

  it('uses the money words of the glossary', () => {
    const { sheet } = renderSheet(ITEM);
    const cells = texts(sheet, 'nldd-table nldd-text-cell');
    for (const word of ['Begroot', 'Gerealiseerd', 'Nog gepland', 'Verwacht totaal', 'Afwijking']) {
      expect(cells).toContain(word);
    }
    expect(sheet.innerHTML.toLowerCase()).not.toContain('prognose');
  });

  it('shows per invoice whether the invoice itself is attached, as a download', () => {
    const { sheet } = renderSheet(ITEM);
    const link = sheet.querySelector('nldd-link');
    expect(link?.getAttribute('text')).toBe('factuur-maart.pdf');
    expect(link?.getAttribute('href')).toBe('/api/costs/c-1/invoice-lines/l-1/attachments/a-1');
    expect(link?.getAttribute('accessible-label')).toBe('Download factuur-maart.pdf, 84 kB');
    expect(texts(sheet, 'nldd-table nldd-text-cell')).toContain('Geen bijlage');
  });

  it('opens the fields of a new invoice from an action and validates on submit', async () => {
    const { sheet, calls } = renderSheet(ITEM);
    fireEvent.click(button(sheet, 'Voeg factuur toe') as Element);
    await waitFor(() => expect(sheet.querySelector('form')).not.toBeNull());
    // The attachment is part of the same step.
    expect(sheet.querySelector('nldd-file-field')).not.toBeNull();
    expect(sheet.querySelector('nldd-banner')).toBeNull();
    expect(button(sheet, 'Annuleer')).toBeDefined();

    fireEvent.submit(sheet.querySelector('form') as HTMLFormElement);
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner')?.getAttribute('text')).toBe(
        'Vul een bedrag in euro in.',
      ),
    );
    expect(calls.some((call) => call.method === 'POST')).toBe(false);

    fireEvent.click(button(sheet, 'Annuleer') as Element);
    await waitFor(() => expect(sheet.querySelector('form')).toBeNull());
  });

  it('lets an invoice be corrected, with its attachments listed', async () => {
    const { sheet } = renderSheet(ITEM);
    const edit = [...sheet.querySelectorAll('nldd-button')].find(
      (el) => el.getAttribute('accessible-label') === 'Wijzig factuur HOST-26-01',
    );
    fireEvent.click(edit as Element);
    await waitFor(() => expect(sheet.querySelector('form')).not.toBeNull());
    const amount = sheet.querySelector('nldd-text-field');
    expect(amount).not.toBeNull();
    const cells = texts(sheet, 'nldd-table nldd-text-cell');
    expect(cells).toContain('84 kB');
    expect(
      [...sheet.querySelectorAll('nldd-table nldd-text-cell')].some((cell) =>
        cell.getAttribute('supporting-text')?.includes('Olga Opdrachteigenaar'),
      ),
    ).toBe(true);
    expect(button(sheet, 'Bewaar factuur')).toBeDefined();
  });

  it('asks before deleting an invoice that has an attachment', async () => {
    const { sheet, calls } = renderSheet(ITEM);
    fireEvent.click(
      [...sheet.querySelectorAll('nldd-button')].find(
        (el) => el.getAttribute('accessible-label') === 'Wijzig factuur HOST-26-01',
      ) as Element,
    );
    await waitFor(() => expect(button(sheet, 'Verwijder deze factuur')).toBeDefined());
    fireEvent.click(button(sheet, 'Verwijder deze factuur') as Element);
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);
    const dialog = [...document.body.querySelectorAll('nldd-modal-dialog')].find((el) =>
      el.getAttribute('text')?.includes("Factuur 'HOST-26-01'"),
    ) as HTMLElement;
    expect(dialog.getAttribute('supporting-text')).toContain('1 bijlage wordt mee verwijderd');
    fireEvent.click(button(dialog, 'Verwijder factuur') as Element);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'DELETE',
        url: '/api/costs/c-1/invoice-lines/l-1',
      }),
    );
  });

  it('offers nothing that changes to a reader', () => {
    const { sheet } = renderSheet({ ...ITEM, may_edit: false });
    expect(texts(sheet, 'nldd-button')).toEqual([]);
    expect(sheet.querySelector('nldd-link')).not.toBeNull();
  });
});
