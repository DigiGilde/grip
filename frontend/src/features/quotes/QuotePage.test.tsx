import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { QuotePage } from './QuotePage';
import { clickButton, mockApi, texts } from './testing';

const HASH = 'a'.repeat(64);

const CONTENT = {
  name: 'Opdracht Alfa',
  context_refs: [],
  lines: [
    {
      position: 1,
      description: 'Productmanager',
      kind: 'personnel',
      fte: '0.8',
      rate_category: 'D',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      monthly_rates: [{ year: 2026, monthly_rate_cents: 1800000 }],
      amount_cents: 17280000,
    },
  ],
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
  quoted_amount_cents: 17000000,
  difference_cents: -280000,
};

const ISSUED = {
  id: 'q-1',
  uri: 'https://grip.example/id/offerte/q-1',
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

let lastCalls: { url: string; method: string; body: unknown }[] = [];

afterEach(() => vi.unstubAllGlobals());

const CHANNELS = [
  { channel: 'client_instance', available: true, reason: null, suggested: false },
  { channel: 'signing_link', available: true, reason: null, suggested: false },
  { channel: 'document', available: true, reason: null, suggested: true },
];

async function renderQuotes(
  preview: object,
  list: object,
  invitations: object[] = [],
  detail: object = { ...ISSUED, offers: [], channels: CHANNELS },
) {
  const api = mockApi({
    '/api/assignments/a-1/quote-preview': preview,
    '/api/assignments/a-1/quotes': list,
    '/api/quotes/q-1/invitations': { invitations },
    '/api/quotes/q-1': detail,
    'POST /api/quotes/q-1/offers': detail,
  });
  lastCalls = api.calls;
  const view = renderApp(
    <Routes>
      <Route path="/opdrachten/:assignmentId/offerte" element={<QuotePage />} />
    </Routes>,
    { path: '/opdrachten/a-1/offerte' },
  );
  await waitFor(() => expect(view.container.querySelector('h1')?.textContent).toContain('Alfa'));
  await waitFor(() => expect(view.container.textContent).not.toContain('Bezig met laden'));
  return view.container;
}

describe('QuotePage', () => {
  it('shows the lines, the total and the difference to the agreed amount', async () => {
    const container = await renderQuotes(PREVIEW, { may_manage: true, quotes: [] });
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('Productmanager');
    expect(cells).toContain('D');
    expect(cells.filter((text) => text.includes('172.800'))).toHaveLength(2);
    expect(container.textContent).toContain('lager dan de begroting');
    expect(texts(container, 'nldd-button')).toContain('Geef offerte uit');
    // Nothing issued yet: say so instead of an empty list.
    expect(
      [...container.querySelectorAll('nldd-inline-dialog')].map((el) => el.getAttribute('text')),
    ).toContain('Er is nog geen offerte uitgegeven');
  });

  it('offers no actions to someone who may only read', async () => {
    const container = await renderQuotes(
      { ...PREVIEW, may_issue: false },
      { may_manage: false, quotes: [ISSUED] },
    );
    expect(texts(container, 'nldd-button')).toEqual([]);
    // The document is still within reach.
    const links = texts(container, 'nldd-link');
    expect(links).toContain('Bekijk de offerte');
  });

  it('says why a quote cannot be made', async () => {
    const container = await renderQuotes(
      {
        ...PREVIEW,
        can_issue: false,
        content: undefined,
        problem: 'Een offerte heeft minstens een begrotingsregel nodig.',
        quoted_amount_cents: null,
        difference_cents: null,
      },
      { may_manage: true, quotes: [] },
    );
    const banner = container.querySelector('nldd-banner[variant="warning"]');
    expect(banner?.getAttribute('supporting-text')).toContain('begrotingsregel');
    expect(texts(container, 'nldd-button')).not.toContain('Geef offerte uit');
  });

  it('leaves out the amounts for someone who may not see them', async () => {
    const container = await renderQuotes(
      {
        assignment_id: 'a-1',
        assignment_name: 'Opdracht Alfa',
        assignment_status: 'quoted',
        can_issue: true,
        may_issue: false,
        problem: null,
      },
      {
        may_manage: false,
        quotes: [
          {
            id: 'q-1',
            uri: ISSUED.uri,
            assignment_id: 'a-1',
            status: 'issued',
            issued_at: ISSUED.issued_at,
            issued_by_name: null,
          },
        ],
      },
    );
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(container.textContent).not.toContain('€');
    // Without the content there is no document to open either.
    expect(texts(container, 'nldd-link')).toEqual(['Terug naar de opdracht']);
  });

  it('offers an issued quote through one of three channels, chosen then', async () => {
    const container = await renderQuotes(
      { ...PREVIEW, assignment_status: 'quoted' },
      { may_manage: true, quotes: [ISSUED] },
    );
    await waitFor(() =>
      expect(texts(container, 'nldd-button')).toContain('Via de grip van de opdrachtgever'),
    );
    const buttons = texts(container, 'nldd-button');
    expect(buttons).toContain('Met een tekenlink in deze grip');
    expect(buttons).toContain('Als document');
    expect(container.textContent ?? '').not.toContain('kan nu niet');
    expect(texts(container, 'nldd-title')).toContain('Aanbieden');

    clickButton(container, 'Via de grip van de opdrachtgever');
    await waitFor(() =>
      expect(lastCalls.some((call) => call.method === 'POST')).toBe(true),
    );
    const sent = lastCalls.find((call) => call.method === 'POST');
    expect(sent?.url).toBe('/api/quotes/q-1/offers');
    expect(sent?.body).toEqual({ channel: 'client_instance' });
  });

  it('says why the grip of the client is not possible, and shows earlier offers', async () => {
    const container = await renderQuotes(
      { ...PREVIEW, assignment_status: 'quoted' },
      { may_manage: true, quotes: [ISSUED] },
      [],
      {
        ...ISSUED,
        channels: [
          {
            channel: 'client_instance',
            available: false,
            reason: 'De opdrachtgever is niet gekoppeld.',
            suggested: false,
          },
          ...CHANNELS.slice(1),
        ],
        offers: [
          {
            id: 'o-1',
            channel: 'client_instance',
            recipient: 'https://grip.opdrachtgever.example',
            offered_at: '2026-02-02T10:00:00Z',
            offered_by_name: 'Opdracht Manager',
            delivery: 'refused',
          },
          {
            id: 'o-2',
            channel: 'document',
            recipient: null,
            offered_at: '2026-02-03T10:00:00Z',
            offered_by_name: 'Opdracht Manager',
            delivery: null,
          },
        ],
      },
    );
    await waitFor(() =>
      expect(container.textContent ?? '').toContain('De opdrachtgever is niet gekoppeld.'),
    );
    const federated = [...container.querySelectorAll('nldd-button')].find(
      (el) => el.getAttribute('text') === 'Via de grip van de opdrachtgever',
    );
    expect(federated?.hasAttribute('disabled')).toBe(true);
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('https://grip.opdrachtgever.example');
    expect(cells).toContain('Niet afgeleverd');
    expect(cells).toContain('Document meegegeven');
  });

  it('gives the manager the ways to record a decision on an open quote', async () => {
    const container = await renderQuotes(
      { ...PREVIEW, assignment_status: 'quoted' },
      { may_manage: true, quotes: [ISSUED] },
      [
        {
          id: 'i-1',
          email: 'tekenaar@opdrachtgever.example',
          created_at: '2026-02-02T10:00:00Z',
          expires_at: null,
          used_at: null,
        },
      ],
    );
    const buttons = texts(container, 'nldd-button');
    expect(buttons).toContain('Leg getekende pdf vast');
    expect(buttons).toContain('Leg afwijzing vast');
    await waitFor(() =>
      expect(texts(container, 'nldd-table nldd-text-cell')).toContain(
        'tekenaar@opdrachtgever.example',
      ),
    );
  });

  it('shows who accepted and offers the signed document', async () => {
    const container = await renderQuotes(
      { ...PREVIEW, assignment_status: 'accepted', can_issue: false },
      {
        may_manage: true,
        quotes: [
          {
            ...ISSUED,
            status: 'accepted',
            acceptance: {
              form: 'uploaded_pdf',
              signed_at: '2026-02-10T12:00:00Z',
              signer_name: 'Directeur Voorbeeld',
              signer_function: 'Directeur',
              organisation_name: 'Voorbeeldministerie',
              has_document: true,
            },
          },
        ],
      },
    );
    expect(container.textContent).toContain('door Directeur Voorbeeld (Directeur)');
    expect(container.textContent).toContain('namens Voorbeeldministerie');
    expect(texts(container, 'nldd-link')).toContain('Download het getekende exemplaar');
    // A decided quote takes no further decision.
    expect(texts(container, 'nldd-button')).not.toContain('Leg afwijzing vast');
  });
});
