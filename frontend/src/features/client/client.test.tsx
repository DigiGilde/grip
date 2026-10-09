import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { mockApi, texts } from '@/features/team/ui/testing';
import { AdminPage } from '@/pages/AdminPage';
import { PATHS } from '@/paths';
import { renderApp, TEST_PERSON } from '@/test/utils';
import { ClientAssignmentPage } from './ClientAssignmentPage';
import { ClientPage } from './ClientPage';
import { deliveryText } from './labels';
import { clientAssignmentPath, clientPath, receivedQuotePath } from './paths';
import { ReceivedQuotePage } from './ReceivedQuotePage';
import { navigation } from '@/features/quotes/proof';
import { validateRequest } from './requestForm';
import { RequestQuotePage } from './RequestQuotePage';

afterEach(() => vi.unstubAllGlobals());

const ASSIGNMENT = {
  id: 'a-1',
  uri: 'https://grip.example/id/opdracht/a-1',
  name: 'Opdracht Alfa',
  status: 'quoted',
  contractor_name: 'Voorbeeldgilde',
  start_date: '2026-07-01',
  end_date: '2027-06-30',
  created_at: '2026-06-01T09:00:00Z',
  context_count: 1,
  latest_quote: {
    id: 'q-1',
    status: 'issued',
    issued_at: '2026-06-02T10:00:00Z',
    total_cents: 8640000,
  },
  request_delivery: {
    operation: 'sendAssignmentRequest',
    status: 'sent',
    queued_at: '2026-06-01T09:00:00Z',
    sent_at: '2026-06-01T09:00:20Z',
    attempts: 1,
  },
};

const CONTENT = {
  name: 'Opdracht Alfa',
  lines: [
    {
      position: 1,
      description: 'Productmanager',
      kind: 'personnel',
      role: 'Productmanager',
      fte: '0.8',
      rate_category: 'D',
      start_date: '2026-07-01',
      end_date: '2026-12-31',
      monthly_rates: [{ year: 2026, monthly_rate_cents: 1800000 }],
      amount_cents: 8640000,
    },
  ],
  subtotals_per_year: [{ year: 2026, amount_cents: 8640000 }],
  total_cents: 8640000,
};

const QUOTE = {
  id: 'q-1',
  uri: 'https://grip.opdrachtnemer.example/id/offerte/q-1',
  assignment_id: 'a-1',
  status: 'issued',
  issued_at: '2026-06-02T10:00:00Z',
  issued_by_name: null,
  total_cents: 8640000,
  snapshot_hash: 'ab'.repeat(32),
  content: CONTENT,
};

describe('validateRequest', () => {
  const valid = { contractor: 'p-1', name: 'Opdracht Alfa', startDate: '', endDate: '' };

  it('accepts a request without period and without context', () => {
    expect(validateRequest(valid)).toBeNull();
  });

  it('asks for a contractor, a name and a period in order', () => {
    expect(validateRequest({ ...valid, contractor: '' })).toContain('opdrachtnemer');
    expect(validateRequest({ ...valid, name: '  ' })).toContain('naam');
    expect(validateRequest({ ...valid, startDate: '2027-01-01', endDate: '2026-01-01' })).toContain(
      'einddatum',
    );
  });
});

describe('deliveryText', () => {
  it('says whether the other side has the message', () => {
    expect(deliveryText(null)).toBe('Niet verstuurd');
    expect(deliveryText({ operation: 'sendAcceptance', status: 'pending', queued_at: '' })).toBe(
      'Het akkoord wacht op verzending',
    );
    expect(
      deliveryText({ operation: 'sendAssignmentRequest', status: 'sent', queued_at: '' }),
    ).toBe('De aanvraag is aangekomen bij de opdrachtnemer');
  });
});

