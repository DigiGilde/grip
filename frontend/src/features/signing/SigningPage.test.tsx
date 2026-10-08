import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { clickButton, mockApi, texts } from '@/features/quotes/testing';
import { renderApp } from '@/test/utils';
import { SigningListPage } from './SigningListPage';
import { SigningPage } from './SigningPage';

const HASH = 'b'.repeat(64);

const QUOTE = {
  id: 'q-1',
  uri: 'https://grip.example/id/offerte/q-1',
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

describe('SigningPage', () => {
  it('shows the whole quote and its hash before asking for a decision', async () => {
    const { container } = renderSigning({ '/api/signing/quotes/q-1': QUOTE });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('h1')?.textContent).toBe('Offerte Opdracht Alfa');
    expect(container.textContent).toContain('Van Testinstantie aan Voorbeeldministerie');
    expect(container.textContent).toContain(HASH);
    expect(container.textContent).toContain('Betaling per maand.');
    expect(texts(container, 'nldd-button')).toEqual(['Geef akkoord', 'Wijs af']);
    expect(container.querySelector('nldd-checkbox-field')?.getAttribute('label')).toContain(
      'namens Voorbeeldministerie',
    );
  });

  it('does not send an acceptance without the mandate confirmation', async () => {
    const { container, calls } = renderSigning({ '/api/signing/quotes/q-1': QUOTE });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    clickButton(container, 'Geef akkoord');
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text')).toBe(
        'Bevestig dat je namens de opdrachtgever mag tekenen.',
      ),
    );
    expect(calls.filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('sends the hash that was shown once the mandate is confirmed', async () => {
    const { container, calls } = renderSigning({
      '/api/signing/quotes/q-1': QUOTE,
      'POST /api/signing/quotes/q-1/accept': {
        ...QUOTE,
        status: 'accepted',
        decided_at: '2026-02-03T10:00:00Z',
      },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    container
      .querySelector('nldd-checkbox-field')
      ?.dispatchEvent(new CustomEvent('change', { detail: { checked: true } }));
    await waitFor(() =>
      expect(container.querySelector('nldd-checkbox-field')?.hasAttribute('checked')).toBe(true),
    );
    clickButton(container, 'Geef akkoord');
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[variant="success"]')?.getAttribute('text')).toBe(
        'Deze offerte is getekend',
      ),
    );
    const post = calls.find((call) => call.method === 'POST');
    expect(post?.body).toEqual({
      quote_hash: HASH,
      signer_function: null,
      organisation_name: null,
      confirm_mandate: true,
    });
    // Signed: the decision is no longer on offer.
    expect(texts(container, 'nldd-button')).not.toContain('Geef akkoord');
  });

  it('asks for the organisation when the quote names no client', async () => {
    const { container } = renderSigning({
      '/api/signing/quotes/q-1': { ...QUOTE, client_name: null },
    });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const labels = [...container.querySelectorAll('nldd-form-field')].map((el) =>
      el.getAttribute('label'),
    );
    expect(labels).toContain('Organisatie namens wie je tekent');
  });

  it('explains a link that leads nowhere without saying whether the quote exists', async () => {
    const { container } = renderSigning({});
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
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
    expect(texts(container, 'nldd-button')).toEqual([]);
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
    expect(link?.getAttribute('accessible-label')).toBe('Open de offerte voor Opdracht Alfa');
  });
});
