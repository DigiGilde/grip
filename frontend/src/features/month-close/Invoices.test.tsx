import { useQuery } from '@tanstack/react-query';
import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/quotes/testing';
import { renderApp } from '@/test/utils';
import type { BillingStatus, MonthBilling, OutgoingInvoice } from './api';
import { BillingTotals, Invoices } from './BillingSection';
import { monthClosePath, monthsFromParam, recordInvoicePath } from './paths';

const DELIVERED: MonthBilling = {
  month: '2026-02',
  closed: true,
  state: 'delivered',
  deliverable_cents: 1440000,
  to_deliver_cents: 0,
  export_id: 'e-2',
  delivered_at: '2026-03-02T09:00:00Z',
  delivered_by_name: 'Opdracht Manager',
  delivered_cents: 1440000,
  invoice_id: null,
  invoice_number: null,
  invoice_date: null,
  invoiced_cents: null,
  invoice_on_earlier_delivery: false,
};

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

function status(overrides: Partial<BillingStatus> = {}): BillingStatus {
  return {
    assignment_id: 'a-1',
    year: null,
    billable: true,
    may_record_invoice: true,
    deliverable_cents: 2880000,
    delivered_cents: 2880000,
    to_deliver_cents: 0,
    invoiced_cents: 1430000,
    to_invoice_cents: 1450000,
    months: [DELIVERED],
    invoices: [INVOICE],
    ...overrides,
  };
}

afterEach(() => vi.unstubAllGlobals());

const openSheet = () =>
  [...document.body.querySelectorAll('nldd-sheet')].find((el) => el.hasAttribute('open'));

describe('Invoices', () => {
  it('shows the difference between an invoice and what was delivered', () => {
    const { container } = renderApp(
      <Invoices assignmentId="a-1" status={status()} recordFor={null} onRecordDone={() => {}} />,
    );
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('F-2026-001');
    expect(cells.some((text) => /^€\s100 minder dan aangeleverd$/.test(text))).toBe(true);
    // The row has one quiet menu, not two buttons.
    expect(texts(container, 'nldd-button')).toEqual([]);
    expect(texts(container, 'nldd-menu-item')).toEqual(['Corrigeer', 'Trek in']);
    // No form is open by default.
    expect(openSheet()).toBeUndefined();
  });

  it('gives a reader the facts without the actions', () => {
    const { container } = renderApp(
      <Invoices
        assignmentId="a-1"
        status={status({ may_record_invoice: false })}
        recordFor={['2026-02']}
        onRecordDone={() => {}}
      />,
    );
    expect(texts(container, 'nldd-button')).toEqual([]);
    expect(openSheet()).toBeUndefined();
  });

  it('records an invoice for the requested month with the amount as typed', async () => {
    const { calls } = mockApi({
      '/api/assignments/a-1/outgoing-invoices/proposal?export_id=e-2': {
        months: ['2026-02'],
        delivered_cents: 1440000,
      },
      'POST /api/assignments/a-1/outgoing-invoices': status({ invoiced_cents: 2870000 }),
    });
    const done = vi.fn();
    renderApp(
      <Invoices assignmentId="a-1" status={status()} recordFor={['2026-02']} onRecordDone={done} />,
    );
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    expect(sheet.textContent).toContain('februari 2026, aangeleverd');
    // The amount field proposes what was delivered, added up by the server.
    await waitFor(() =>
      expect(
        [...sheet.querySelectorAll('nldd-text-field')].map((el) => el.getAttribute('value')),
      ).toContain('14400'),
    );
    const fields = [...sheet.querySelectorAll('nldd-text-field')];
    fields[0]?.dispatchEvent(new CustomEvent('input', { detail: { value: 'F-2026-002' } }));
    sheet
      .querySelector('nldd-date-field')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: '2026-04-10' } }));
    fields[1]?.dispatchEvent(new CustomEvent('input', { detail: { value: '14.300,00' } }));
    await waitFor(() => expect(fields[1]?.getAttribute('value')).toBe('14.300,00'));
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      export_ids: ['e-2'],
      invoice_number: 'F-2026-002',
      invoice_date: '2026-04-10',
      amount_cents: 1430000,
      note: null,
    });
    await waitFor(() => expect(done).toHaveBeenCalled());
  });

  it('keeps a withdrawn invoice in sight with the reason', () => {
    const { container } = renderApp(
      <Invoices
        assignmentId="a-1"
        status={status({
          invoices: [
            {
              ...INVOICE,
              withdrawn_at: '2026-04-05T10:00:00Z',
              withdrawn_by_name: 'Opdracht Manager',
              withdrawn_reason: 'Bij de verkeerde opdracht vastgelegd',
            },
          ],
        })}
        recordFor={null}
        onRecordDone={() => {}}
      />,
    );
    expect(texts(container, 'nldd-title')).toEqual(['Ingetrokken facturen']);
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain(
      'Bij de verkeerde opdracht vastgelegd',
    );
  });
});

