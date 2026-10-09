import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { QuotePage } from './QuotePage';
import { clickButton, mockApi, texts } from './testing';

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
  {
    channel: 'client_instance',
    available: false,
    reason: 'De opdrachtgever gebruikt grip nog niet.',
  },
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

let lastCalls: { url: string; method: string; body: unknown }[] = [];

const APPROVAL = {
  quote_id: 'q-1',
  approval_required: true,
  approval_reason: 'vanaf € 100.000',
  status: 'none',
  may_offer: false,
  blocked_message: 'Deze offerte kan pas worden aangeboden na interne goedkeuring.',
  approver_available: true,
  may_request_approval: true,
  may_decide_approval: false,
  may_withdraw: false,
  current: null,
  history: [],
};

interface Setup {
  detail?: object;
  evidence?: object[];
  budgetMoved?: boolean;
  approval?: object;
  preview?: object;
  quotes?: object[];
  mayManage?: boolean;
  offers?: object[];
}

async function renderTab({
  preview = PREVIEW,
  quotes = [],
  mayManage = true,
  offers = [],
  approval,
  budgetMoved,
  evidence,
  detail = {},
}: Setup) {
  const { calls } = mockApi({
    ...(evidence ? { '/api/proof/quotes/q-1/evidence': { items: evidence } } : {}),
    ...(approval ? { '/api/assignments/a-1/quote-approvals': { items: [approval] } } : {}),
    'POST /api/quotes/q-1/approval/request': {
      ...APPROVAL,
      status: 'requested',
    },
    '/api/assignments/a-1/quote-preview': preview,
    '/api/assignments/a-1/quotes': {
      may_manage: mayManage,
      quotes,
      ...(budgetMoved === undefined
        ? {}
        : { budget_moved: budgetMoved, budget_compared_quote_id: 'q-1' }),
    },
    '/api/quotes/q-1': {
      ...(quotes[0] ?? QUOTE),
      content: CONTENT,
      offers,
      channels: CHANNELS,
      ...detail,
    },
  });
  const view = renderApp(
    <Routes>
      <Route path="/opdrachten/:assignmentId/offerte" element={<QuotePage />} />
    </Routes>,
    { path: '/opdrachten/a-1/offerte' },
  );
  const loading = () => view.container.querySelector('nldd-inline-dialog[variant="loading"]');
  await waitFor(() =>
    expect(view.container.querySelector('h1, nldd-title, nldd-banner')).not.toBeNull(),
  );
  await waitFor(() => expect(loading()).toBeNull());
  if (quotes.length > 0) {
    await waitFor(() => expect(view.container.querySelector('nldd-card')).not.toBeNull());
    // The card is complete once the quote's offers and channels are in.
    await waitFor(() =>
      expect(
        view.container.querySelector('nldd-card[data-ready]')?.getAttribute('data-ready'),
      ).toBe('true'),
    );
  }
  lastCalls = calls;
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

  it('shows every rate when a rate card changes inside the line', async () => {
    const container = await renderTab({
      preview: {
        ...PREVIEW,
        content: {
          ...CONTENT,
          lines: [
            {
              ...LINE,
              monthly_rates: [],
              rate_periods: [
                {
                  start_date: '2026-01-01',
                  end_date: '2026-06-30',
                  monthly_rate_cents: 1800000,
                },
                {
                  start_date: '2026-07-01',
                  end_date: '2026-12-31',
                  monthly_rate_cents: 1900000,
                },
              ],
            },
          ],
        },
      },
    });
    const later = [...container.querySelectorAll('nldd-table nldd-text-cell')]
      .map((el) => el.getAttribute('supporting-text'))
      .filter(Boolean);
    expect(later.some((text) => /^vanaf 1 jul 2026: €\s19\.000$/.test(text ?? ''))).toBe(true);
    expect(container.textContent).toContain('Het tarief wijzigt per 1 jul 2026.');
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
    // The steps are the assignment's, in its head: the card draws none.
    expect(container.querySelector('nldd-step-bar')).toBeNull();
    expect(container.textContent).toContain('Geldig t/m 31 mrt 2026');
    expect(container.textContent).toContain('Gemaakt op 1 feb 2026 door Opdracht Manager');
    // The one thing to do after making a quote.
    expect(primaries(container)).toEqual(['Bied aan']);
    // The quote to wait for is the subject; no second quote is proposed.
    expect(texts(container, 'nldd-button')).not.toContain('Maak offerte');
    expect(container.querySelector('nldd-table')).toBeNull();
    // The echtheidskenmerk is behind "Details", in a sheet, never in the reading line.
    expect(container.textContent).not.toContain(HASH);
    expect(texts(container, 'nldd-card nldd-button')).toContain('Details');
    const sheet = [...document.body.querySelectorAll('nldd-sheet')].find(
      (el) => el.querySelector('nldd-title')?.getAttribute('text') === 'Details van de offerte',
    );
    const lines = [...(sheet as Element).querySelectorAll('[data-code-line]')].map(
      (el) => el.textContent,
    );
    // Blocks of eight, four to a line: it cannot run out of its box.
    expect(lines).toEqual([
      'aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa',
      'aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa',
    ]);
    expect(texts(sheet as Element, 'nldd-button')).toContain('Kopieer echtheidskenmerk');
    expect(sheet?.textContent).toContain('Verandert er ook maar één teken');
    expect(sheet?.textContent?.replace(/Technisch:.*/, '')).not.toMatch(/hash|SHA/i);
  });

  it('keeps the signing link in reach after inviting someone', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      offers: [LINK_OFFER],
    });
    await waitFor(() => expect(container.querySelector('[data-offer]')).not.toBeNull());
    const row = container.querySelector('nldd-card [data-offer]') as Element;
    const lines = [...row.querySelectorAll('nldd-text')].map((el) => el.textContent);
    expect(lines[0]).toBe('Met een tekenlink aan tekenaar@opdrachtgever.example');
    expect(lines[1]).toMatch(
      /^Uitgenodigd, nog niet geopend · aangeboden op .* · link geldig t\/m 4 mrt 2026$/,
    );
    // The link itself is on screen, on a line of its own, with its buttons under it.
    expect(row.querySelector('[data-signing-link]')?.textContent).toMatch(/\/tekenen\/q-1$/);
    expect(texts(row, 'nldd-button')).toEqual(['Kopieer tekenlink', 'Kopieer bericht']);
    expect(texts(container, 'nldd-card nldd-badge')).toEqual(['Aangeboden']);
    // Waiting for the client: nothing primary, and the invitation is shown once.
    expect(primaries(container)).toEqual([]);
    expect(container.querySelectorAll('nldd-card [data-offer]')).toHaveLength(1);
    expect(container.querySelector('nldd-table')).toBeNull();
    // Withdrawing and renewing sit in the row's menu.
    expect(texts(row, 'nldd-menu-item')).toEqual(['Verleng met 30 dagen', 'Trek de tekenlink in']);
    // The tag says where the quote is.
    expect(texts(container, 'nldd-card nldd-badge')).toEqual(['Aangeboden']);
  });

  it('makes recording the signed copy the step when the quote went out as a document', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      offers: [{ id: 'o-2', channel: 'document', offered_at: '2026-02-03T10:00:00Z' }],
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Leg getekende pdf vast']));
    expect(container.querySelector('nldd-card [data-offer]')?.textContent).toContain(
      'Als document verstuurd, wacht op het getekende exemplaar',
    );
  });

  it('lists a channel that is not possible with its reason, in the sheet', async () => {
    await renderTab({ quotes: [QUOTE] });
    const sheet = [...document.body.querySelectorAll('nldd-sheet')].find(
      (el) => el.querySelector('nldd-title')?.getAttribute('text') === 'Offerte aanbieden',
    );
    await waitFor(() => expect(sheet?.querySelectorAll('nldd-list-item')).toHaveLength(3));
    const rows = [...(sheet as Element).querySelectorAll('nldd-list-item')];
    const federated = rows.find((row) =>
      row
        .querySelector('nldd-text-cell')
        ?.getAttribute('text')
        ?.includes('grip van de opdrachtgever'),
    );
    expect(federated?.hasAttribute('disabled')).toBe(true);
    expect(federated?.querySelector('nldd-text-cell')?.getAttribute('supporting-text')).toBe(
      'De opdrachtgever gebruikt grip nog niet.',
    );
    expect(document.body.textContent).not.toContain('instantie');
  });

  it('chooses no channel for the person and shows the choice', async () => {
    await renderTab({ quotes: [QUOTE] });
    const sheet = [...document.body.querySelectorAll('nldd-sheet')].find(
      (el) => el.querySelector('nldd-title')?.getAttribute('text') === 'Offerte aanbieden',
    ) as Element;
    await waitFor(() => expect(sheet.querySelectorAll('nldd-list-item')).toHaveLength(3));
    const rows = [...sheet.querySelectorAll('nldd-list-item')];
    // Every row draws a radio, and none is chosen yet.
    expect(rows.every((row) => row.querySelector('nldd-radio-button[decorative]'))).toBe(true);
    expect(rows.some((row) => row.hasAttribute('checked'))).toBe(false);
    const submit = sheet.querySelector('nldd-button[type="submit"]');
    expect(submit?.hasAttribute('disabled')).toBe(true);
    expect(sheet.textContent).toContain('Kies eerst hoe de opdrachtgever de offerte krijgt.');
    // Choosing one marks it and frees the button.
    const document_ = rows.find(
      (row) => row.querySelector('nldd-text-cell')?.getAttribute('text') === 'Als document',
    ) as Element;
    document_.dispatchEvent(new CustomEvent('change', { detail: { checked: true } }));
    await waitFor(() => expect(document_.hasAttribute('checked')).toBe(true));
    expect(document_.querySelector('nldd-radio-button')?.hasAttribute('checked')).toBe(true);
    expect(sheet.querySelector('nldd-button[type="submit"]')?.hasAttribute('disabled')).toBe(false);
  });

  it('gives a reader the card without actions', async () => {
    const container = await renderTab({
      preview: { ...PREVIEW, may_issue: false },
      quotes: [QUOTE],
      mayManage: false,
      offers: [
        {
          id: 'o-1',
          channel: 'signing_link',
          offered_at: '2026-02-02T10:00:00Z',
        },
      ],
    });
    await waitFor(() => expect(container.querySelector('[data-offer]')).not.toBeNull());
    expect(texts(container, 'nldd-button').filter((text) => text !== 'Details')).toEqual([]);
    expect(container.querySelector('nldd-icon-button')).toBeNull();
    expect(texts(container, 'nldd-link')).toEqual(['Bekijk pdf']);
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
    expect(primaries(container)).toEqual([]);
    expect(container.querySelector('nldd-card nldd-icon-button')).toBeNull();
  });

  it('collapses earlier quotes to one line each', async () => {
    const container = await renderTab({
      quotes: [
        QUOTE,
        {
          ...QUOTE,
          id: 'q-0',
          reference: 'VG-2026-0003',
          status: 'superseded',
          total_cents: 16000000,
        },
      ],
    });
    const earlier = container.querySelector('nldd-list[accessible-label="Eerdere offertes"]');
    expect(earlier?.querySelectorAll('nldd-list-item')).toHaveLength(1);
    expect(earlier?.querySelector('nldd-text-cell')?.getAttribute('text')).toBe(
      'VG-2026-0003 · 1 feb 2026',
    );
    expect(container.querySelectorAll('nldd-card')).toHaveLength(1);
  });

  it('proposes a new quote when the server says the budget moved, also at the same total', async () => {
    const container = await renderTab({
      preview: { ...PREVIEW, assignment_status: 'quoted' },
      quotes: [QUOTE],
      budgetMoved: true,
    });
    expect(texts(container, 'nldd-button')).toContain('Maak nieuwe offerte');
    expect(container.textContent).toContain(
      'De begroting is gewijzigd sinds deze offerte; het totaal is gelijk gebleven.',
    );
    // Offering the old quote would send amounts that no longer hold: the
    // card's next step is the new quote.
    expect(primaries(container)).toEqual(['Maak nieuwe offerte']);
    expect(texts(container, 'nldd-button')).not.toContain('Bied aan');
  });

  it('names the new total when it changed, and proposes nothing while the budget stands', async () => {
    const moved = await renderTab({
      preview: {
        ...PREVIEW,
        assignment_status: 'quoted',
        content: { ...CONTENT, total_cents: 18000000 },
      },
      quotes: [QUOTE],
      budgetMoved: true,
    });
    expect(moved.textContent).toMatch(/staat nu op €\s180\.000/);
    // A different total in the browser is no ground by itself: the server decides.
    const same = await renderTab({
      preview: {
        ...PREVIEW,
        assignment_status: 'quoted',
        content: { ...CONTENT, total_cents: 18000000 },
      },
      quotes: [QUOTE],
      budgetMoved: false,
    });
    expect(texts(same, 'nldd-button')).not.toContain('Maak nieuwe offerte');
  });

  it('puts internal approval between making and offering only where it is required', async () => {
    const container = await renderTab({ quotes: [QUOTE], approval: APPROVAL });
    expect(primaries(container)).toEqual(['Vraag goedkeuring']);
    expect(texts(container, 'nldd-button')).not.toContain('Bied aan');
    expect(texts(container, 'nldd-card nldd-menu-item')).not.toContain('Bied opnieuw aan');
    // The rule, as a fact of the quote; what to do is said in the head of the assignment.
    expect(container.textContent).toContain('Interne goedkeuring nodig: vanaf € 100.000.');
    expect(container.textContent).not.toContain('pas worden aangeboden na interne goedkeuring');
    // Nothing is asked yet: the tag does not say it waits.
    expect(texts(container, 'nldd-card nldd-badge')).toEqual(['Offerte gemaakt']);
    clickButton(container, 'Vraag goedkeuring');
    const openSheet = () =>
      [...document.body.querySelectorAll('nldd-sheet')].find((el) => el.hasAttribute('open'));
    await waitFor(() =>
      expect(openSheet()?.querySelector('nldd-title')?.getAttribute('text')).toBe(
        'Goedkeuring vragen',
      ),
    );
    const sheet = openSheet();
    sheet?.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(lastCalls.some((call) => call.method === 'POST')).toBe(true));
    expect(lastCalls.find((call) => call.method === 'POST')?.body).toEqual({
      note: null,
    });
  });

  it('waits in words while an approver has the quote', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      approval: {
        ...APPROVAL,
        status: 'requested',
        may_request_approval: false,
        may_withdraw: true,
        current: {
          id: 'r-1',
          status: 'requested',
          requested_at: '2026-02-02T09:30:00Z',
          requested_by_name: 'Opdracht Manager',
          request_note: 'Graag voor vrijdag',
        },
      },
    });
    expect(container.textContent).toMatch(
      /Wacht op goedkeuring sinds 2 feb 2026.*gevraagd door Opdracht Manager/,
    );
    expect(container.textContent).toContain('Toelichting bij de aanvraag: Graag voor vrijdag');
    expect(primaries(container)).toEqual([]);
    expect(texts(container, 'nldd-card nldd-menu-item')).toEqual([
      'Trek de aanvraag in',
      'Leg afwijzing vast',
    ]);
  });

  it('says who sent it back and why from the history, when no request is current', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      approval: {
        ...APPROVAL,
        status: 'sent_back',
        may_request_approval: false,
        current: null,
        history: [
          {
            id: 'r-1',
            status: 'sent_back',
            requested_at: '2026-02-02T09:30:00Z',
            decided_at: '2026-02-03T11:00:00Z',
            decided_by_name: 'Collega Goedkeurder',
            decision_note: 'De looptijd klopt niet',
          },
        ],
      },
    });
    expect(container.textContent).toMatch(
      /Teruggestuurd op 3 feb 2026.*door Collega Goedkeurder: De looptijd klopt niet/,
    );
  });

  it('leads to a new quote when the approver sent it back, with the note', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      approval: {
        ...APPROVAL,
        status: 'sent_back',
        may_request_approval: false,
        current: {
          id: 'r-1',
          status: 'sent_back',
          requested_at: '2026-02-02T09:30:00Z',
          decided_at: '2026-02-03T11:00:00Z',
          decided_by_name: 'Collega Goedkeurder',
          decision_note: 'De looptijd klopt niet',
        },
      },
    });
    expect(container.textContent).toMatch(
      /Teruggestuurd op 3 feb 2026.*door Collega Goedkeurder: De looptijd klopt niet/,
    );
    expect(primaries(container)).toEqual(['Maak nieuwe offerte']);
  });

  it('says where the right is granted when nobody can approve', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      approval: { ...APPROVAL, approver_available: false },
    });
    // The head of the assignment says that nobody can approve and who grants
    // the right; the card does not say it again.
    expect(container.querySelector('nldd-card nldd-banner')).toBeNull();
    expect(primaries(container)).toEqual([]);
  });

  it('keeps who approved on the card after the quote is offered', async () => {
    const offered = await renderTab({
      quotes: [QUOTE],
      offers: [LINK_OFFER],
      approval: {
        ...APPROVAL,
        status: 'approved',
        may_offer: true,
        blocked_message: null,
        current: {
          id: 'r-1',
          status: 'approved',
          requested_at: '2026-02-02T09:30:00Z',
          decided_at: '2026-02-03T11:00:00Z',
          decided_by_name: 'Collega Goedkeurder',
        },
      },
    });
    expect(offered.textContent).toMatch(
      /Intern goedgekeurd op 3 feb 2026.*door Collega Goedkeurder/,
    );
  });

  it('offers as before once the quote is approved, and shows no step where none is required', async () => {
    const approved = await renderTab({
      quotes: [QUOTE],
      approval: {
        ...APPROVAL,
        status: 'approved',
        may_offer: true,
        blocked_message: null,
        current: {
          id: 'r-1',
          status: 'approved',
          requested_at: '2026-02-02T09:30:00Z',
          decided_at: '2026-02-03T11:00:00Z',
          decided_by_name: 'Collega Goedkeurder',
        },
      },
    });
    expect(primaries(approved)).toEqual(['Bied aan']);
    expect(approved.textContent).toMatch(
      /Intern goedgekeurd op 3 feb 2026.*door Collega Goedkeurder/,
    );
    const plain = await renderTab({
      quotes: [QUOTE],
      approval: {
        ...APPROVAL,
        approval_required: false,
        may_offer: true,
        blocked_message: null,
      },
    });
    expect(plain.textContent).not.toContain('goedkeuring');
  });

  it('shows nothing about approval for a quote that does not need it', async () => {
    const container = await renderTab({
      quotes: [QUOTE],
      approval: {
        ...APPROVAL,
        approval_required: false,
        may_offer: true,
        blocked_message: null,
        // Nobody holds the right, which is no concern where it is not asked for.
        approver_available: false,
        may_request_approval: true,
        may_decide_approval: true,
        may_withdraw: true,
      },
    });
    expect(container.querySelector('nldd-banner')).toBeNull();
    expect(container.textContent).not.toMatch(/goedkeur/i);
    expect(texts(container, 'nldd-button')).not.toContain('Beoordeel');
    expect(texts(container, 'nldd-card nldd-menu-item').join(' ')).not.toMatch(
      /goedkeur|aanvraag/i,
    );
    expect(primaries(container)).toEqual(['Bied aan']);
  });

  it('shows who decided with the proof, and the bundle for who manages', async () => {
    const accepted = {
      ...QUOTE,
      status: 'accepted',
      acceptance: {
        form: 'signing_link',
        signed_at: '2026-02-10T12:00:00Z',
        signer_name: 'Tekenaar Voorbeeld',
        has_document: false,
      },
    };
    const row = {
      id: 'ev-1',
      decision: 'accept',
      channel: 'signing_link',
      created_at: '2026-02-10T12:00:00Z',
    };
    const container = await renderTab({
      preview: { ...PREVIEW, assignment_status: 'accepted', can_issue: false },
      quotes: [accepted],
      evidence: [row],
    });
    await waitFor(() => expect(texts(container, 'nldd-card nldd-link')).toContain('Bekijk bewijs'));
    const links = [...container.querySelectorAll('nldd-card nldd-link')];
    const href = (text: string) =>
      links.find((el) => el.getAttribute('text') === text)?.getAttribute('href');
    expect(href('Bekijk bewijs')).toBe('/api/proof/evidence/ev-1/page');
    expect(href('Download bewijs')).toBe('/api/proof/evidence/ev-1/bundle');
    expect(container.textContent).not.toContain('bewijspakket');

    const reader = await renderTab({
      preview: { ...PREVIEW, assignment_status: 'accepted', can_issue: false, may_issue: false },
      quotes: [accepted],
      mayManage: false,
      evidence: [row],
    });
    await waitFor(() => expect(texts(reader, 'nldd-card nldd-link')).toContain('Bekijk bewijs'));
    expect(texts(reader, 'nldd-card nldd-link')).not.toContain('Download bewijs');
  });

  it('says so when a decision was recorded the old way, without a proof', async () => {
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
            has_document: false,
          },
        },
      ],
      evidence: [],
    });
    await waitFor(() => expect(container.textContent).toContain('Zonder bewijspakket vastgelegd.'));
    expect(texts(container, 'nldd-card nldd-link')).not.toContain('Bekijk bewijs');
  });

  it('says who can see the signing link to a reader who cannot, and to the others that it is no secret', async () => {
    const reader = await renderTab({
      preview: { ...PREVIEW, may_issue: false },
      quotes: [QUOTE],
      mayManage: false,
      offers: [{ id: 'o-1', channel: 'signing_link', offered_at: '2026-02-02T10:00:00Z' }],
    });
    await waitFor(() => expect(reader.querySelector('[data-offer]')).not.toBeNull());
    expect(reader.textContent).toContain(
      'De tekenlink is zichtbaar voor de eigenaar en de managers van de opdracht.',
    );
    expect(reader.textContent).not.toContain('/tekenen/');

    const manager = await renderTab({ quotes: [QUOTE], offers: [LINK_OFFER] });
    await waitFor(() => expect(manager.querySelector('[data-signing-link]')).not.toBeNull());
    expect(manager.textContent).toContain(
      'De link werkt alleen voor tekenaar@opdrachtgever.example, na inloggen.',
    );
    expect(manager.textContent).not.toContain('zichtbaar voor de eigenaar');
  });

  it('shows the file hash in the details once they are opened', async () => {
    const container = await renderTab({ quotes: [QUOTE] });
    const api = globalThis.fetch;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
        String(input) === '/api/quotes/q-1/document'
          ? new Response('%PDF', { headers: { 'X-Document-SHA256': 'c'.repeat(64) } })
          : api(input, init),
      ),
    );
    const sheet = () =>
      [...document.body.querySelectorAll('nldd-sheet')].find(
        (el) => el.querySelector('nldd-title')?.getAttribute('text') === 'Details van de offerte',
      );
    // Not asked for before anyone looks.
    expect(sheet()?.querySelector('[data-file-line]')).toBeNull();
    clickButton(container, 'Details');
    await waitFor(() => expect(sheet()?.querySelectorAll('[data-file-line]')).toHaveLength(2));
    expect(texts(sheet() as Element, 'nldd-title')).toContain('Bestandskenmerk');
    expect(sheet()?.querySelector('[data-file-line]')?.textContent).toBe(
      'cccccccc cccccccc cccccccc cccccccc',
    );
  });

  it('says what happened to the mail with the link, and offers to send it again', async () => {
    const mailed = (mail: object) => [{ ...LINK_OFFER, mail }];
    const sent = await renderTab({
      quotes: [QUOTE],
      offers: mailed({
        state: 'sent',
        queued_at: '2026-02-02T10:00:00Z',
        sent_at: '2026-02-02T10:01:00Z',
      }),
    });
    await waitFor(() => expect(sent.querySelector('[data-offer]')).not.toBeNull());
    expect(sent.querySelector('[data-offer]')?.textContent).toContain('Gemaild op 2 feb 2026');
    expect(texts(sent, '[data-offer] nldd-menu-item')).toContain('Stuur opnieuw');
    // The link itself stays in reach.
    expect(texts(sent, '[data-offer] nldd-button')).toContain('Kopieer tekenlink');

    const queued = await renderTab({
      quotes: [QUOTE],
      offers: mailed({ state: 'queued', queued_at: '2026-02-02T10:00:00Z' }),
    });
    await waitFor(() => expect(queued.querySelector('[data-offer]')).not.toBeNull());
    expect(queued.querySelector('[data-offer]')?.textContent).toContain('Wordt gemaild');

    const failed = await renderTab({
      quotes: [QUOTE],
      offers: mailed({
        state: 'failed',
        queued_at: '2026-02-02T10:00:00Z',
        failed_reason: 'het adres is geweigerd door de mailserver',
      }),
    });
    await waitFor(() => expect(failed.querySelector('[data-offer]')).not.toBeNull());
    expect(failed.querySelector('[data-offer]')?.textContent).toContain(
      'Mail niet afgeleverd: het adres is geweigerd door de mailserver',
    );
  });

  it('says nothing about mail where the link is not mailed', async () => {
    const container = await renderTab({ quotes: [QUOTE], offers: [LINK_OFFER] });
    await waitFor(() => expect(container.querySelector('[data-offer]')).not.toBeNull());
    expect(container.textContent).not.toMatch(/mail/i);
    expect(texts(container, '[data-offer] nldd-menu-item')).not.toContain('Stuur opnieuw');
    expect(document.body.querySelector('nldd-sheet')?.textContent ?? '').not.toContain('per mail');
  });

  it('takes the file hash and its note from the response, without fetching the file', async () => {
    const container = await renderTab({
      quotes: [
        {
          ...QUOTE,
          document_sha256: 'd'.repeat(64),
          document_note: 'Het bestand is vastgelegd na het maken van de offerte, op 08-10-2026.',
        },
      ],
    });
    const before = lastCalls.length;
    clickButton(container, 'Details');
    const sheet = [...document.body.querySelectorAll('nldd-sheet')].find(
      (el) => el.querySelector('nldd-title')?.getAttribute('text') === 'Details van de offerte',
    ) as Element;
    await waitFor(() => expect(sheet.querySelectorAll('[data-file-line]')).toHaveLength(2));
    expect(sheet.textContent).toContain('vastgelegd na het maken van de offerte');
    expect(lastCalls.slice(before).map((call) => call.url)).not.toContain(
      '/api/quotes/q-1/document',
    );
  });
});
