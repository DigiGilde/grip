import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { clickButton, mockApi, texts } from '@/features/quotes/testing';
import { renderApp } from '@/test/utils';
import type { BillingStatus, MonthBilling, OutgoingInvoice } from './api';
import { BillingSection } from './BillingSection';

function month(overrides: Partial<MonthBilling>): MonthBilling {
  return {
    month: '2026-01',
    closed: true,
    state: 'not_delivered',
    deliverable_cents: 1440000,
    to_deliver_cents: 1440000,
    export_id: null,
    delivered_at: null,
    delivered_by_name: null,
    delivered_cents: null,
    invoice_id: null,
    invoice_number: null,
    invoice_date: null,
    invoiced_cents: null,
    invoice_on_earlier_delivery: false,
    ...overrides,
  };
}

const DELIVERED = month({
  month: '2026-02',
  state: 'delivered',
  to_deliver_cents: 0,
  export_id: 'e-2',
  delivered_at: '2026-03-02T09:00:00Z',
  delivered_by_name: 'Opdracht Manager',
  delivered_cents: 1440000,
});

const INVOICE: OutgoingInvoice = {
  id: 'i-1',
  invoice_number: 'F-2026-001',
  invoice_date: '2026-04-03',
  amount_cents: 1430000,
  delivered_cents: 1440000,
  difference_cents: -10000,
  months: ['2026-03'],
  export_ids: ['e-3'],
  source: 'manual',
  note: null,
  recorded_at: '2026-04-04T10:00:00Z',
  recorded_by_name: 'Opdracht Manager',
  withdrawn_at: null,
  withdrawn_by_name: null,
  withdrawn_reason: null,
};

const INVOICED = month({
  month: '2026-03',
  state: 'invoiced',
  to_deliver_cents: 0,
  export_id: 'e-3',
  delivered_at: '2026-04-01T09:00:00Z',
  delivered_cents: 1440000,
  invoice_id: 'i-1',
  invoice_number: 'F-2026-001',
  invoice_date: '2026-04-03',
  invoiced_cents: 1430000,
});

function status(overrides: Partial<BillingStatus> = {}): BillingStatus {
  return {
    assignment_id: 'a-1',
    year: null,
    billable: true,
    may_record_invoice: true,
    deliverable_cents: 4320000,
    delivered_cents: 2880000,
    to_deliver_cents: 1440000,
    invoiced_cents: 1430000,
    to_invoice_cents: 1450000,
    months: [month({}), DELIVERED, INVOICED],
    invoices: [INVOICE],
    ...overrides,
  };
}

afterEach(() => vi.unstubAllGlobals());

async function renderSection(value: object, replies: Record<string, unknown> = {}) {
  const api = mockApi({ '/api/assignments/a-1/billing-status': value, ...replies });
  const view = renderApp(<BillingSection assignmentId="a-1" />);
  await waitFor(() => expect(view.container.textContent).not.toContain('Bezig met laden'));
  return { ...api, container: view.container };
}

