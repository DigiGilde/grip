import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { clickButton, mockApi, texts } from '@/features/quotes/testing';
import { navigation, receiptFacts } from '@/features/quotes/proof';
import { renderApp } from '@/test/utils';
import { SigningListPage } from './SigningListPage';
import { SigningPage } from './SigningPage';

const HASH = 'b'.repeat(64);

const QUOTE = {
  id: 'q-1',
  uri: 'https://grip.example/id/offerte/q-1',
  reference: 'VG-2026-0007',
  status: 'issued',
  issued_at: '2026-02-01T09:00:00Z',
  contractor_name: 'Testinstantie',
  client_name: 'Voorbeeldministerie',
  snapshot_hash: HASH,
  decided_at: null,
  content: {
    name: 'Opdracht Alfa',
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
    conditions: 'Betaling per maand.',
  },
};

afterEach(() => vi.unstubAllGlobals());

function renderSigning(replies: Record<string, unknown>) {
  const api = mockApi(replies);
  const view = renderApp(
    <Routes>
      <Route path="/tekenen/:quoteId" element={<SigningPage />} />
    </Routes>,
    { path: '/tekenen/q-1' },
  );
  return { ...api, container: view.container };
}

const EVIDENCE = {
  id: 'ev-1',
  decision: 'accept',
  channel: 'signing_link',
  quote_id: 'q-1',
  sound: true,
  proven: ['De handtekening van de instantie onder de verklaring klopt.'],
  not_proven: ['Het mandaat ligt buiten grip vast.'],
  wrong: [],
  has_identity_statement: true,
  has_timestamp: false,
  statement: {
    besluit: 'akkoord',
    offerte: { kenmerk: 'VG-2026-0007', totaal_centen: 17280000 },
    wie: { naam: 'Tekenaar Voorbeeld', functie: 'Directeur' },
    // An organisation as the contract names it, not a plain string.
    namens: { name: 'Voorbeeldministerie', tooi_uri: 'https://identifier.example/org/1' },
    wanneer: { aangemeld_op: '2026-02-03T09:58:00Z', ontvangen_op: '2026-02-03T10:00:00Z' },
    hoe: { aanmelding: { ontbreekt_omdat: 'De provider vroeg niet opnieuw om in te loggen.' } },
  },
};

const openSheet = () =>
  [...document.body.querySelectorAll('nldd-sheet')].find((el) => el.hasAttribute('open'));