describe('ClientPage', () => {
  it('lists the sent requests with their delivery and offers to request a quote', async () => {
    mockApi({ '/api/client/assignments': { may_request: true, items: [ASSIGNMENT] } });
    const { container } = renderApp(<ClientPage />, { path: PATHS.client });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const link = container.querySelector('nldd-table nldd-link');
    expect(link?.getAttribute('text')).toBe('Opdracht Alfa');
    expect(link?.getAttribute('href')).toBe(clientAssignmentPath('a-1'));
    expect(texts(container, 'nldd-table nldd-badge')).toEqual(['Offerte gemaakt', 'Aangekomen']);
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Voorbeeldgilde');
    expect(texts(container, 'nldd-button')).toContain('Offerte aanvragen');
  });

  it('hides amounts and the request button from who may not use them', async () => {
    const { total_cents: _hidden, ...quoteWithoutAmount } = ASSIGNMENT.latest_quote;
    mockApi({
      '/api/client/assignments': {
        may_request: false,
        items: [{ ...ASSIGNMENT, latest_quote: quoteWithoutAmount }],
      },
    });
    const { container } = renderApp(<ClientPage />, { path: PATHS.client });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(texts(container, 'nldd-table-row[slot="header"] nldd-text-cell')).not.toContain(
      'Offerte',
    );
    expect(texts(container, 'nldd-button')).not.toContain('Offerte aanvragen');
  });

  it('shows the received quotes and marks the ones waiting for this person', async () => {
    mockApi({
      '/api/received-quotes': {
        items: [
          {
            id: 'q-1',
            assignment_id: 'a-1',
            assignment_name: 'Opdracht Alfa',
            contractor_name: 'Voorbeeldgilde',
            status: 'issued',
            issued_at: '2026-06-02T10:00:00Z',
            total_cents: 8640000,
            may_decide: true,
          },
        ],
      },
    });
    const { container } = renderApp(<ClientPage />, { path: clientPath('offertes') });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-table nldd-link')?.getAttribute('href')).toBe(
      receivedQuotePath('q-1'),
    );
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Wacht op je besluit');
  });

  it('shows the received requests with an empty state when there are none', async () => {
    mockApi({ '/api/received-requests': { items: [] } });
    const { container } = renderApp(<ClientPage />, { path: clientPath('ontvangen') });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain('Er zijn geen ontvangen aanvragen'),
    );
    expect(container.querySelector('nldd-table')).toBeNull();
  });
});

describe('RequestQuotePage', () => {
  it('offers the connected contractors and says when sending would not work', async () => {
    mockApi({
      '/api/client/options': {
        may_request: true,
        problem: 'Het verkeer met andere organisaties staat uit in deze instantie.',
        contractors: [
          {
            peer_id: 'p-1',
            name: 'Voorbeeldgilde',
            base_uri: 'https://x.example',
            reachable: true,
          },
        ],
      },
      '/api/nodes/corpora': {
        problem: 'Er is geen corpus gekoppeld aan deze instantie. Je kunt doorgaan zonder context.',
      },
    });
    const { container } = renderApp(<RequestQuotePage />, { path: PATHS.clientRequest });
    await waitFor(() => expect(container.querySelector('select')).not.toBeNull());
    const options = [...container.querySelectorAll('select option')].map((el) => el.textContent);
    expect(options).toEqual(['Kies een opdrachtnemer', 'Voorbeeldgilde']);
    expect(texts(container, 'nldd-banner[variant="warning"]')).toEqual([
      'Het verkeer met andere organisaties staat uit in deze instantie.',
    ]);
    // Without a corpus the picker says so, and the request can still be sent.
    await waitFor(() =>
      expect(texts(container, 'nldd-banner[variant="neutral"]')[0]).toContain('geen corpus'),
    );
    // Nothing chosen and no explanation: the heading says the field is optional.
    expect(texts(container, 'nldd-inline-dialog')).not.toContain('Nog geen context gekozen');
    expect(container.textContent).not.toContain('Context is niet verplicht');
    expect(texts(container, 'nldd-button')).toContain('Verstuur aanvraag');
  });

  it('tells a person without the function why there is no form', async () => {
    mockApi({ '/api/client/options': { may_request: false, problem: null } });
    const { container } = renderApp(<RequestQuotePage />, { path: PATHS.clientRequest });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toEqual(['Je kunt geen offerte aanvragen']),
    );
    expect(container.querySelector('select')).toBeNull();
    expect(texts(container, 'nldd-button')).not.toContain('Verstuur aanvraag');
  });
});

function renderAt(path: string, pattern: string, element: React.ReactElement) {
  return renderApp(
    <Routes>
      <Route path={pattern} element={element} />
    </Routes>,
    { path },
  );
}

