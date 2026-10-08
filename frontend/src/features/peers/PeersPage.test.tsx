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
  is_active: true,
  key_count: 1,
  jwks_fetched_at: '2026-10-08T10:00:00Z',
};
const SERVICES = ['grip-opdrachtverkeer', 'corpus-context'];

afterEach(() => vi.unstubAllGlobals());

async function renderPeers(body: object) {
  mockApi({ '/api/peers': body });
  const view = renderApp(<PeersPage />, {
    path: '/beheer/koppelingen',
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
