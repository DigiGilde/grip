import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { QuotePage } from './QuotePage';
import { mockApi, texts } from './testing';

const HASH = 'a'.repeat(64);

const LINE = {
  position: 1,
  description: 'Productmanager',
  kind: 'personnel',
  fte: '0.8',
  rate_category: 'D',
  scales: [14, 15],
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  monthly_rates: [{ year: 2026, monthly_rate_cents: 1800000 }],
  amount_cents: 17280000,
};

const CONTENT = {
  name: 'Opdracht Alfa',
  context_refs: [],
  lines: [LINE],
  subtotals_per_year: [{ year: 2026, amount_cents: 17280000 }],
  total_cents: 17280000,
};

const PREVIEW = {
  assignment_id: 'a-1',
  assignment_name: 'Opdracht Alfa',
  assignment_status: 'draft',
  can_issue: true,
  may_issue: true,
  problem: null,
  content: CONTENT,
  quoted_amount_cents: null,
  difference_cents: null,
  default_conditions: null,
};

const QUOTE = {
  id: 'q-1',
  uri: 'https://grip.example/id/offerte/q-1',
  reference: 'VG-2026-0007',
  assignment_id: 'a-1',
  status: 'issued',
  issued_at: '2026-02-01T09:00:00Z',
  issued_by_name: 'Opdracht Manager',
  total_cents: 17280000,
  snapshot_hash: HASH,
  valid_until: '2026-03-31',
  acceptance: null,
  rejection: null,
};

const CHANNELS = [
  { channel: 'client_instance', available: false, reason: 'De opdrachtgever gebruikt grip nog niet.' },
  { channel: 'signing_link', available: true },
  { channel: 'document', available: true, suggested: true },
];

const LINK_OFFER = {
  id: 'o-1',
  channel: 'signing_link',
  recipient: 'tekenaar@opdrachtgever.example',
  offered_at: '2026-02-02T10:00:00Z',
  offered_by_name: 'Opdracht Manager',
  invitation: {
    id: 'i-1',
    signing_path: '/tekenen/q-1',
    expires_at: '2026-03-04T10:00:00Z',
    opened_at: null,
    used_at: null,
    withdrawn_at: null,
    state: 'invited',
  },
};

afterEach(() => vi.unstubAllGlobals());

interface Setup {
  preview?: object;
  quotes?: object[];
  mayManage?: boolean;
  offers?: object[];
}

async function renderTab({ preview = PREVIEW, quotes = [], mayManage = true, offers = [] }: Setup) {
  mockApi({
    '/api/assignments/a-1/quote-preview': preview,
    '/api/assignments/a-1/quotes': { may_manage: mayManage, quotes },
    '/api/quotes/q-1': { ...(quotes[0] ?? QUOTE), content: CONTENT, offers, channels: CHANNELS },
  });
  const view = renderApp(
    <Routes>
      <Route path="/opdrachten/:assignmentId/offerte" element={<QuotePage />} />
    </Routes>,
    { path: '/opdrachten/a-1/offerte' },
  );
  const loading = () => view.container.querySelector('nldd-inline-dialog[variant="loading"]');
  await waitFor(() => expect(view.container.querySelector('h1, nldd-title, nldd-banner')).not.toBeNull());
  await waitFor(() => expect(loading()).toBeNull());
  if (quotes.length > 0) {
    await waitFor(() => expect(view.container.querySelector('nldd-card')).not.toBeNull());
    // The card is complete once the quote's offers and channels are in.
    await waitFor(() =>
      expect(view.container.querySelector('nldd-card nldd-step-bar')?.getAttribute('data-ready')).toBe(
        'true',
      ),
    );
  }
  return view.container;
}

/** The primary buttons on the page itself; sheets live outside the container. */
function primaries(container: HTMLElement): string[] {
  return texts(container, 'nldd-button[appearance="primary"]');
}