describe('ReceivedQuotePage', () => {
  const DETAIL = {
    assignment_id: 'a-1',
    assignment_name: 'Opdracht Alfa',
    contractor_name: 'Voorbeeldgilde',
    may_decide: true,
    quote: QUOTE,
    deliveries: [],
  };

  it('shows the snapshot with its hash and lets a tekenbevoegde decide', async () => {
    mockApi({ '/api/received-quotes/q-1': DETAIL });
    const { container } = renderAt(
      receivedQuotePath('q-1'),
      PATHS.receivedQuote,
      <ReceivedQuotePage />,
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Productmanager');
    expect(container.textContent).toContain('ab'.repeat(32));
    expect(texts(container, 'nldd-button')).toEqual(
      expect.arrayContaining(['Geef akkoord', 'Wijs af']),
    );
  });

  it('sends an acceptance through the login and decides nothing before the return', async () => {
    const go = vi.spyOn(navigation, 'go').mockImplementation(() => {});
    const { calls } = mockApi({
      '/api/received-quotes/q-1': DETAIL,
      '/api/proof/intents': {
        id: 'in-1',
        authorize_url: '/api/proof/intents/in-1/authorize',
        expires_at: '2026-02-03T10:05:00Z',
        reauthentication: true,
      },
    });
    const { container } = renderAt(
      receivedQuotePath('q-1'),
      PATHS.receivedQuote,
      <ReceivedQuotePage />,
    );
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.textContent).toContain('Daarna is je akkoord vastgelegd.');
    [...container.querySelectorAll('nldd-button')]
      .find((el) => el.getAttribute('text') === 'Geef akkoord')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    const dialog = await waitFor(() => {
      const found = [...document.body.querySelectorAll('nldd-button')].filter(
        (el) => el.getAttribute('text') === 'Geef akkoord',
      );
      expect(found.length).toBeGreaterThan(1);
      return found[found.length - 1] as Element;
    });
    dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await waitFor(() => expect(go).toHaveBeenCalledWith('/api/proof/intents/in-1/authorize'));
    // Only the intent was asked for; the old route that decides at once is not used.
    expect(calls).toContain('/api/proof/intents');
    expect(calls.some((url) => url.includes('/acceptance'))).toBe(false);
    go.mockRestore();
  });

  it('says that nothing was recorded when the browser returns with an error', async () => {
    mockApi({ '/api/received-quotes/q-1': DETAIL });
    const { container } = renderAt(
      `${receivedQuotePath('q-1')}?besluit_fout=verlopen`,
      PATHS.receivedQuote,
      <ReceivedQuotePage />,
    );
    await waitFor(() => expect(container.querySelector('[data-decision-error]')).not.toBeNull());
    expect(container.querySelector('[data-decision-error]')?.getAttribute('supporting-text')).toBe(
      'Het duurde te lang tussen je keuze en het inloggen.',
    );
  });

  it('shows a decision and whether it reached the contractor, without buttons', async () => {
    mockApi({
      '/api/received-quotes/q-1': {
        ...DETAIL,
        may_decide: false,
        quote: {
          ...QUOTE,
          status: 'accepted',
          acceptance: {
            form: 'own_instance',
            signed_at: '2026-06-03T10:00:00Z',
            signer_name: 'Tekenbevoegde Voorbeeld',
            signer_function: 'Directeur',
          },
        },
        deliveries: [
          {
            operation: 'sendAcceptance',
            status: 'sent',
            queued_at: '2026-06-03T10:00:00Z',
            sent_at: '2026-06-03T10:00:15Z',
            attempts: 1,
          },
        ],
      },
    });
    const { container } = renderAt(
      receivedQuotePath('q-1'),
      PATHS.receivedQuote,
      <ReceivedQuotePage />,
    );
    await waitFor(() =>
      expect(texts(container, 'nldd-banner[variant="success"]')).toEqual([
        'Op deze offerte is akkoord gegeven',
      ]),
    );
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain(
      'Het akkoord is aangekomen bij de opdrachtnemer',
    );
    expect(texts(container, 'nldd-button')).not.toContain('Geef akkoord');
  });

  it('says so when the reader may not see the content', async () => {
    const { content: _c, snapshot_hash: _h, total_cents: _t, ...basics } = QUOTE;
    mockApi({ '/api/received-quotes/q-1': { ...DETAIL, may_decide: false, quote: basics } });
    const { container } = renderAt(
      receivedQuotePath('q-1'),
      PATHS.receivedQuote,
      <ReceivedQuotePage />,
    );
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain(
        'Je ziet de inhoud van deze offerte niet',
      ),
    );
    expect(container.querySelector('nldd-table')).toBeNull();
  });

  it('explains a quote that is not there', async () => {
    mockApi({});
    const { container } = renderAt(
      receivedQuotePath('q-9'),
      PATHS.receivedQuote,
      <ReceivedQuotePage />,
    );
    await waitFor(() =>
      expect(container.querySelector('[data-state="not-found"]')?.textContent).toContain(
        'Deze offerte is niet gevonden',
      ),
    );
  });
});