/** Stands in for the figures at the top of Afsluiten, which live under ['overview']. */
function OverviewProbe() {
  useQuery({
    queryKey: ['overview', 'probe'],
    queryFn: () => fetch('/api/overview-probe').then((response) => response.json()),
  });
  return null;
}

const probeCalls = (calls: { url: string }[]) =>
  calls.filter((call) => call.url === '/api/overview-probe').length;

describe('the figures of the overview after an invoice action', () => {
  const replies = {
    '/api/overview-probe': {},
    'POST /api/assignments/a-1/outgoing-invoices': status(),
    'PATCH /api/outgoing-invoices/i-1': status(),
    'POST /api/outgoing-invoices/i-1/withdraw': status(),
    '/api/assignments/a-1/outgoing-invoices/proposal?export_id=e-2': {
      months: ['2026-02'],
      delivered_cents: 1440000,
    },
  };

  const submit = () =>
    (openSheet() as Element)
      .querySelector('nldd-form')
      ?.dispatchEvent(new Event('submit', { cancelable: true }));

  it('asks for them again after recording an invoice', async () => {
    const { calls } = mockApi(replies);
    renderApp(
      <>
        <OverviewProbe />
        <Invoices
          assignmentId="a-1"
          status={status()}
          recordFor={['2026-02']}
          onRecordDone={() => {}}
        />
      </>,
    );
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    await waitFor(() =>
      expect(
        [...sheet.querySelectorAll('nldd-text-field')].map((el) => el.getAttribute('value')),
      ).toContain('14400'),
    );
    const fields = [...sheet.querySelectorAll('nldd-text-field')];
    fields[0]?.dispatchEvent(new CustomEvent('input', { detail: { value: 'F-2026-002' } }));
    sheet
      .querySelector('nldd-date-field')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: '2026-04-10' } }));
    await waitFor(() => expect(fields[0]?.getAttribute('value')).toBe('F-2026-002'));
    expect(probeCalls(calls)).toBe(1);
    submit();
    await waitFor(() => expect(probeCalls(calls)).toBe(2));
  });

  it('asks for them again after withdrawing an invoice', async () => {
    const { calls } = mockApi(replies);
    const { container } = renderApp(
      <>
        <OverviewProbe />
        <Invoices assignmentId="a-1" status={status()} recordFor={null} onRecordDone={() => {}} />
      </>,
    );
    container.querySelector('nldd-menu-item[text="Trek in"]')?.dispatchEvent(new Event('select'));
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    const reason = sheet.querySelector('nldd-multi-line-text-field') as Element;
    expect(reason).not.toBeNull();
    reason.dispatchEvent(new CustomEvent('input', { detail: { value: 'Verkeerde opdracht' } }));
    await waitFor(() => expect(reason.getAttribute('value')).toBe('Verkeerde opdracht'));
    expect(probeCalls(calls)).toBe(1);
    submit();
    await waitFor(() => expect(probeCalls(calls)).toBe(2));
  });

  it('asks for them again after correcting an invoice', async () => {
    const { calls } = mockApi(replies);
    const { container } = renderApp(
      <>
        <OverviewProbe />
        <Invoices assignmentId="a-1" status={status()} recordFor={null} onRecordDone={() => {}} />
      </>,
    );
    container.querySelector('nldd-menu-item[text="Corrigeer"]')?.dispatchEvent(new Event('select'));
    await waitFor(() => expect(openSheet()).toBeDefined());
    expect(probeCalls(calls)).toBe(1);
    submit();
    await waitFor(() => expect(probeCalls(calls)).toBe(2));
  });
});

describe('BillingTotals', () => {
  it('never calls a delivered amount invoiced', () => {
    const { container } = renderApp(
      <BillingTotals
        status={status({ invoiced_cents: 0, to_invoice_cents: 2880000, invoices: [] })}
      />,
    );
    const figures = texts(container, 'nldd-table-row:not([slot]) nldd-text-cell');
    expect(figures[0]).toContain('28.800');
    expect(figures[2]).toMatch(/^€\s0$/);
    expect(figures[3]).toContain('28.800');
  });

  it('is absent for someone who may not see the amounts', () => {
    const { container } = renderApp(
      <BillingTotals
        status={{ assignment_id: 'a-1', year: null, billable: true, may_record_invoice: false }}
      />,
    );
    expect(container.querySelector('nldd-table')).toBeNull();
  });
});

describe('addresses of the steps', () => {
  it('lands on closing one month, and on recording an invoice for some', () => {
    expect(monthClosePath('a-1', '2026-09')).toBe('/opdrachten/a-1/afsluiten?maand=2026-09');
    expect(recordInvoicePath('a-1', ['2026-01', '2026-02'])).toBe(
      '/opdrachten/a-1/afsluiten?factuur=2026-01,2026-02',
    );
    expect(monthsFromParam('2026-01,onzin,2026-02')).toEqual(['2026-01', '2026-02']);
    expect(monthsFromParam(null)).toEqual([]);
  });
});