describe('BillingSection', () => {
  it('says per month in words whether it was delivered or invoiced', async () => {
    const { container } = await renderSection(status());
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('Niet aangeleverd');
    expect(cells.some((text) => text.startsWith('Aangeleverd op 2 mrt 2026'))).toBe(true);
    expect(cells).toContain('Gefactureerd met nummer F-2026-001 op 3 apr 2026');
    expect(texts(container, 'nldd-badge')).toEqual([
      'Niet aangeleverd',
      'Aangeleverd',
      'Gefactureerd',
    ]);
  });

  it('never calls a delivered amount invoiced', async () => {
    const { container } = await renderSection(
      status({
        invoiced_cents: 0,
        to_invoice_cents: 2880000,
        months: [DELIVERED, { ...DELIVERED, month: '2026-03', export_id: 'e-3' }],
        invoices: [],
      }),
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const totals = container.querySelector(
      'nldd-table[accessible-label^="Aangeleverd en gefactureerd"]',
    );
    const figures = texts(totals as Element, 'nldd-table-row:not([slot]) nldd-text-cell');
    // Aangeleverd, nog aan te leveren, gefactureerd, nog te factureren.
    expect(figures[0]).toContain('28.800');
    expect(figures[2]).toMatch(/^€\s0$/);
    expect(figures[3]).toContain('28.800');
    expect(texts(container, 'nldd-badge')).toEqual(['Aangeleverd', 'Aangeleverd']);
    expect(
      [...container.querySelectorAll('nldd-inline-dialog')].map((el) =>
        el.getAttribute('supporting-text'),
      ),
    ).toContain('Tot die tijd telt geen enkel bedrag van deze opdracht als gefactureerd.');
  });

  it('shows the difference between an invoice and what was delivered', async () => {
    const { container } = await renderSection(status());
    await waitFor(() =>
      expect(texts(container, 'nldd-table nldd-text-cell')).toContain('F-2026-001'),
    );
    expect(
      texts(container, 'nldd-table nldd-text-cell').some((text) =>
        /^€\s100 minder dan aangeleverd$/.test(text),
      ),
    ).toBe(true);
  });

  it('offers only delivered months without an invoice for a new invoice', async () => {
    const { container } = await renderSection(status());
    await waitFor(() => expect(container.querySelector('nldd-checkbox')).not.toBeNull());
    const labels = [...container.querySelectorAll('nldd-checkbox')].map((el) =>
      el.getAttribute('accessible-label'),
    );
    expect(labels).toEqual(['Kies februari 2026 voor een factuur']);
    const record = [...container.querySelectorAll('nldd-button')].find(
      (el) => el.getAttribute('text') === 'Leg factuur vast',
    );
    // Nothing chosen yet.
    expect(record?.hasAttribute('disabled')).toBe(true);
  });

  it('records an invoice for the chosen months with the amount as typed', async () => {
    const { container, calls } = await renderSection(status(), {
      '/api/assignments/a-1/outgoing-invoices/proposal?export_id=e-2': {
        months: ['2026-02'],
        delivered_cents: 1440000,
      },
      'POST /api/assignments/a-1/outgoing-invoices': status({ invoiced_cents: 2870000 }),
    });
    await waitFor(() => expect(container.querySelector('nldd-checkbox')).not.toBeNull());
    container
      .querySelector('nldd-checkbox')
      ?.dispatchEvent(new CustomEvent('change', { detail: { checked: true } }));
    await waitFor(() =>
      expect(container.querySelector('nldd-checkbox')?.hasAttribute('checked')).toBe(true),
    );
    clickButton(container, 'Leg factuur vast');

    const sheet = () =>
      [...document.body.querySelectorAll('nldd-sheet')].find((el) => el.hasAttribute('open'));
    await waitFor(() => expect(sheet()).toBeDefined());
    // The amount field proposes what was delivered, added up by the server.
    await waitFor(() =>
      expect(
        [...(sheet() as Element).querySelectorAll('nldd-text-field')].map((el) =>
          el.getAttribute('value'),
        ),
      ).toContain('14400'),
    );
    const fields = [...(sheet() as Element).querySelectorAll('nldd-text-field')];
    fields[0]?.dispatchEvent(new CustomEvent('input', { detail: { value: 'F-2026-002' } }));
    (sheet() as Element)
      .querySelector('nldd-date-field')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: '2026-04-10' } }));
    fields[1]?.dispatchEvent(new CustomEvent('input', { detail: { value: '14.300,00' } }));
    await waitFor(() => expect(fields[1]?.getAttribute('value')).toBe('14.300,00'));
    (sheet() as Element)
      .querySelector('nldd-form')
      ?.dispatchEvent(new Event('submit', { cancelable: true }));

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      export_ids: ['e-2'],
      invoice_number: 'F-2026-002',
      invoice_date: '2026-04-10',
      amount_cents: 1430000,
      note: null,
    });
  });

  it('gives a reader the facts without the actions', async () => {
    const { container } = await renderSection(status({ may_record_invoice: false }));
    await waitFor(() =>
      expect(texts(container, 'nldd-table nldd-text-cell')).toContain('F-2026-001'),
    );
    expect(container.querySelector('nldd-checkbox')).toBeNull();
    expect(texts(container, 'nldd-button')).toEqual([]);
  });

  it('shows nothing to someone who may not read the amounts', async () => {
    const { container } = await renderSection({
      assignment_id: 'a-1',
      year: null,
      billable: true,
      may_record_invoice: false,
    });
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(container.textContent).not.toContain('€');
    expect(container.textContent).not.toContain('efactureerd');
  });

  it('says so when the month was delivered again after the invoice', async () => {
    const { container } = await renderSection(
      status({ months: [{ ...INVOICED, invoice_on_earlier_delivery: true }] }),
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(
      [...container.querySelectorAll('nldd-text-cell')].map((el) =>
        el.getAttribute('supporting-text'),
      ),
    ).toContain(
      'De factuur hoort bij een eerdere aanlevering; de maand is daarna opnieuw aangeleverd',
    );
  });

  it('keeps a withdrawn invoice in sight with the reason', async () => {
    const { container } = await renderSection(
      status({
        invoiced_cents: 0,
        months: [DELIVERED],
        invoices: [
          {
            ...INVOICE,
            months: [],
            export_ids: [],
            withdrawn_at: '2026-04-05T10:00:00Z',
            withdrawn_by_name: 'Opdracht Manager',
            withdrawn_reason: 'Bij de verkeerde opdracht vastgelegd',
          },
        ],
      }),
    );
    await waitFor(() =>
      expect(texts(container, 'nldd-table nldd-text-cell')).toContain(
        'Bij de verkeerde opdracht vastgelegd',
      ),
    );
    // Withdrawn is not in force: nothing counts as invoiced.
    expect(
      [...container.querySelectorAll('nldd-inline-dialog')].map((el) => el.getAttribute('text')),
    ).toContain('Er is nog geen factuur vastgelegd');
  });
});
