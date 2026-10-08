import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { ApprovalListPage } from './ApprovalListPage';
import { ApprovalPage } from './ApprovalPage';
import { QuoteSettingsPage } from './QuoteSettingsPage';
import { VerifyProofPage } from './VerifyProofPage';
import { navigation } from './proof';
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
    const { container } = renderPage({
      '/api/quote-approvals/quotes/q-1': APPROVER_QUOTE,
    });
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

  it('leaves for the login to approve the version that was shown', async () => {
    const go = vi.spyOn(navigation, 'go').mockImplementation(() => {});
    const { container, calls } = renderPage({
      '/api/quote-approvals/quotes/q-1': APPROVER_QUOTE,
      'POST /api/proof/intents': {
        id: 'in-1',
        authorize_url: '/api/proof/intents/in-1/authorize',
        expires_at: '2026-02-03T10:05:00Z',
        reauthentication: true,
      },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    clickButton(container, 'Keur goed');
    await waitFor(() => expect(openSheet()).toBeDefined());
    expect(openSheet()?.textContent).toContain('Daarna is je goedkeuring vastgelegd.');
    openSheet()
      ?.querySelector('nldd-form')
      ?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(go).toHaveBeenCalledWith('/api/proof/intents/in-1/authorize'));
    const posts = calls.filter((call) => call.method === 'POST');
    expect(posts.map((call) => call.url)).toEqual(['/api/proof/intents']);
    expect(posts[0]?.body).toEqual({
      kind: 'approve',
      quote_id: 'q-1',
      quote_hash: HASH,
      note: null,
      return_path: '/goedkeuren/q-1',
    });
    go.mockRestore();
  });

  it('shows the receipt of an approval on return', async () => {
    mockApi({
      '/api/quote-approvals/quotes/q-1': {
        ...APPROVER_QUOTE,
        approval: { ...APPROVER_QUOTE.approval, status: 'approved', may_decide_approval: false },
      },
      '/api/proof/evidence/ev-2': {
        id: 'ev-2',
        decision: 'approve',
        channel: 'internal',
        quote_id: 'q-1',
        sound: true,
        proven: [],
        not_proven: [],
        wrong: [],
        has_identity_statement: true,
        has_timestamp: false,
        statement: {
          besluit: 'goedkeuring',
          offerte: { kenmerk: 'VG-2026-0007', totaal_centen: 17280000 },
          wie: { naam: 'Collega Goedkeurder' },
          wanneer: { ontvangen_op: '2026-02-03T11:00:00Z' },
        },
      },
    });
    const { container } = renderApp(
      <Routes>
        <Route path="/goedkeuren/:quoteId" element={<ApprovalPage />} />
      </Routes>,
      { path: '/goedkeuren/q-1?bewijs=ev-2' },
    );
    await waitFor(() => expect(container.querySelector('[data-receipt]')).not.toBeNull());
    expect(container.querySelector('[data-receipt]')?.getAttribute('text')).toBe(
      'Je goedkeuring is vastgelegd',
    );
    // One confirmation, not two banners saying the same.
    expect(container.querySelectorAll('nldd-banner')).toHaveLength(1);
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual(['Download bewijs']);
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
      {
        key: 'quote_approval.threshold_cents',
        value: threshold,
        default: 0,
        label: '',
      },
      {
        key: 'quote_approval.allow_self_approval',
        value: self,
        default: false,
        label: '',
      },
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
      expect(
        sheet.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text'),
      ).toContain('Vul het bedrag in'),
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

describe('VerifyProofPage', () => {
  const STATEMENT = {
    besluit: 'akkoord',
    offerte: { kenmerk: 'VG-2026-0007', totaal_centen: 17280000 },
    wie: { naam: 'Tekenaar Voorbeeld' },
    wanneer: { aangemeld_op: '2026-02-03T09:58:00Z', ontvangen_op: '2026-02-03T10:00:00Z' },
  };
  const pick = (container: HTMLElement, content: string) => {
    const file = new File([content], 'bewijs-abc.json', { type: 'application/json' });
    container
      .querySelector('nldd-file-field')
      ?.dispatchEvent(new CustomEvent('change', { detail: { files: [file] } }));
  };

  it("says what a bundle shows and what it leaves open, in the server's words", async () => {
    const { calls } = mockApi({
      'POST /api/signing/verify': {
        sound: true,
        proven: ['De inhoud van de offerte past bij de vingerafdruk.'],
        not_proven: ['Het mandaat ligt buiten grip vast.'],
        wrong: [],
        statement: STATEMENT,
      },
    });
    const { container } = renderApp(<VerifyProofPage />);
    expect(container.querySelector('h1')?.textContent).toBe('Controleer een bewijs');
    pick(container, JSON.stringify({ verklaring: {} }));
    await waitFor(() => expect(container.querySelector('[data-verify-result]')).not.toBeNull());
    expect(
      container.querySelector('[data-verify-result]')?.getAttribute('data-verify-result'),
    ).toBe('sound');
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      bundle: { verklaring: {} },
    });
    const cells = texts(container, 'nldd-list nldd-text-cell');
    expect(cells).toContain('De inhoud van de offerte past bij de vingerafdruk.');
    expect(cells).toContain('Het mandaat ligt buiten grip vast.');
    // The two moments as facts, without a judgement on the time between them.
    expect(container.textContent).toMatch(
      /Ingelogd op 3 feb 2026, \d\d:58\. Akkoord gegeven op 3 feb 2026, \d\d:00\./,
    );
    expect(container.textContent).not.toMatch(/zwakker|minder sterk/i);
    expect(container.querySelector('nldd-banner[variant="warning"]')).toBeNull();
  });

  it('says plainly that a changed bundle does not hold', async () => {
    mockApi({
      'POST /api/signing/verify': {
        sound: false,
        proven: [],
        not_proven: [],
        wrong: ['De handtekening onder de verklaring klopt niet.'],
        statement: null,
      },
    });
    const { container } = renderApp(<VerifyProofPage />);
    pick(container, '{}');
    await waitFor(() => expect(container.querySelector('[data-verify-result]')).not.toBeNull());
    expect(container.querySelector('nldd-banner')?.getAttribute('variant')).toBe('critical');
    expect(texts(container, 'nldd-title')).toContain('Wat niet klopt');
  });

  it('does not send a file that is no bundle', async () => {
    const { calls } = mockApi({});
    const { container } = renderApp(<VerifyProofPage />);
    pick(container, 'dit is geen json');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-banner[variant="critical"], nldd-inline-dialog'),
      ).not.toBeNull(),
    );
    expect(calls).toEqual([]);
  });

  it('shows a refusal of the server plainly', async () => {
    mockApi({
      'POST /api/signing/verify': {
        status: 413,
        body: { title: 'Te groot', detail: 'De bundel is te groot.' },
      },
    });
    const { container } = renderApp(<VerifyProofPage />);
    pick(container, '{}');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-banner[variant="critical"], nldd-inline-dialog'),
      ).not.toBeNull(),
    );
    expect(container.innerHTML).toContain('De bundel is te groot.');
  });
});