describe('QuotePage', () => {
  it('offers to make a quote from the budget when there is none', async () => {
    const container = await renderTab({});
    expect(primaries(container)).toEqual(['Maak offerte']);
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('Productmanager');
    // Scales first, as on the rate leaflet a client knows.
    expect(cells).toContain('14 en 15 (categorie D)');
    // What "maak" does not say by itself.
    expect(container.textContent).toContain('Daarna wijzigt de offerte niet meer');
    expect(container.querySelector('nldd-card')).toBeNull();
  });

  it('explains a part month where the amount is not rate times months', async () => {
    const container = await renderTab({
      preview: {
        ...PREVIEW,
        content: {
          ...CONTENT,
          lines: [{ ...LINE, start_date: '2026-10-01', end_date: '2026-10-29' }],
        },
      },
    });
    expect(container.textContent).toContain('oktober 2026 telt voor 29 van de 31 dagen');
  });

  it('says why a quote cannot be made', async () => {
    const container = await renderTab({
      preview: {
        ...PREVIEW,
        can_issue: false,
        content: undefined,
        problem: 'Een offerte heeft minstens een begrotingsregel nodig.',
      },
    });
    expect(
      container.querySelector('nldd-banner[variant="warning"]')?.getAttribute('supporting-text'),
    ).toContain('begrotingsregel');
    expect(primaries(container)).toEqual([]);
  });

  it('shows one quote as one card with the amount, the status and one action', async () => {
    const container = await renderTab({ quotes: [QUOTE] });
    const title = container.querySelector('nldd-card nldd-title');
    expect(title?.getAttribute('text')).toMatch(/^€\s172\.800$/);
    expect(title?.getAttribute('overline')).toBe('Offerte VG-2026-0007');
    expect(texts(container, 'nldd-card nldd-badge')).toEqual(['Offerte gemaakt']);
    expect(texts(container, 'nldd-step-bar-item')).toEqual([
      'Gemaakt',
      'Aangeboden',
      'Getekend of afgewezen',
    ]);
    expect(container.textContent).toContain('Geldig t/m 31 mrt 2026');
    expect(container.textContent).toContain('Gemaakt op 1 feb 2026 door Opdracht Manager');
    // The one thing to do after making a quote.
    expect(primaries(container)).toEqual(['Bied aan']);
    // The quote to wait for is the subject; no second quote is proposed.
    expect(texts(container, 'nldd-button')).not.toContain('Maak offerte');
    expect(container.querySelector('nldd-table')).toBeNull();
    // The fingerprint is behind a control, not in the reading line.
    expect(container.querySelector('nldd-card nldd-text-cell')?.textContent ?? '').not.toContain(
      HASH,
    );
    expect(container.querySelector('nldd-popover [data-fingerprint]')?.textContent).toBe(HASH);
  });

  it('keeps the signing link in reach after inviting someone', async () => {
    const container = await renderTab({ quotes: [QUOTE], offers: [LINK_OFFER] });
    await waitFor(() => expect(container.querySelector('nldd-list-item')).not.toBeNull());
    const row = container.querySelector('nldd-card nldd-list-item nldd-text-cell');
    expect(row?.getAttribute('text')).toBe('Met een tekenlink aan tekenaar@opdrachtgever.example');
    expect(row?.getAttribute('supporting-text')).toMatch(/^Uitgenodigd, nog niet geopend · aangeboden op/);
    expect(texts(container, 'nldd-card nldd-list-item nldd-button')).toEqual([
      'Kopieer tekenlink',
      'Kopieer bericht',
    ]);
    expect(container.textContent).toContain('/tekenen/q-1');
    expect(container.textContent).toContain('geldig t/m 4 mrt 2026');
    expect(texts(container, 'nldd-card nldd-badge')).toEqual(['Aangeboden']);
    // Waiting for the client: nothing primary, and the invitation is shown once.
    expect(primaries(container)).toEqual([]);
    expect(container.querySelectorAll('nldd-card nldd-list-item')).toHaveLength(1);
    expect(container.querySelector('nldd-table')).toBeNull();
    // Withdrawing and renewing sit in the row's menu.
    expect(texts(container, 'nldd-list-item nldd-menu-item')).toEqual([
      'Verleng met 30 dagen',
      'Trek de tekenlink in',
    ]);
  });

  it('makes recording the signed copy the step when the quote went out as a document', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      offers: [{ id: 'o-2', channel: 'document', offered_at: '2026-02-03T10:00:00Z' }],
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Leg getekende pdf vast']));
    expect(
      container.querySelector('nldd-card nldd-list-item nldd-text-cell')?.getAttribute('supporting-text'),
    ).toMatch(/^Meegegeven, wacht op het getekende exemplaar/);
  });

  it('lists a channel that is not possible with its reason, in the sheet', async () => {
    await renderTab({ quotes: [QUOTE] });
    const sheet = [...document.body.querySelectorAll('nldd-sheet')].find(
      (el) => el.querySelector('nldd-title')?.getAttribute('text') === 'Offerte aanbieden',
    );
    await waitFor(() => expect(sheet?.querySelectorAll('nldd-list-item')).toHaveLength(3));
    const rows = [...(sheet as Element).querySelectorAll('nldd-list-item')];
    const federated = rows.find((row) =>
      row.querySelector('nldd-text-cell')?.getAttribute('text')?.includes('grip van de opdrachtgever'),
    );
    expect(federated?.hasAttribute('disabled')).toBe(true);
    expect(federated?.querySelector('nldd-text-cell')?.getAttribute('supporting-text')).toBe(
      'De opdrachtgever gebruikt grip nog niet.',
    );
    expect(document.body.textContent).not.toContain('instantie');
  });

  it('gives a reader the card without actions', async () => {
    const container = await renderTab({
      preview: { ...PREVIEW, may_issue: false },
      quotes: [QUOTE],
      mayManage: false,
      offers: [{ id: 'o-1', channel: 'signing_link', offered_at: '2026-02-02T10:00:00Z' }],
    });
    await waitFor(() => expect(container.querySelector('nldd-list-item')).not.toBeNull());
    expect(
      texts(container, 'nldd-button').filter((text) => !text.toLowerCase().includes('vingerafdruk')),
    ).toEqual([]);
    expect(container.querySelector('nldd-icon-button')).toBeNull();
    expect(texts(container, 'nldd-link')).toEqual(['Bekijk', 'Download pdf']);
    expect(container.textContent).not.toContain('/tekenen/');
  });

  it('shows who signed once the client accepted', async () => {
    const container = await renderTab({
      preview: { ...PREVIEW, assignment_status: 'accepted', can_issue: false },
      quotes: [
        {
          ...QUOTE,
          status: 'accepted',
          acceptance: {
            form: 'signing_link',
            signed_at: '2026-02-10T12:00:00Z',
            signer_name: 'Tekenaar Voorbeeld',
            signer_function: 'Directeur',
            organisation_name: 'Voorbeeldministerie',
            has_document: false,
          },
        },
      ],
    });
    expect(container.textContent).toContain(
      'door Tekenaar Voorbeeld (Directeur) namens Voorbeeldministerie',
    );
    expect(texts(container, 'nldd-step-bar-item')).toEqual(['Gemaakt', 'Aangeboden', 'Getekend']);
    expect(primaries(container)).toEqual([]);
    expect(container.querySelector('nldd-card nldd-icon-button')).toBeNull();
  });

  it('collapses earlier quotes to one line each', async () => {
    const container = await renderTab({
      quotes: [
        QUOTE,
        { ...QUOTE, id: 'q-0', reference: 'VG-2026-0003', status: 'superseded', total_cents: 16000000 },
      ],
    });
    const earlier = container.querySelector('nldd-list[accessible-label="Eerdere offertes"]');
    expect(earlier?.querySelectorAll('nldd-list-item')).toHaveLength(1);
    expect(earlier?.querySelector('nldd-text-cell')?.getAttribute('text')).toBe(
      'VG-2026-0003 · 1 feb 2026',
    );
    expect(container.querySelectorAll('nldd-card')).toHaveLength(1);
  });

  it('proposes a new quote only when the budget moved since', async () => {
    const container = await renderTab({
      preview: { ...PREVIEW, assignment_status: 'quoted', content: { ...CONTENT, total_cents: 18000000 } },
      quotes: [QUOTE],
    });
    expect(texts(container, 'nldd-button')).toContain('Maak nieuwe offerte');
    expect(container.textContent).toMatch(/De begroting staat nu op €\s180\.000/);
    expect(primaries(container)).toEqual(['Bied aan']);
  });
});