describe('ClientAssignmentPage', () => {
  const DETAIL = {
    ...ASSIGNMENT,
    description: 'Fictieve aanvraag.',
    context_refs: ['https://corpus.voorbeeldministerie.example/id/node/n-1'],
    quotes: [ASSIGNMENT.latest_quote],
    contractor_reachable: true,
    may_request_usage: true,
  };
  const CONTEXT = {
    peildatum: '2026-10-08',
    acceptance_date: null,
    items: [
      {
        uri: 'https://corpus.voorbeeldministerie.example/id/node/n-1',
        resolved: true,
        node: {
          uri: 'https://corpus.voorbeeldministerie.example/id/node/n-1',
          type: 'instrument',
          title: 'Opdracht bouwsteen Alfa',
          managing_organisation: { name: 'Voorbeeldministerie' },
        },
        origins: [{ uri: 'u-3', title: 'Motie over hergebruik' }],
        steps_to_origin: 2,
      },
      {
        uri: 'https://corpus.anderministerie.example/id/node/n-2',
        resolved: false,
        problem: 'Voor deze URI is geen corpus gekoppeld aan deze instantie.',
      },
    ],
  };

  it('shows the request, its resolved context, the quotes and the progress', async () => {
    mockApi({
      '/api/client/assignments/a-1': DETAIL,
      '/api/assignments/a-1/context': CONTEXT,
      '/api/client/assignments/a-1/progress': {
        available: true,
        fetched_at: '2026-10-08T10:00:00Z',
        status: 'in_progress',
        as_of: '2026-09-30',
        summary: 'Eerste versie opgeleverd.',
        milestones: [{ description: 'Eerste versie', due_date: '2026-09-15', state: 'done' }],
        delivered: ['Eerste versie'],
      },
      '/api/client/assignments/a-1/final-report': { received: false },
    });
    const { container } = renderAt(
      clientAssignmentPath('a-1'),
      PATHS.clientAssignment,
      <ClientAssignmentPage />,
    );
    await waitFor(() => expect(container.textContent).toContain('Eerste versie opgeleverd.'));
    await waitFor(() => expect(container.textContent).toContain('Motie over hergebruik'));
    // The context is a card per node that says where it comes from; the
    // chain itself is in the detail.
    const cards = [...container.querySelectorAll('nldd-card')].map((el) => el.textContent ?? '');
    expect(texts(container, 'nldd-card nldd-title')[0]).toBe('Opdracht bouwsteen Alfa');
    expect(cards[0]).toContain('Komt voort uit: Motie over hergebruik (2 stappen)');
    // A URI nobody answers for stays visible, with the reason.
    expect(cards[1]).toContain('https://corpus.anderministerie.example/id/node/n-2');
    expect(cards[1]).toContain('geen corpus gekoppeld');
    expect(texts(container, 'nldd-text-cell')).toContain(
      'De aanvraag is aangekomen bij de opdrachtnemer',
    );
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Klaar');
    // Spending is offered as an action, and nothing was asked yet.
    expect(texts(container, 'nldd-button')).toContain('Vraag de uitputting op');
    expect(container.querySelector('nldd-table[accessible-label^="Uitputting"]')).toBeNull();
    // No final report came in, so no empty section for it.
    expect(texts(container, 'nldd-title')).not.toContain('Eindrapport');
  });

  it('does not offer the spending to who may not read amounts', async () => {
    mockApi({
      '/api/client/assignments/a-1': {
        ...DETAIL,
        may_request_usage: false,
        contractor_reachable: false,
        context_refs: [],
      },
      '/api/client/assignments/a-1/final-report': { received: false },
    });
    const { container } = renderAt(
      clientAssignmentPath('a-1'),
      PATHS.clientAssignment,
      <ClientAssignmentPage />,
    );
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain(
        'De voortgang is hier niet op te vragen',
      ),
    );
    expect(texts(container, 'nldd-button')).not.toContain('Vraag de uitputting op');
    expect(texts(container, 'nldd-inline-dialog')).toContain('Deze opdracht heeft geen context');
  });
});

describe('AdminPage', () => {
  it('lists the settings pages for the beheerder', () => {
    const { container } = renderApp(<AdminPage />, {
      path: PATHS.admin,
      auth: { status: 'authenticated', person: TEST_PERSON, functions: ['beheerder'] },
    });
    const items = [...container.querySelectorAll('nldd-list-item')].map((el) =>
      el.getAttribute('href'),
    );
    // Grouped by what a beheerder does: people, money, documents, connections, oversight.
    expect(items).toEqual([
      PATHS.wiesProposals,
      PATHS.roles,
      PATHS.functionFramework,
      PATHS.rates,
      PATHS.quoteSender,
      PATHS.quoteSettings,
      PATHS.vacancySetup,
      PATHS.vacancyStandardTexts,
      PATHS.peers,
      PATHS.organisations,
      PATHS.languageModel,
      PATHS.client,
      PATHS.activity,
    ]);
    expect(
      [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
        el.getAttribute('text'),
      ),
    ).toEqual(['Mensen en rollen', 'Geld', 'Documenten en teksten', 'Verbindingen', 'Toezicht']);
  });

  it('tells anyone else that it is for the beheerder', () => {
    const { container } = renderApp(<AdminPage />, { path: PATHS.admin });
    expect(container.querySelector('nldd-list')).toBeNull();
    const state = container.querySelector('[data-state="no-access"]');
    expect(state?.textContent).toContain('Je hebt hier geen toegang');
    expect(state?.textContent).toContain('Beheer is voor beheerders');
  });
});
