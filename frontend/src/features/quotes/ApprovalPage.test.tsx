import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { ApprovalListPage } from './ApprovalListPage';
import { ApprovalPage } from './ApprovalPage';
import { QuoteSettingsPage } from './QuoteSettingsPage';
import { clickButton, mockApi, texts } from './testing';

const HASH = 'b'.repeat(64);

const APPROVER_QUOTE = {
  quote_id: 'q-1',
  quote_reference: 'VG-2026-0007',
  assignment_id: 'a-1',
  assignment_name: 'Opdracht Alfa',
  client_name: 'Voorbeeldministerie',
  issued_at: '2026-02-01T09:00:00Z',
  issued_by_name: 'Opdracht Manager',
  total_cents: 17280000,
  snapshot_hash: HASH,
  content: {
    name: 'Opdracht Alfa',
    context_refs: [],
    lines: [],
    subtotals_per_year: [],
    total_cents: 17280000,
    conditions: 'Betaling per maand.',
  },
  approval: {
    quote_id: 'q-1',
    approval_required: true,
    status: 'requested',
    may_offer: false,
    approver_available: true,
    may_decide_approval: true,
    current: {
      id: 'r-1',
      status: 'requested',
      requested_at: '2026-02-02T09:30:00Z',
      requested_by_name: 'Opdracht Manager',
      request_note: 'Graag voor vrijdag',
    },
  },
};

afterEach(() => vi.unstubAllGlobals());

const openSheet = () =>
  [...document.body.querySelectorAll('nldd-sheet')].find((el) => el.hasAttribute('open'));

function renderPage(replies: Record<string, unknown>) {
  const { calls } = mockApi(replies);
  const view = renderApp(
    <Routes>
      <Route path="/goedkeuren/:quoteId" element={<ApprovalPage />} />
    </Routes>,
    { path: '/goedkeuren/q-1' },
  );
  return { container: view.container, calls };
}

