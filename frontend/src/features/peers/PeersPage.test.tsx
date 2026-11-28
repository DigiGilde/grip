import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { TEST_PERSON, renderApp } from '@/test/utils';
import { PeersPage } from './PeersPage';

const PEER = {
  id: 'p-1',
  peer_id: '00000000000000000020',
  name: 'Voorbeeldgilde',
  organisation_tooi_uri: '',
  base_uri: 'https://grip.opdrachtnemer.example',
  role: 'counterpart',
  grant_hashes: { 'grip-opdrachtverkeer': '$1$4$grant' },
  financial_inspection: true,
  is_example: false,
  is_active: true,
  key_count: 1,
  jwks_fetched_at: '2026-10-08T10:00:00Z',
  undelivered: 0,
};
const SERVICES = ['grip-opdrachtverkeer', 'corpus-context'];

afterEach(() => vi.unstubAllGlobals());

async function renderPeers(
  body: object,
  path = '/beheer/koppelingen',
  more: Record<string, unknown> = {},
) {
  mockApi({ '/api/peers': body, ...more });
  const view = renderApp(<PeersPage />, {
    path,
    auth: { status: 'authenticated', person: TEST_PERSON, functions: ['beheerder'] },
  });
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return view.container;
}

describe('PeersPage', () => {
  it('lists a peer with its kind, its contract and its status', async () => {
    const container = await renderPeers({
      items: [PEER],
      services: SERVICES,
      outway_configured: true,
    });
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(container.querySelector('nldd-table nldd-link[text="Voorbeeldgilde"]')).not.toBeNull();
    expect(cells).toContain('Opdrachtgever of opdrachtnemer');
    expect(cells).toContain('grip-opdrachtverkeer');
    // A peer that works carries no status; only one that is switched off does.
    expect(container.querySelector('nldd-table nldd-badge')).toBeNull();
    expect(container.querySelector('nldd-banner[variant="warning"]')).toBeNull();
    const kind = container.querySelector('nldd-text-cell[supporting-text="Met financiële inzage"]');
    expect(kind).not.toBeNull();
  });

  it('marks a peer that is switched off and one without a grant hash', async () => {
    const container = await renderPeers({
      items: [{ ...PEER, is_active: false, grant_hashes: {}, financial_inspection: false }],
      services: SERVICES,
      outway_configured: true,
    });
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('Geen grant hash vastgelegd');
    const status = container.querySelector('nldd-table nldd-badge');
    expect(status?.getAttribute('text')).toBe('Uitgeschakeld');
  });

  it('marks an example instance as a peer nothing is exchanged with', async () => {
    const container = await renderPeers({
      items: [{ ...PEER, is_example: true }],
      services: SERVICES,
      outway_configured: true,
    });
    const status = container.querySelector('nldd-table nldd-badge');
    expect(status?.getAttribute('text')).toBe('Voorbeeld, geen verkeer');
  });

  it('marks a peer to which messages do not arrive', async () => {
    const container = await renderPeers({
      items: [{ ...PEER, undelivered: 2 }],
      services: SERVICES,
      outway_configured: true,
    });
    const status = container.querySelector('nldd-table nldd-badge');
    expect(status?.getAttribute('text')).toBe('Berichten komen niet aan');
  });

  it('opens the peer the address names, as a task leads to it', async () => {
    const container = await renderPeers(
      { items: [{ ...PEER, undelivered: 1 }], services: SERVICES, outway_configured: true },
      '/beheer/koppelingen?koppeling=p-1&bij-taak=t-1',
      {
        '/api/peers/p-1/undelivered': {
          items: [
            {
              id: 'm-1',
              kind: 'Verzoek om een kostenpost',
              reason: 'De ontvanger kent deze instantie niet',
              since: '2026-11-28T09:00:00Z',
              retry_until: null,
              final: true,
            },
          ],
        },
      },
    );
    // The sheet sits in a portal on the body.
    expect(container.querySelector('nldd-table')).not.toBeNull();
    await waitFor(() =>
      expect(texts(document.body, 'nldd-title')).toContain('Berichten die niet aankomen'),
    );
    expect(texts(document.body, 'nldd-sheet nldd-top-title-bar')).toEqual(['Voorbeeldgilde']);
    expect(document.querySelector('nldd-button[text="Opnieuw versturen"]')).not.toBeNull();
  });

  it('warns when no outway is configured', async () => {
    const container = await renderPeers({
      items: [],
      services: SERVICES,
      outway_configured: false,
    });
    expect(texts(container, 'nldd-banner[variant="warning"]')).toEqual([
      'Er is geen outway ingesteld',
    ]);
    expect(texts(container, 'nldd-inline-dialog[slot="empty"]')).toEqual(['Nog geen koppelingen']);
  });
});