describe('the switch for mailing the signing link', () => {
  const settings = (value: boolean) => ({
    items: [
      { key: 'quote_approval.mode', value: 'never', default: 'never', label: '' },
      { key: 'mail.signing_link', value, default: true, label: '' },
    ],
  });

  it('saves the switch, and is absent where the server does not offer the setting', async () => {
    const { calls } = mockApi({
      '/api/instance-settings': settings(true),
      'PATCH /api/instance-settings': settings(false),
    });
    const { container } = renderApp(<QuoteSettingsPage />);
    await waitFor(() => expect(container.querySelector('nldd-checkbox-field')).not.toBeNull());
    const box = container.querySelector('nldd-checkbox-field') as Element;
    expect(box.hasAttribute('checked')).toBe(true);
    box.dispatchEvent(new CustomEvent('change', { detail: { checked: false } }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true));
    expect(calls.find((call) => call.method === 'PATCH')?.body).toEqual({
      values: { 'mail.signing_link': false },
    });

    mockApi({ '/api/instance-settings': { items: settings(true).items.slice(0, 1) } });
    const other = renderApp(<QuoteSettingsPage />);
    await waitFor(() => expect(other.container.querySelector('nldd-list')).not.toBeNull());
    expect(other.container.querySelector('nldd-checkbox-field')).toBeNull();
    expect(other.container.textContent).not.toMatch(/mail/i);
  });
});