describe('ApprovalPage', () => {
  it('is the quote, who asks, and one decision', async () => {
    const { container } = renderPage({ '/api/quote-approvals/quotes/q-1': APPROVER_QUOTE });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const amount = container.querySelector('nldd-title[heading-level="2"]');
    expect(amount?.getAttribute('text')).toMatch(/^€\s172\.800$/);
    expect(amount?.getAttribute('overline')).toBe('Ter goedkeuring');
    expect(container.textContent).toContain('Voor Voorbeeldministerie · kenmerk VG-2026-0007');
    expect(container.textContent).toContain('gevraagd door Opdracht Manager');
    expect(container.textContent).toContain('Graag voor vrijdag');
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual(['Keur goed']);
    expect(texts(container, 'nldd-button').filter((text) => text !== 'Details')).toEqual([
      'Keur goed',
      'Stuur terug',
    ]);
    expect(openSheet()).toBeUndefined();
  });

  it('does not send a quote back without saying what must change', async () => {
    const { container, calls } = renderPage({
      '/api/quote-approvals/quotes/q-1': APPROVER_QUOTE,
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    clickButton(container, 'Stuur terug');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text')).toBe(
        'Schrijf op wat er anders moet.',
      ),
    );
    expect(calls.filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('approves the version that was shown', async () => {
    const { container, calls } = renderPage({
      '/api/quote-approvals/quotes/q-1': APPROVER_QUOTE,
      'POST /api/quotes/q-1/approval/decision': { ...APPROVER_QUOTE.approval, status: 'approved' },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    clickButton(container, 'Keur goed');
    await waitFor(() => expect(openSheet()).toBeDefined());
    openSheet()
      ?.querySelector('nldd-form')
      ?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      decision: 'approve',
      quote_hash: HASH,
      note: null,
    });
  });

  it('gives whoever asked no decision on the own quote', async () => {
    const { container } = renderPage({
      '/api/quote-approvals/quotes/q-1': {
        ...APPROVER_QUOTE,
        approval: { ...APPROVER_QUOTE.approval, may_decide_approval: false },
      },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(texts(container, 'nldd-button').filter((text) => text !== 'Details')).toEqual([]);
    expect(container.textContent).toContain('een andere collega beslist');
  });

  it('says nothing about a quote the reader may not approve', async () => {
    const { container } = renderPage({});
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
        'Deze offerte staat niet voor je klaar',
      ),
    );
  });
});

describe('ApprovalListPage', () => {
  it('lists what waits, with the way in', async () => {
    mockApi({
      '/api/quote-approvals/waiting': {
        items: [
          {
            quote_id: 'q-1',
            quote_reference: 'VG-2026-0007',
            assignment_id: 'a-1',
            assignment_name: 'Opdracht Alfa',
            client_name: 'Voorbeeldministerie',
            requested_at: '2026-02-02T09:30:00Z',
            requested_by_name: 'Opdracht Manager',
            total_cents: 17280000,
            may_decide: true,
          },
        ],
      },
    });
    const { container } = renderApp(<ApprovalListPage />);
    await waitFor(() => expect(container.querySelector('nldd-link')).not.toBeNull());
    expect(container.querySelector('h1')?.textContent).toBe('Wacht op mijn goedkeuring');
    expect(container.querySelector('nldd-link')?.getAttribute('href')).toBe('/goedkeuren/q-1');
    expect(texts(container, 'nldd-table-row:not([slot]) nldd-text-cell')[0]).toBe('Opdracht Alfa');
  });

  it('is one calm state when nothing waits', async () => {
    mockApi({ '/api/quote-approvals/waiting': { items: [] } });
    const { container } = renderApp(<ApprovalListPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
        'Er wacht geen offerte op je goedkeuring',
      ),
    );
    expect(container.querySelector('nldd-table')).toBeNull();
  });
});

describe('QuoteSettingsPage', () => {
  const settings = (mode: string, threshold = 0, self = false) => ({
    items: [
      { key: 'quote_approval.mode', value: mode, default: 'never', label: '' },
      { key: 'quote_approval.threshold_cents', value: threshold, default: 0, label: '' },
      { key: 'quote_approval.allow_self_approval', value: self, default: false, label: '' },
    ],
  });

  it('says in words when approval is needed', async () => {
    mockApi({ '/api/instance-settings': settings('from_amount', 10000000) });
    const { container } = renderApp(<QuoteSettingsPage />);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    const cells = texts(container, 'nldd-list nldd-text-cell');
    expect(cells.some((text) => /^Vanaf €\s100\.000$/.test(text))).toBe(true);
    expect(cells).toContain('Mag niet: een ander keurt goed');
    expect(container.textContent).toContain('bij Team, onder Rechten in grip');
  });

  it('refuses "from an amount" without an amount, and saves the amount in cents', async () => {
    const { calls } = mockApi({
      '/api/instance-settings': settings('from_amount', 0),
      'PATCH /api/instance-settings': settings('from_amount', 5000000),
    });
    const { container } = renderApp(<QuoteSettingsPage />);
    await waitFor(() => expect(texts(container, 'nldd-button')).toContain('Wijzig'));
    clickButton(container, 'Wijzig');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text')).toContain(
        'Vul het bedrag in',
      ),
    );
    expect(calls.filter((call) => call.method === 'PATCH')).toEqual([]);
    sheet
      .querySelector('nldd-text-field')
      ?.dispatchEvent(new CustomEvent('input', { detail: { value: '50.000' } }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-text-field')?.getAttribute('value')).toBe('50.000'),
    );
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true));
    expect(calls.find((call) => call.method === 'PATCH')?.body).toEqual({
      values: {
        'quote_approval.mode': 'from_amount',
        'quote_approval.allow_self_approval': false,
        'quote_approval.threshold_cents': 5000000,
      },
    });
  });
});
