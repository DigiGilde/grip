import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { TEST_PERSON, renderApp } from '@/test/utils';
import type { Peer } from './api';
import { PeerSheet } from './PeerSheet';

const PEER: Peer = {
  id: 'p-1',
  version: 1,
  peer_id: '00000000000000000020',
  name: 'Voorbeeldgilde',
  organisation_tooi_uri: '',
  base_uri: 'https://grip.opdrachtnemer.example',
  role: 'counterpart',
  grant_hashes: { 'grip-opdrachtverkeer': '$1$4$grant' },
  financial_inspection: false,
  is_example: false,
  is_active: true,
  key_count: 1,
  jwks_fetched_at: '2026-10-08T10:00:00Z',
  undelivered: 2,
};
const SERVICES = ['grip-opdrachtverkeer', 'corpus-context'];
const MESSAGES = {
  items: [
    {
      id: 'm-1',
      kind: 'Verzoek om een kostenpost',
      reason: 'Het bericht botst met wat de ontvanger al heeft',
      since: '2026-11-27T09:00:00Z',
      retry_until: null,
      final: true,
    },
    {
      id: 'm-2',
      kind: 'Vacature',
      reason: 'De ontvanger kent deze instantie niet',
      since: '2026-11-28T09:00:00Z',
      retry_until: '2026-12-05T09:00:00Z',
      final: false,
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

/** The sheet sits in a portal on the body, outside the rendered container. */
function renderSheet(peer: Peer, routes: Record<string, unknown>) {
  const api = mockApi(routes);
  renderApp(<PeerSheet open peer={peer} services={SERVICES} onClose={() => undefined} />, {
    auth: { status: 'authenticated', person: TEST_PERSON, functions: ['beheerder'] },
  });
  return { container: document.body, api };
}

describe('PeerSheet', () => {
  it('lists the messages that do not arrive, and offers to send a final one again', async () => {
    const { container } = renderSheet(PEER, { '/api/peers/p-1/undelivered': MESSAGES });
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());

    expect(texts(container, 'nldd-title')).toContain('Berichten die niet aankomen');
    expect(texts(container, 'nldd-list nldd-text-cell')).toEqual([
      'Verzoek om een kostenpost',
      'Vacature',
    ]);
    const lines = [...container.querySelectorAll('nldd-list nldd-text-cell')].map((cell) =>
      (cell.getAttribute('supporting-text') ?? '').replace(/ | /g, ' '),
    );
    expect(lines[0]).toMatch(/^Het bericht botst met wat de ontvanger al heeft\. Sinds 27 nov/);
    expect(lines[0]).toMatch(/Komt niet meer vanzelf aan\.$/);
    expect(lines[1]).toMatch(/^De ontvanger kent deze instantie niet\. Sinds 28 nov/);
    expect(lines[1]).toMatch(/Grip probeert het tot 5 dec/);
    // Only the final message has the button; grip still tries the other one.
    const resend = container.querySelectorAll('nldd-list nldd-button[text="Opnieuw versturen"]');
    expect(resend).toHaveLength(1);
    expect(resend[0]?.getAttribute('accessible-label')).toBe(
      'Verzoek om een kostenpost opnieuw versturen',
    );
    // The connection test stays where it was.
    expect(container.querySelector('nldd-button[text="Test de verbinding"]')).not.toBeNull();
  });

  it('shows nothing about messages when every message arrives', async () => {
    const { container, api } = renderSheet(
      { ...PEER, undelivered: 0 },
      { '/api/peers/p-1/undelivered': MESSAGES },
    );
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Test de verbinding"]')).not.toBeNull(),
    );
    expect(texts(container, 'nldd-title')).not.toContain('Berichten die niet aankomen');
    expect(container.querySelector('nldd-list')).toBeNull();
    expect(api.calls.some((call) => call.includes('/undelivered'))).toBe(false);
  });
});