describe('SigningPage', () => {
  it('is the quote, the amount, who offers it, and one decision', async () => {
    const { container } = renderSigning({ '/api/signing/quotes/q-1': QUOTE });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('h1')?.textContent).toBe('Offerte Opdracht Alfa');
    const amount = container.querySelector('nldd-title[heading-level="2"]');
    expect(amount?.getAttribute('text')).toMatch(/^€\s172\.800$/);
    expect(amount?.getAttribute('overline')).toBe('Testinstantie biedt aan');
    expect(container.textContent).toContain('Aan Voorbeeldministerie · kenmerk VG-2026-0007');
    expect(container.textContent).toContain('Betaling per maand.');
    // One primary, one secondary, and what signing means in one sentence.
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual(['Geef akkoord']);
    expect(texts(container, 'nldd-button').filter((text) => text !== 'Details')).toEqual([
      'Geef akkoord',
      'Wijs af',
    ]);
    expect(container.textContent).toContain(
      'Met je akkoord gaat Voorbeeldministerie deze opdracht aan',
    );
    // The echtheidskenmerk is there, behind "Details".
    expect(texts(container, 'nldd-button')).toContain('Details');
    expect(document.body.querySelectorAll('nldd-sheet [data-code-line]').length).toBe(2);
    // No form is open by default.
    expect(openSheet()).toBeUndefined();
  });

  it('does not send an acceptance without the mandate confirmation', async () => {
    const { container, calls } = renderSigning({
      '/api/signing/quotes/q-1': QUOTE,
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    clickButton(container, 'Geef akkoord');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    expect(sheet.querySelector('nldd-checkbox-field')?.getAttribute('label')).toContain(
      'namens Voorbeeldministerie',
    );
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text')).toBe(
        'Bevestig dat je namens de opdrachtgever mag tekenen.',
      ),
    );
    expect(calls.filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('leaves for the login with the fingerprint that was shown, and decides nothing yet', async () => {
    const go = vi.spyOn(navigation, 'go').mockImplementation(() => {});
    const { container, calls } = renderSigning({
      '/api/signing/quotes/q-1': QUOTE,
      'POST /api/signing/quotes/q-1/intents': {
        id: 'in-1',
        authorize_url: '/api/signing/intents/in-1/authorize',
        expires_at: '2026-02-03T10:05:00Z',
        reauthentication: true,
      },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    clickButton(container, 'Geef akkoord');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    // One calm sentence on what happens next.
    expect(sheet.textContent).toContain(
      'Om te bevestigen dat jij dit bent, log je opnieuw in. Daarna is je akkoord vastgelegd.',
    );
    sheet
      .querySelector('nldd-checkbox-field')
      ?.dispatchEvent(new CustomEvent('change', { detail: { checked: true } }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-checkbox-field')?.hasAttribute('checked')).toBe(true),
    );
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(go).toHaveBeenCalledWith('/api/signing/intents/in-1/authorize'));
    const posts = calls.filter((call) => call.method === 'POST');
    // Only the intent was sent; the old route that decides at once is not used.
    expect(posts.map((call) => call.url)).toEqual(['/api/signing/quotes/q-1/intents']);
    expect(posts[0]?.body).toEqual({
      decision: 'accept',
      quote_hash: HASH,
      return_path: '/tekenen/q-1',
      signer_function: null,
      organisation_name: null,
      confirm_mandate: true,
    });
    // Still open: nothing was decided.
    expect(texts(container, 'nldd-button')).toContain('Geef akkoord');
    go.mockRestore();
  });

  it('says to confirm with the passkey once the intent asks for it, and states it on the receipt', async () => {
    const go = vi.spyOn(navigation, 'go').mockImplementation(() => {});
    const { container } = renderSigning({
      '/api/signing/quotes/q-1': QUOTE,
      'POST /api/signing/quotes/q-1/intents': {
        id: 'in-1',
        authorize_url: '/api/signing/intents/in-1/authorize',
        expires_at: '2026-02-03T10:05:00Z',
        reauthentication: true,
        passkey: {
          options_url: '/api/signing/intents/in-1/passkey/options',
          verify_url: '/api/signing/intents/in-1/passkey',
        },
      },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    clickButton(container, 'Wijs af');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    expect(sheet.textContent).toContain('log je opnieuw in');
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(sheet.textContent).toContain(
        'Bevestig met je passkey. Daarna is je afwijzing vastgelegd.',
      ),
    );
    go.mockRestore();
    expect(
      receiptFacts({
        decision: 'accept',
        statement: { ...EVIDENCE.statement, hoe: { passkey: { gebruiker_geverifieerd: true } } },
      }),
    ).toContainEqual({ label: 'Bevestigd met', value: 'Passkey' });
    expect(receiptFacts(EVIDENCE).some((fact) => fact.label === 'Bevestigd met')).toBe(false);
  });

  it('shows the receipt on return, with nothing about how the login went', async () => {
    const go = vi.spyOn(navigation, 'go').mockImplementation(() => {});
    mockApi({
      '/api/signing/quotes/q-1': { ...QUOTE, status: 'accepted' },
      '/api/signing/evidence/ev-1': EVIDENCE,
    });
    const { container } = renderApp(
      <Routes>
        <Route path="/tekenen/:quoteId" element={<SigningPage />} />
      </Routes>,
      { path: '/tekenen/q-1?bewijs=ev-1' },
    );
    await waitFor(() => expect(container.querySelector('[data-receipt]')).not.toBeNull());
    const banner = container.querySelector('[data-receipt]');
    expect(banner?.getAttribute('text')).toBe('Je akkoord is vastgelegd');
    expect(banner?.getAttribute('variant')).toBe('success');
    const facts = texts(container, 'nldd-list nldd-text-cell');
    expect(facts).toContain('Akkoord');
    expect(facts.some((text) => /^VG-2026-0007 · €\s172\.800$/.test(text))).toBe(true);
    expect(facts).toContain('Tekenaar Voorbeeld (Directeur)');
    expect(facts).toContain('Voorbeeldministerie');
    // One primary action, the bundle; the statement and the pdf next to it.
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual(['Download bewijs']);
    expect(texts(container, 'nldd-link')).toEqual(
      expect.arrayContaining(['Bekijk akkoordverklaring', 'Bekijk pdf', 'Controleer een bewijs']),
    );
    clickButton(container, 'Download bewijs');
    expect(go).toHaveBeenCalledWith('/api/signing/evidence/ev-1/bundle');
    // The signer reads nothing about the login: no judgement, no notice.
    expect(container.textContent).not.toMatch(/opnieuw|zwakker|minder sterk|mandaat|provider/i);
    expect(container.querySelector('nldd-banner[variant="warning"]')).toBeNull();
    go.mockRestore();
  });

  it('says what happened when the decision did not go through, and opens the form as it was', async () => {
    sessionStorage.setItem(
      'grip.besluit.q-1',
      JSON.stringify({ decision: 'reject', reason: 'Het bedrag is te hoog' }),
    );
    const { container } = (() => {
      mockApi({ '/api/signing/quotes/q-1': QUOTE });
      return renderApp(
        <Routes>
          <Route path="/tekenen/:quoteId" element={<SigningPage />} />
        </Routes>,
        { path: '/tekenen/q-1?besluit_fout=geweigerd' },
      );
    })();
    await waitFor(() => expect(container.querySelector('[data-decision-error]')).not.toBeNull());
    const banner = container.querySelector('[data-decision-error]');
    expect(banner?.getAttribute('text')).toBe('Er is niets vastgelegd');
    expect(banner?.getAttribute('supporting-text')).toBe('Je hebt het inloggen afgebroken.');
    clickButton(container, 'Probeer opnieuw');
    await waitFor(() =>
      expect(openSheet()?.querySelector('nldd-title')?.getAttribute('text')).toBe(
        'Offerte afwijzen',
      ),
    );
    expect(
      [...(openSheet()?.querySelectorAll('[value]') ?? [])].map((el) => el.getAttribute('value')),
    ).toContain('Het bedrag is te hoog');
    expect(container.querySelector('[data-decision-error]')).toBeNull();
    sessionStorage.clear();
  });

  it('asks for the organisation when the quote names no client', async () => {
    const { container } = renderSigning({
      '/api/signing/quotes/q-1': { ...QUOTE, client_name: null },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const labels = [...document.body.querySelectorAll('nldd-sheet nldd-form-field')].map((el) =>
      el.getAttribute('label'),
    );
    expect(labels).toContain('Organisatie namens wie je tekent');
  });

  it('explains a link that leads nowhere without saying whether the quote exists', async () => {
    const { container } = renderSigning({});
    await waitFor(() =>
      expect(container.querySelector('[data-state="not-found"]')?.textContent).toContain(
        'Deze offerte staat niet voor je klaar',
      ),
    );
    expect(texts(container, 'nldd-button')).toEqual([]);
  });

  it('offers no decision on a quote that was replaced', async () => {
    const { container } = renderSigning({
      '/api/signing/quotes/q-1': { ...QUOTE, status: 'superseded' },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-banner')?.getAttribute('text')).toContain('vervangen');
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual([]);
  });
});

describe('SigningListPage', () => {
  it('says so when nothing is waiting', async () => {
    mockApi({ '/api/signing/invitations': { invitations: [] } });
    const { container } = renderApp(<SigningListPage />, { path: '/tekenen' });
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
        'Er staat geen offerte voor je klaar',
      ),
    );
  });

  it('links each invitation to its quote with a name that says which', async () => {
    mockApi({
      '/api/signing/invitations': {
        invitations: [
          {
            quote_id: 'q-1',
            reference: 'VG-2026-0007',
            assignment_name: 'Opdracht Alfa',
            status: 'issued',
            issued_at: '2026-02-01T09:00:00Z',
            valid_until: null,
            expires_at: null,
          },
        ],
      },
    });
    const { container } = renderApp(<SigningListPage />, { path: '/tekenen' });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const link = container.querySelector('nldd-table nldd-link');
    expect(link?.getAttribute('href')).toBe('/tekenen/q-1');
    expect(link?.getAttribute('accessible-label')).toBe(
      'Bekijk en teken: offerte VG-2026-0007 voor Opdracht Alfa',
    );
  });
});
